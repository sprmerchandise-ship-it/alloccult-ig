#!/usr/bin/env python3
"""
"Living painting" motion for Reels: 2.5D parallax + atmospheric overlays.
Free and runs on a plain CPU (GitHub's free runners).

  python motion.py art.jpg out.mp4 [seconds]     # quick test on one image

1. Depth: Depth Anything V2 (small, open weights, ONNX on CPU) estimates what
   is near and what is far in the artwork. Without the model (no onnxruntime,
   download blocked) a heuristic depth is used instead (centre and detail read
   as near), so rendering never fails.
2. Parallax: each frame re-samples the artwork with a moving virtual camera
   (drift, rise or dolly-in). Near parts move more than far parts, so the
   camera seems to travel into the picture. The artwork itself is never redrawn
   or generated: only its pixels are displaced by a few percent.
3. Overlays: drifting smoke, gold dust motes, candle flicker, vignette and film
   grain, all generated from a seed so a re-render is identical.

render_reel.py uses render_segment() in place of the ffmpeg Ken Burns zoom when
posting.json has "motion": "parallax" (the default).
"""
import hashlib, math, os, subprocess, sys, urllib.request
import numpy as np
from PIL import Image

import cv2

W, H, FPS = 1080, 1920, 30
GOLD = (212, 175, 55)

MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "depth_anything_v2_vits.onnx")
MODEL_URLS = [
    "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/download/v2.0.0/"
    "depth_anything_v2_vits.onnx",
]

# Strength knobs (fractions of the artwork's width unless noted).
PARALLAX = 0.022        # how far near parts travel relative to far parts
DRIFT = 0.012           # how far the whole picture travels
DOLLY = 0.10            # extra zoom across a dolly-in segment
SMOKE = 0.16            # smoke opacity (0..1)
DUST = 70               # number of dust motes
FLICKER = 0.035         # candle flicker, +- brightness
GRAIN = 5.0             # film grain, +- levels of 255
VIGNETTE = 0.45         # darkening at the corners (0..1)

MOVES = ["dolly", "drift_right", "rise", "drift_left"]


# ---------------------------------------------------------------- depth

_SESSION = False        # False = not tried yet, None = unavailable


def _session():
    global _SESSION
    if _SESSION is not False:
        return _SESSION
    _SESSION = None
    try:
        import onnxruntime as ort
    except ImportError:
        print("  (onnxruntime missing: heuristic depth)")
        return None
    if not os.path.exists(MODEL_PATH):
        os.makedirs(MODEL_DIR, exist_ok=True)
        for url in MODEL_URLS:
            try:
                print(f"  downloading depth model ({url.rsplit('/', 1)[-1]})")
                urllib.request.urlretrieve(url, MODEL_PATH + ".part")
                os.replace(MODEL_PATH + ".part", MODEL_PATH)
                break
            except Exception as e:                       # noqa: BLE001 — any network failure
                print(f"  depth model download failed ({e})")
    if os.path.exists(MODEL_PATH):
        try:
            _SESSION = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
        except Exception as e:                           # noqa: BLE001 — corrupt file etc.
            print(f"  depth model unusable ({e}); heuristic depth")
            os.remove(MODEL_PATH)
    return _SESSION


def _model_depth(rgb, sess):
    inp = sess.get_inputs()[0]
    side = inp.shape[2] if isinstance(inp.shape[2], int) else 518
    x = cv2.resize(rgb, (side, side), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = (x - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    d = sess.run(None, {inp.name: x})[0].reshape(side, side)
    return cv2.resize(d, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)


def _heuristic_depth(rgb):
    """Engravings and paintings usually put the subject in the middle and the
    detail on the subject: centre + local contrast reads as 'near'."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    centre = np.exp(-(((xx - w / 2) / (0.45 * w)) ** 2 + ((yy - h * 0.55) / (0.5 * h)) ** 2))
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    detail = cv2.GaussianBlur(np.abs(cv2.Laplacian(g, cv2.CV_32F)), (0, 0), max(w, h) / 40)
    detail /= detail.max() + 1e-6
    return 0.6 * centre + 0.4 * detail


_DEPTHS = {}


def depth_map(rgb):
    """Near = 1, far = 0, smoothed so edges stretch softly instead of tearing."""
    key = hashlib.md5(rgb.tobytes()).hexdigest()          # hook + beat 1 share an image
    if key not in _DEPTHS:
        _DEPTHS[key] = _depth_map(rgb)
    return _DEPTHS[key]


def _depth_map(rgb):
    sess = _session()
    d = None
    if sess is not None:
        try:
            d = _model_depth(rgb, sess)
        except Exception as e:                           # noqa: BLE001
            print(f"  depth model failed ({e}); heuristic depth")
    if d is None:
        d = _heuristic_depth(rgb)
    lo, hi = np.percentile(d, (2, 98))
    d = np.clip((d - lo) / (hi - lo + 1e-6), 0, 1).astype(np.float32)
    return cv2.GaussianBlur(d, (0, 0), max(rgb.shape[:2]) / 120)


# ---------------------------------------------------------------- camera

def _ease(t):
    return t * t * (3 - 2 * t)


def camera(move, t):
    """(zoom, dolly, dx, dy) at segment time t in 0..1; dx/dy in art widths."""
    e = _ease(t)
    if move == "dolly":                       # push in with a slight sideways glide
        return 1.04, DOLLY * e, 0.3 * DRIFT * (2 * e - 1), 0.0
    if move == "rise":
        return 1.06, 0.03 * e, 0.0, DRIFT * (1 - 2 * e)
    sign = 1 if move == "drift_right" else -1
    return 1.06, 0.02 * e, sign * DRIFT * (2 * e - 1), 0.0


class Parallax:
    """Pre-computes the depth-weighted sampling grid for one artwork."""

    def __init__(self, art):
        self.art = art
        self.h, self.w = art.shape[:2]
        self.depth = depth_map(art)
        self.focus = float(np.median(self.depth))            # nearer than this moves more
        rel = self.depth - self.focus
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.cx, self.cy = (self.w - 1) / 2, (self.h - 1) / 2
        self.X, self.Y, self.rel = xx - self.cx, yy - self.cy, rel
        self.gain = (1 + PARALLAX / DRIFT * rel).astype(np.float32)

    def frame(self, move, t):
        zoom, dolly, dx, dy = camera(move, t)
        # Near parts (rel > 0) scale and shift more than far ones.
        scale = zoom * (1 + dolly * (1 + self.rel))
        mx = self.cx + self.X / scale + dx * self.w * self.gain
        my = self.cy + self.Y / scale + dy * self.w * self.gain
        return cv2.remap(self.art, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- overlays

def _noise(rng, w, h, octaves=4):
    """Smooth value noise with round (not stretched) features."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cx = 3 * 2 ** o
        cy = max(2, round(cx * h / w))
        g = rng.random((cy + 1, cx + 1)).astype(np.float32)
        out += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.5
    out /= total
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


class Atmosphere:
    """Smoke, dust, flicker, vignette and grain; seeded, so the same segment
    always renders the same way. Works on uint8 frames with OpenCV for speed."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.qw, self.qh = W // 4, H // 4                   # smoke at quarter res
        self.smoke = [_noise(rng, self.qw, self.qh * 2), _noise(rng, self.qw, self.qh * 2)]
        self.hw, self.hh = W // 2, H // 2                   # dust at half res
        n = DUST
        self.px, self.py = rng.random(n) * self.hw, rng.random(n) * self.hh
        self.vx = rng.normal(0, 3, n)                       # half-res px per second
        self.vy = -rng.uniform(4, 18, n)                    # rising
        self.r = rng.uniform(0.7, 1.8, n)
        self.a = rng.uniform(0.25, 0.8, n)
        self.ph = rng.random(n) * 2 * math.pi
        self.flick = rng.random(3) * 2 * math.pi
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
        vig = 1 - VIGNETTE * np.clip(v, 0, 1) ** 2.2
        self.vignette = cv2.merge([vig.astype(np.float32)] * 3)
        tint = np.array(GOLD, np.float32) * 0.6 + 255 * 0.4
        self.tint = np.empty((H, W, 3), np.uint8)
        self.tint[:] = tint.astype(np.uint8)
        g = np.empty((H + 64, W + 64, 3), np.float32)
        cv2.randn(g, 0, GRAIN)
        g = cv2.cvtColor(cv2.cvtColor(g, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)  # mono grain
        self.grain_pos = np.clip(g, 0, 255).astype(np.uint8)
        self.grain_neg = np.clip(-g, 0, 255).astype(np.uint8)
        self.rng = np.random.default_rng(seed + 1)

    def flicker(self, s):
        f = self.flick
        return 1 + FLICKER * (0.6 * math.sin(7.1 * s + f[0]) + 0.3 * math.sin(13.3 * s + f[1])
                              + 0.1 * math.sin(29.0 * s + f[2]))

    def glow(self, s):
        """Single-channel 0..1 mask of smoke + dust at full res."""
        qh = self.qh
        o1 = int(s * 9) % qh                                # scroll up, two speeds
        o2 = int(s * 5) % qh
        m = self.smoke[0][qh - o1: 2 * qh - o1] * self.smoke[1][o2: o2 + qh]
        m = np.clip((m - 0.18) * 2.2, 0, 1) ** 1.5 * SMOKE
        m = cv2.resize(m, (self.hw, self.hh), interpolation=cv2.INTER_CUBIC)
        x = (self.px + self.vx * s + 6 * np.sin(0.7 * s + self.ph)) % self.hw
        y = (self.py + self.vy * s) % self.hh
        tw = self.a * (0.6 + 0.4 * np.sin(2.3 * s + self.ph))
        dust = np.zeros_like(m)
        for xi, yi, ri, ai in zip(x, y, self.r, tw):
            cv2.circle(dust, (int(xi * 16), int(yi * 16)), max(1, int(ri * 16)), float(ai),
                       -1, cv2.LINE_AA, shift=4)
        m = np.minimum(m + cv2.GaussianBlur(dust, (0, 0), 0.9) * 0.9, 1)
        return cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)

    def grain(self, frame):
        ox, oy = self.rng.integers(0, 64, 2)
        cv2.add(frame, self.grain_pos[oy:oy + H, ox:ox + W], frame)
        cv2.subtract(frame, self.grain_neg[oy:oy + H, ox:ox + W], frame)
        return frame


# ---------------------------------------------------------------- segment

def _encoder(out, seconds):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-t", f"{seconds}", out], stdin=subprocess.PIPE)


def render_segment(base, art_box, art, text_rgba, seconds, out, move, seed,
                   text_delay=0.3, frame_rect=None):
    """Write one segment clip (H.264, no audio).

    base       RGB PIL image: the blurred backdrop, or the drawn sigil card
    art_box    (x, y) where the artwork sits on base, or None
    art        RGB PIL artwork already sized to its box, or None (slow zoom only)
    text_rgba  RGBA PIL text layer, faded in from text_delay
    frame_rect gold frame (x0, y0, x1, y1) redrawn over the moving artwork
    """
    frames = int(seconds * FPS)
    atm = Atmosphere(seed)
    base = cv2.multiply(np.asarray(base, np.float32), atm.vignette).astype(np.uint8)
    tx = np.asarray(text_rgba.convert("RGBA"))
    t_rgb = np.ascontiguousarray(tx[..., :3])
    t_a = tx[..., 3].astype(np.float32) / 255
    par = Parallax(np.asarray(art.convert("RGB"))) if art is not None else None
    if par is not None:
        x, y = art_box
        vig = atm.vignette[y:y + par.h, x:x + par.w]
    enc = _encoder(out, seconds)
    try:
        for i in range(frames):
            s = i / FPS
            t = i / max(1, frames - 1)
            fl = atm.flicker(s)
            if par is not None:
                f = base.copy()
                a = par.frame(move, t)
                f[y:y + par.h, x:x + par.w] = cv2.multiply(a, vig, scale=fl, dtype=cv2.CV_8U)
                if frame_rect:
                    cv2.rectangle(f, frame_rect[:2], frame_rect[2:], GOLD, 2)
            else:                                           # sigil card: slow zoom only
                M = cv2.getRotationMatrix2D((W / 2, H * 0.4), 0, 1 + 0.06 * _ease(t))
                f = cv2.convertScaleAbs(cv2.warpAffine(base, M, (W, H)), alpha=fl)
            g = atm.glow(s)
            f = cv2.blendLinear(f, atm.tint, 1 - g, g)
            k = float(np.clip((s - text_delay) / 0.5, 0, 1))
            if k > 0:
                ta = t_a * k
                f = cv2.blendLinear(f, t_rgb, 1 - ta, ta)
            atm.grain(f)
            fade = max(0.0, min(1.0, s / 0.35, (seconds - s) / 0.35))   # through black
            if fade < 1:
                f = cv2.convertScaleAbs(f, alpha=fade)
            enc.stdin.write(f.tobytes())
    finally:
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError(f"ffmpeg failed encoding {out}")


def main():
    src, out = sys.argv[1], sys.argv[2]
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    img = Image.open(src).convert("RGB")
    s = min(960 / img.width, 1040 / img.height)
    art = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    base = Image.new("RGB", (W, H), (8, 6, 6))
    x, y = (W - art.width) // 2, 220 + (1040 - art.height) // 2
    render_segment(base, (x, y), art, Image.new("RGBA", (W, H)), secs, out, "dolly", 1,
                   frame_rect=(x - 6, y - 6, x + art.width + 5, y + art.height + 5))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Render a 1080x1920 Reel (H.264 + AAC) from a reel spec, or from carousel slides.

  python render_reel.py queue/2026-10-12.json 0 out/reel.mp4   # spec #0 of a queue file
  python render_reel.py queue/2026-10-12.json all out/bundle  # all 7 + captions.md
  python render_reel.py --slides slides/1789935285 out/reel.mp4 --mood bells

Spec fields used: id, title, hook, beats[{text, seconds, image_query}], mood.
Each beat gets a public-domain museum image (museum.py) with a slow Ken Burns
move, gold-on-black text, fade-through-black cuts, and a soundtrack (music.py).
Resolved images are written back into spec["images"] so a re-render (e.g. the
daily post after the Monday preview) uses exactly the same artwork.

Needs ffmpeg, pillow, numpy, fonttools, and fonts/Cinzel.ttf + fonts/EBGaramond.ttf
(the workflows download them; falls back to PIL's default font without them).
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import museum, music

W, H, FPS = 1080, 1920, 30
GOLD = (212, 175, 55)
PARCHMENT = (236, 226, 204)
DUST = (150, 140, 120)
HOOK_SECONDS, OUTRO_SECONDS = 3.0, 3.0


def font(name, size, weight=None):
    path = f"fonts/{name}.ttf"
    if os.path.exists(path):
        f = ImageFont.truetype(path, size)
        if weight:
            try:
                f.set_variation_by_axes([weight])     # variable-weight Google fonts
            except (OSError, ValueError):
                pass
        return f
    print(f"  (missing {path}, using default font)")
    return ImageFont.load_default(size)


_CMAPS = {}


def drawable(text, fnt):
    """Remove characters the font has no glyph for (e.g. Hebrew) — they would
    render as empty boxes — and tidy the punctuation left behind."""
    path = getattr(fnt, "path", None)
    if not path:
        return text
    if path not in _CMAPS:
        from fontTools.ttLib import TTFont
        _CMAPS[path] = set(TTFont(path).getBestCmap())
    t = "".join(c for c in text if c.isspace() or ord(c) in _CMAPS[path])
    t = " ".join(t.split())
    t = re.sub(r"([.!?,;:])(\s*[.!?,;:])+", r"\1", t)     # "letters. . Count" -> "letters. Count"
    return re.sub(r"\s+([.!?,;:])", r"\1", t).lstrip(".,;:!? ")


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def contain(img, w, h):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def sigil(d, cx, cy, r):
    """Gold heptagram in a double circle — drawn, so it never depends on a font glyph."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=GOLD, width=3)
    d.ellipse((cx - r * 0.92, cy - r * 0.92, cx + r * 0.92, cy + r * 0.92), outline=GOLD, width=1)
    pts = [(cx + r * 0.88 * math.sin(2 * math.pi * k / 7),
            cy - r * 0.88 * math.cos(2 * math.pi * k / 7)) for k in range(7)]
    d.line([pts[(k * 3) % 7] for k in range(8)], fill=GOLD, width=2, joint="curve")


def backdrop(img_path, box=(960, 1040), top=220):
    """Blurred, darkened full-bleed copy behind the framed artwork."""
    canvas = Image.new("RGB", (W, H), (8, 6, 6))
    if not img_path:
        sigil(ImageDraw.Draw(canvas), W / 2, top + box[1] / 2, 230)
        return canvas
    art = Image.open(img_path).convert("RGB")
    bg = cover(art, W, H).filter(ImageFilter.GaussianBlur(40))
    canvas = Image.blend(canvas, bg, 0.35)
    fg = contain(art, *box)
    x, y = (W - fg.width) // 2, top + (box[1] - fg.height) // 2
    canvas.paste(fg, (x, y))
    ImageDraw.Draw(canvas).rectangle((x - 6, y - 6, x + fg.width + 5, y + fg.height + 5),
                                     outline=GOLD, width=2)
    return canvas


def text_layer(text, kind, credit=""):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # Dark gradient so text stays readable over any artwork.
    for i in range(700):
        a = int(230 * (i / 700) ** 1.4)
        d.line([(0, H - 700 + i), (W, H - 700 + i)], fill=(0, 0, 0, a))
    if kind == "hook":
        fnt, colour, y0, gap = font("Cinzel", 80, 700), GOLD, 1380, 100
        text = text.upper()
    elif kind == "outro":
        d.text((W / 2, 1450), "alloccult.com", font=font("Cinzel", 70, 600), fill=GOLD, anchor="mm")
        d.text((W / 2, 1550), "The Forbidden Library", font=font("EBGaramond", 46),
               fill=PARCHMENT, anchor="mm")
        return layer
    else:
        fnt, colour, y0, gap = font("EBGaramond", 60, 500), PARCHMENT, 1390, 76
    lines = wrap(d, drawable(text, fnt), fnt, 920)[:4]
    y = y0                      # grow downward so long text never covers the art
    for line in lines:
        d.text((W / 2, y), line, font=fnt, fill=colour, anchor="mm")
        y += gap
    if credit:
        d.text((W / 2, H - 120), credit[:95], font=font("EBGaramond", 24), fill=DUST, anchor="mm")
    return layer


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{r.stderr[-1500:]}")


def clip(bg_png, text_png, seconds, out, zoom_in=True, text_delay=0.3):
    frames = int(seconds * FPS)
    rate = 0.10 / frames
    z = f"1+{rate}*on" if zoom_in else f"1.10-{rate}*on"
    fade_out = max(0.0, seconds - 0.35)
    vf = (f"[0:v]scale={W * 2}:{H * 2},zoompan=z='{z}':"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}[bg];"
          f"[1:v]format=rgba,fade=in:st={text_delay}:d=0.5:alpha=1[tx];"
          f"[bg][tx]overlay=0:0:shortest=1,fade=in:st=0:d=0.35,"
          f"fade=out:st={fade_out}:d=0.35,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", bg_png,
         "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}", "-i", text_png,
         "-filter_complex", vf, "-map", "[v]", "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), out])


def assemble(clips, seconds, mood, seed, out, tmp):
    listing = os.path.join(tmp, "clips.txt")
    with open(listing, "w") as f:
        f.writelines(f"file '{os.path.abspath(c)}'\n" for c in clips)
    silent = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listing, "-c", "copy", silent])
    audio = music.soundtrack(mood, seconds + 1, seed, os.path.join(tmp, "music.wav"))
    print(f"  audio: {audio}")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-stream_loop", "-1", "-i", audio,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-af", f"afade=in:d=1,afade=out:st={max(0, seconds - 2.5)}:d=2.5,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{seconds}",
         "-movflags", "+faststart", out])


def render_spec(spec, out):
    """Render one reel spec to out (mp4). Fills spec['images'] in place."""
    tmp = tempfile.mkdtemp(prefix="reel_")
    beats = spec["beats"]
    images = spec.get("images") or [None] * len(beats)
    used = {i["key"] for i in images if i}
    paths = []
    for n, beat in enumerate(beats):
        # Try the stored image first, then fresh search results, until one
        # actually downloads (some museum image servers block CI runners).
        p = os.path.join(tmp, f"img{n}.jpg")
        for _ in range(5):
            if not images[n]:
                print(f"  beat {n + 1}: searching '{beat['image_query']}'")
                images[n] = museum.find_image(beat["image_query"], used)
                if not images[n]:
                    break
            used.add(images[n]["key"])
            try:
                museum.download(images[n]["url"], p)
                Image.open(p).verify()
                break
            except Exception as e:                       # noqa: BLE001 — any fetch/decode failure
                print(f"  download failed for {images[n]['key']} ({e}); trying another")
                images[n] = None
        paths.append(p if images[n] else None)
    spec["images"] = images

    segments = [(paths[0], spec["hook"], "hook", HOOK_SECONDS, "")]
    for n, beat in enumerate(beats):
        credit = images[n]["credit"] if images[n] and paths[n] else ""
        segments.append((paths[n], beat["text"], "beat", float(beat.get("seconds", 4)), credit))
    segments.append((paths[-1], "", "outro", OUTRO_SECONDS, ""))

    clips, total = [], 0.0
    for n, (img, text, kind, secs, credit) in enumerate(segments):
        bg = os.path.join(tmp, f"bg{n}.png")
        tx = os.path.join(tmp, f"tx{n}.png")
        backdrop(img).save(bg)
        text_layer(text, kind, credit).save(tx)
        c = os.path.join(tmp, f"clip{n}.mp4")
        clip(bg, tx, secs, c, zoom_in=n % 2 == 0)
        clips.append(c)
        total += secs
    assemble(clips, total, spec.get("mood", "drone"), spec.get("id", spec["hook"]), out, tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"  wrote {out} ({total:.0f}s)")
    return out


def render_slides(slide_dir, out, mood="drone", seconds_each=4.0):
    """Turn a carousel (slides/<id>/*.jpg) into a music Reel — no extra text."""
    tmp = tempfile.mkdtemp(prefix="slides_")
    files = sorted(f for f in os.listdir(slide_dir) if f.lower().endswith((".jpg", ".png")))
    clips = []
    for n, f in enumerate(files):
        bg = os.path.join(tmp, f"bg{n}.png")
        backdrop(os.path.join(slide_dir, f), box=(1080, 1350), top=285).save(bg)
        tx = os.path.join(tmp, f"tx{n}.png")
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(tx)
        c = os.path.join(tmp, f"clip{n}.mp4")
        clip(bg, tx, seconds_each, c, zoom_in=n % 2 == 0)
        clips.append(c)
    assemble(clips, seconds_each * len(clips), mood, slide_dir, out, tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="queue JSON file, or slides dir with --slides")
    ap.add_argument("index", nargs="?", help="reel index in the queue file")
    ap.add_argument("out", nargs="?", default="out/reel.mp4")
    ap.add_argument("--slides", action="store_true")
    ap.add_argument("--mood", default="drone", choices=music.MOODS)
    a = ap.parse_args()
    if a.slides:
        out = a.index or a.out
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        render_slides(a.source, out, a.mood)
        return
    queue = json.load(open(a.source))
    if a.index == "all":
        os.makedirs(a.out, exist_ok=True)
        notes = [f"# ALLOCCULT Reels — week of {queue['week']}\n"]
        for spec in queue["reels"]:
            print(f"Rendering {spec['id']} ({spec['day']}): {spec['title']}")
            render_spec(spec, os.path.join(a.out, f"{spec['id']}.mp4"))
            json.dump(queue, open(a.source, "w"), indent=2, ensure_ascii=False)
            credits = "\n".join(f"- {i['credit']}" for i in spec["images"] if i)
            notes.append(f"## {spec['day']} — {spec['title']}\n\nFile: `{spec['id']}.mp4` · "
                         f"mood: {spec.get('mood')} · archive: alloccult.com{spec['route']}\n\n"
                         f"{spec['caption']}\n\n" + " ".join("#" + h for h in spec["hashtags"])
                         + f"\n\nImages:\n{credits or '- (none found — plain cards)'}\n")
        open(os.path.join(a.out, "captions.md"), "w").write("\n".join(notes))
        return
    spec = queue["reels"][int(a.index or 0)]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    render_spec(spec, a.out)
    json.dump(queue, open(a.source, "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

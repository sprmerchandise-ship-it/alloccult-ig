#!/usr/bin/env python3
"""
Soundtracks for Reels.

1. If music/ holds tracks named <mood>_*.mp3|wav|m4a (e.g. music/ritual_01.mp3),
   one matching the reel's mood is used. Only put tracks there that you have the
   rights to use on Instagram (your own, CC0, or a licence that covers social).
2. Otherwise an original dark-ambient track is generated here with numpy, so
   there is never a copyright claim. Same title -> same track (seeded).

Moods: drone, ritual, bells, choir.

Note: the Instagram API cannot attach tracks from Instagram's own music
library — API-published Reels carry their audio as "Original audio".
"""
import glob, hashlib, os, wave
import numpy as np

SR = 44100
MOODS = ("drone", "ritual", "bells", "choir")
# D2–G2: low but still audible on phone speakers.
ROOTS = [73.42, 77.78, 82.41, 87.31, 92.50, 98.00]


def pick_track(mood, seed_text):
    files = sorted(f for f in glob.glob("music/*")
                   if f.rsplit(".", 1)[-1].lower() in ("mp3", "wav", "m4a")
                   and os.path.basename(f).lower().startswith(mood + "_"))
    if not files:
        return None
    return files[int(hashlib.md5(seed_text.encode()).hexdigest(), 16) % len(files)]


def _env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.linspace(1, 0, r)
    return e


def _lowpass(x, cutoff):
    # One-pole low-pass via FFT mask — cheap and smooth enough for pads.
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(spec, len(x))


def _reverb(x, rng, seconds=3.5, mix=0.45):
    n = int(seconds * SR)
    ir = rng.standard_normal(n) * np.exp(-np.linspace(0, 7, n))
    ir = _lowpass(ir, 4000)
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    return (1 - mix) * x / (np.max(np.abs(x)) + 1e-9) + mix * wet


def _drone(t, root, rng):
    out = np.zeros_like(t)
    for ratio, amp in ((1, 1.0), (1.5, 0.5), (2, 0.45), (3, 0.15), (4, 0.08)):
        for detune in (-0.25, 0.0, 0.3):
            ph = rng.uniform(0, 2 * np.pi)
            out += amp * np.sin(2 * np.pi * (root * ratio + detune) * t + ph)
    swell = 0.65 + 0.35 * np.sin(2 * np.pi * t / rng.uniform(7, 11))
    return out * swell


def _wind(n, rng):
    w = _lowpass(rng.standard_normal(n), 600)
    return w * (0.5 + 0.5 * np.sin(2 * np.pi * np.arange(n) / SR / 13))


def _heartbeat(n, bpm, rng):
    out = np.zeros(n)
    beat = int(SR * 60 / bpm)
    k = np.arange(int(0.35 * SR)) / SR
    thump = np.sin(2 * np.pi * (70 + 50 * np.exp(-k * 25)) * k) * np.exp(-k * 9)
    for start in range(int(SR * 1.5), n - len(thump), beat):
        for off, g in ((0, 1.0), (int(0.28 * SR), 0.6)):     # lub-dub
            s = start + off
            if s + len(thump) < n:
                out[s:s + len(thump)] += g * thump
    return out


def _bells(n, root, rng):
    out = np.zeros(n)
    scale = [1, 6 / 5, 4 / 3, 3 / 2, 9 / 5, 2]          # minor pentatonic-ish
    t = int(SR * rng.uniform(1, 2.5))
    while t < n - SR * 4:
        f = root * 4 * rng.choice(scale)
        k = np.arange(int(SR * 4)) / SR
        b = sum(a * np.sin(2 * np.pi * f * p * k) * np.exp(-k * d)
                for p, a, d in ((1, 1, 1.2), (2.76, 0.5, 2.5), (5.4, 0.25, 4), (8.93, 0.12, 6)))
        out[t:t + len(k)] += b
        t += int(SR * rng.uniform(2.5, 5))
    return out


def _choir(t, root, rng):
    out = np.zeros_like(t)
    for ratio in (2, 2 * 6 / 5, 3, 4):                     # minor triad, open voicing
        for _ in range(6):
            f = root * ratio * (1 + rng.uniform(-0.004, 0.004))
            vib = 0.004 * np.sin(2 * np.pi * rng.uniform(4.5, 5.5) * t)
            saw = 2 * ((f * t * (1 + vib)) % 1) - 1
            out += saw
    return _lowpass(out, root * 14)


def generate(mood, seconds, seed_text, path):
    rng = np.random.default_rng(int(hashlib.md5(seed_text.encode()).hexdigest()[:8], 16))
    n = int(seconds * SR)
    t = np.arange(n) / SR
    root = rng.choice(ROOTS)

    mix = _drone(t, root, rng) * 0.6 + _wind(n, rng) * 0.25
    if mood == "ritual":
        mix += _heartbeat(n, rng.uniform(54, 66), rng) * 2.2
    elif mood == "bells":
        mix = mix * 0.6 + _bells(n, root, rng) * 0.5
    elif mood == "choir":
        mix = mix * 0.4 + _choir(t, root, rng) * 0.12

    left = _reverb(mix, rng)
    right = _reverb(mix, rng)
    stereo = np.stack([left, right], axis=1) * _env(n, 1.5, 2.5)[:, None]
    stereo = stereo / (np.max(np.abs(stereo)) + 1e-9) * 0.8
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def soundtrack(mood, seconds, seed_text, path):
    """Path to an audio file for this reel: a matching music/ track or a generated one."""
    mood = mood if mood in MOODS else "drone"
    return pick_track(mood, seed_text) or generate(mood, seconds, seed_text, path)


if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else "drone"
    print(generate(m, 30, "demo-" + m, f"demo_{m}.wav"))

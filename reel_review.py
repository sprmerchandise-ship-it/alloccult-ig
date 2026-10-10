#!/usr/bin/env python3
"""
Claude reviews every Reel before it can post.

For each spec in a queue file: render → grab a still from the middle of every
segment (hook, each beat, outro) → Claude checks the stills and the text the
same way it checks carousels (facts vs. the archive page, image fit and
appropriateness, legibility, hook, caption) → fixes are applied (new text,
rejected images re-picked, weak beats dropped) → re-render, up to 3 rounds.
The spec gets "status": "approved" or "rejected"; post_reel.py only posts
approved Reels.

  python reel_review.py queue/2026-10-19.json out/posts-2026-10-19
  python reel_review.py queue/2026-10-09.json out/check --check   # live test, saves nothing

Writes the reviewed MP4s and captions.md to the output folder (the weekly
preview bundle). Needs ANTHROPIC_API_KEY and GH_PAT.
"""
import json, os, subprocess, sys

from carousel_ai import SEVERITY, STR, VOICE, _ask, _jpeg_b64, _obj, history_note
from render_reel import HOOK_SECONDS, OUTRO_SECONDS, render_spec
from site_source import page_text

ROUNDS = 4

REVIEW_SCHEMA = _obj({
    "approved": {"type": "boolean"},
    "summary": STR,
    "segments": {"type": "array", "items": _obj({
        "segment": {"type": "integer"},
        "image_ok": {"type": "boolean"},
        "image_problem": STR,
        "new_image_query": STR,
        "text_ok": {"type": "boolean"},
        "text_problem": STR,
        "new_text": STR,
        "drop_beat": {"type": "boolean"},
        "blocking": {"type": "boolean"},
    })},
    "caption_ok": {"type": "boolean"},
    "caption_blocking": {"type": "boolean"},
    "caption_problem": STR,
    "new_caption": STR,
    "new_hashtags": {"type": "array", "items": STR},
})


def stills(spec, mp4, outdir):
    """One frame from each segment, after its text has faded in."""
    durs = [HOOK_SECONDS] + [float(b.get("seconds", 4)) for b in spec["beats"]] + [OUTRO_SECONDS]
    paths, t = [], 0.0
    for n, d in enumerate(durs, start=1):
        p = os.path.join(outdir, f"{spec['id']}_still{n:02d}.jpg")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t + d * 0.6:.2f}",
                        "-i", mp4, "-frames:v", "1", "-q:v", "3", p], check=True)
        paths.append(p)
        t += d
    return paths


def review(spec, frames, source):
    content = []
    for n, p in enumerate(frames, start=1):
        content.append({"type": "text", "text": f"Segment {n}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": _jpeg_b64(p, 540)}})
    images = spec.get("images") or []
    segs = [{"segment": 1, "kind": "hook", "text": spec["hook"],
             "image": (images[0] or {}).get("title", "(none — drawn sigil)") if images else ""}]
    segs += [{"segment": n + 2, "kind": "beat", "text": b["text"],
              "image": ((images[n] if n < len(images) else None) or {}).get("title", "(none — drawn sigil)")}
             for n, b in enumerate(spec["beats"])]
    content.append({"type": "text", "text": f"""These are stills from an Instagram Reel
(one per segment, 1080x1920; the hook reuses beat 1's image; the last segment
is a fixed alloccult.com end card — check it only for legibility). It has an
original ambient soundtrack you can't hear; ignore audio. You are the last
check before it posts publicly on @all.occult. Be strict.

Reject an image if it doesn't show its beat's subject or something clearly
related; if its museum title shows it's a pun or coincidence; if it is
sectarian, racist or hateful propaganda; if it is gratuitous gore or nudity; or
if it's illegible. Reject text that is inaccurate, overclaims, misdates,
contradicts the archive page without good reason, or is clumsy; on-screen lines
must stay short (max ~14 words). Check legibility and that the hook stops a
scroll.

Fixes: "new_image_query" (1–3 words naming the subject, for the Wellcome
Collection), "new_text", or "drop_beat" for a weak beat or one with no fitting
image (keep at least 3 beats). Leave fix fields "" when fine. List every
segment. "approved" is true if nothing blocking remains. "new_hashtags" is []
unless they need changing (then exactly 12, lowercase, no #).

{SEVERITY}
{history_note(spec.get("review_log"))}
SEGMENTS (with each image's museum title):
{json.dumps(segs, ensure_ascii=False, indent=1)}

CAPTION:
{spec['caption']}

HASHTAGS: {' '.join(spec['hashtags'])}

ARCHIVE PAGE TEXT (alloccult.com{spec['route']}):
{source or '(unavailable)'}"""})
    return _ask(VOICE, content, REVIEW_SCHEMA)


def has_blockers(verdict):
    return (any(v["blocking"] and (not v["image_ok"] or not v["text_ok"] or v["drop_beat"])
                for v in verdict["segments"])
            or (verdict["caption_blocking"] and not verdict["caption_ok"]))


def apply_fixes(spec, verdict):
    # Only blocking problems are acted on (see carousel_ai.SEVERITY).
    verdict = {**verdict, "segments": [v for v in verdict["segments"] if v["blocking"]]}
    beats, images = spec["beats"], spec.setdefault("images", [None] * len(spec["beats"]))
    rejects = spec.setdefault("reject_images", [])
    changes = []
    for v in verdict["segments"]:
        seg = v["segment"]
        if seg == 1:                                    # the hook (shows beat 1's image)
            if not v["text_ok"] and v["new_text"]:
                spec["hook"] = v["new_text"]
                changes.append(f"hook: {v['text_problem']}")
            i = 0
        else:
            i = seg - 2
            if not 0 <= i < len(beats):
                continue                                # the end card
            if not v["text_ok"] and v["new_text"]:
                beats[i]["text"] = v["new_text"]
                changes.append(f"beat {i + 1} text: {v['text_problem']}")
        if not v["image_ok"] and i < len(images):
            if images[i]:
                rejects.append(images[i]["key"])
            images[i] = None
            if v["new_image_query"]:
                beats[i]["image_query"] = v["new_image_query"]
            changes.append(f"beat {i + 1} image: {v['image_problem']}")
    drops = sorted({v["segment"] - 2 for v in verdict["segments"]
                    if v["drop_beat"] and 0 <= v["segment"] - 2 < len(beats)}, reverse=True)
    if len(beats) - len(drops) >= 3:
        for i in drops:
            del beats[i]
            if i < len(images):
                del images[i]
            changes.append(f"beat {i + 1} dropped")
    if not verdict["caption_ok"] and verdict["caption_blocking"] and verdict["new_caption"]:
        spec["caption"] = verdict["new_caption"]
        changes.append(f"caption: {verdict['caption_problem']}")
    if len(verdict["new_hashtags"]) == 12:
        spec["hashtags"] = [h.lower().lstrip("#") for h in verdict["new_hashtags"]]
        changes.append("hashtags updated")
    return changes


def review_spec(spec, outdir, source):
    mp4 = os.path.join(outdir, f"{spec['id']}.mp4")
    log = spec.setdefault("review_log", [])
    for rnd in range(1, ROUNDS + 1):
        render_spec(spec, mp4)
        verdict = review(spec, stills(spec, mp4, outdir), source)
        ok = not has_blockers(verdict)            # polish-only notes don't hold a post
        print(f"  review round {rnd}: {'APPROVED' if ok else 'changes needed'} — {verdict['summary']}")
        if ok:
            spec["status"] = "approved"
            log.append({"round": rnd, "approved": True, "summary": verdict["summary"]})
            return True
        changes = apply_fixes(spec, verdict)
        for c in changes:
            print("    fix:", c)
        log.append({"round": rnd, "approved": False, "summary": verdict["summary"], "fixes": changes})
        if not changes:
            break
    spec["status"] = "rejected"
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    qpath, outdir = args[0], args[1]
    check = "--check" in sys.argv          # live test: review 1 Reel from scratch, save nothing
    os.makedirs(outdir, exist_ok=True)
    queue = json.load(open(qpath))
    if check:
        import copy
        spec = copy.deepcopy(queue["reels"][0])
        for k in ("status", "review_log", "images", "reject_images"):
            spec.pop(k, None)
        print(f"Check run: reviewing a fresh copy of {spec['id']} ({spec['title']})")
        ok = review_spec(spec, outdir, page_text(spec["route"]))
        json.dump(spec, open(os.path.join(outdir, "reviewed_spec.json"), "w"), indent=2, ensure_ascii=False)
        print("Result:", spec["status"])
        return
    notes = [f"# ALLOCCULT Reels — week of {queue['week']}\n"]
    for spec in queue["reels"]:
        if spec.get("status") in ("approved", "posted"):
            continue
        print(f"Reviewing {spec['id']} ({spec['day']}): {spec['title']}")
        review_spec(spec, outdir, page_text(spec["route"]))
        json.dump(queue, open(qpath, "w"), indent=2, ensure_ascii=False)   # save as we go
    for spec in queue["reels"]:
        credits = "\n".join(f"- {i['credit']}" for i in spec.get("images") or [] if i)
        notes.append(f"## {spec['day']} — {spec['title']}  [{spec.get('status', 'unreviewed').upper()}]\n\n"
                     f"File: `{spec['id']}.mp4` · mood: {spec.get('mood')} · alloccult.com{spec['route']}\n\n"
                     f"{spec['caption']}\n\n" + " ".join("#" + h for h in spec["hashtags"])
                     + f"\n\nImages:\n{credits or '- (none)'}\n")
    open(os.path.join(outdir, "captions.md"), "w").write("\n".join(notes))
    for f in os.listdir(outdir):                          # stills were for the reviewer only
        if "_still" in f:
            os.remove(os.path.join(outdir, f))
    ok = sum(s.get("status") == "approved" for s in queue["reels"])
    print(f"{ok}/{len(queue['reels'])} Reels approved.")


if __name__ == "__main__":
    main()

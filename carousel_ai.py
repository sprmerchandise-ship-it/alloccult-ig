#!/usr/bin/env python3
"""
Claude writes each carousel and Claude reviews it before it can post.

  write_draft(entry, source_text)  -> draft dict (slides, caption, hashtags)
  review(draft, slide_paths, source_text) -> verdict dict

The review looks at the rendered slides (vision) and the text, and checks:
facts against the archive page and established history; that each image
actually shows the slide's subject and is fit for the brand (no sectarian or
hateful propaganda, no mismatched puns, no gore or nudity for its own sake);
legibility; and the hook. apply_fixes() turns a verdict into edits — new text,
rejected images with new searches — and post.py re-renders and re-reviews
until it passes or gives up.

Needs ANTHROPIC_API_KEY.
"""
import base64, io, json

import anthropic
from PIL import Image

MODEL = "claude-opus-5-5"
_client = None

VOICE = (
    "ALLOCCULT (@all.occult) is a dark occult brand and forbidden-knowledge library "
    "(alloccult.com, 'The Forbidden Library'). Voice: dark, mysterious, esoteric; "
    "slightly forbidden; authoritative but cryptic; short punchy sentences. Every fact "
    "must be historically accurate — real names, dates, texts. Never cheesy or comedic. "
    "Never the phrase 'ancient secrets'. No emojis.")


def _ask(system, content, schema, effort="high"):
    global _client
    _client = _client or anthropic.Anthropic()
    resp = _client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens)")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def _obj(props, required=None):
    return {"type": "object", "properties": props,
            "required": required or list(props), "additionalProperties": False}


STR = {"type": "string"}

DRAFT_SCHEMA = _obj({
    "hook": STR,
    "slides": {"type": "array", "items": _obj({"kicker": STR, "text": STR, "image_query": STR})},
    "caption": STR,
    "hashtags": {"type": "array", "items": STR},
})


def write_draft(entry, source_text, avoid_titles=()):
    """A new carousel about one archive entry, grounded in its page text."""
    prompt = f"""Write an Instagram carousel that makes people stop scrolling, then
sends them to this ALLOCCULT archive entry.

ENTRY: {entry['title']} — alloccult.com{entry['route']}
SECTION: {entry.get('section', '')}
SUMMARY: {entry.get('description', '')}

What works in this niche (from our competitor analysis): image-led slides; a
cover hook that is a question or a startling claim; specific sources — real
names, dates, texts; one idea per slide; a final slide that asks a question
people can actually answer in the comments.

Rules:
- Base every claim on the PAGE TEXT below or on well-established scholarship.
  If the page text states something you know is wrong, leave it out.
- "hook": the cover line, max 8 words.
- 6–8 "slides" after the cover: "kicker" is a short place/name/date label
  (e.g. "Egypt · Anubis", "Lyon · 1538"); "text" max 22 words.
- The last slide asks the audience a question.
- "image_query": 1–3 words naming the thing itself, as a museum catalogue would
  (e.g. "Anubis", "Charon", "astrolabe", "Agrippa", "dance of death"). We
  search the Wellcome Collection first: old prints, woodcuts and manuscripts.
- "caption": 80–140 words, short lines, ends with
  "The full entry waits in the Forbidden Library: alloccult.com{entry['route']}".
- "hashtags": exactly 12, lowercase, no # sign.
- Don't repeat these recent carousels: {', '.join(avoid_titles) or 'none'}.

PAGE TEXT:
{source_text or '(unavailable — rely on well-established scholarship only)'}"""
    data = _ask(VOICE, prompt, DRAFT_SCHEMA)
    slides = [{"text": data["hook"], "image_query": data["slides"][0]["image_query"]}]
    slides += [{"kicker": s["kicker"], "text": s["text"], "image_query": s["image_query"]}
               for s in data["slides"]]
    return {"title": entry["title"], "route": entry["route"], "section": entry.get("section", ""),
            "slides": slides, "caption": data["caption"],
            "hashtags": [h.lower().lstrip("#").replace(" ", "") for h in data["hashtags"]][:12]}


PICK_SCHEMA = _obj({"choice": {"type": "integer"}, "reason": STR})


def pick_image(kicker, text, cands):
    """Index of the museum image that best fits the slide, or -1 if none truly fits.
    Museum titles are descriptive, so this catches title-word puns (an "angelfish"
    for the Angel of Death) before anything is rendered."""
    if not cands:
        return -1
    listing = "\n".join(f"{i}: {c['title']}" for i, c in enumerate(cands))
    prompt = f"""Pick the museum image for this Instagram slide.

SLIDE: {kicker or '(cover)'} — {text}

CANDIDATES (museum catalogue titles):
{listing}

Choose the one that most directly depicts the slide's subject. Reject any that
only share a word with it (a pun or coincidence), unrelated portraits or
landscapes, and sectarian or hateful propaganda. If none truly fits, answer -1.
"choice" is the number; "reason" is one short sentence."""
    data = _ask(VOICE, prompt, PICK_SCHEMA, effort="medium")
    return data["choice"] if -1 <= data["choice"] < len(cands) else -1


REVIEW_SCHEMA = _obj({
    "approved": {"type": "boolean"},
    "summary": STR,
    "slides": {"type": "array", "items": _obj({
        "slide": {"type": "integer"},
        "image_ok": {"type": "boolean"},
        "image_problem": STR,
        "new_image_query": STR,
        "text_ok": {"type": "boolean"},
        "text_problem": STR,
        "new_kicker": STR,
        "new_text": STR,
        "drop_slide": {"type": "boolean"},
    })},
    "caption_ok": {"type": "boolean"},
    "caption_problem": STR,
    "new_caption": STR,
    "new_hashtags": {"type": "array", "items": STR},
})


def _jpeg_b64(path, width=760):
    im = Image.open(path).convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


def review(draft, slide_paths, source_text):
    """Claude's verdict on the rendered carousel. Approves only if it would post it as is."""
    content = []
    for n, p in enumerate(slide_paths, start=1):
        content.append({"type": "text", "text": f"Slide {n}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": _jpeg_b64(p)}})
    meta = [{"slide": n, "kicker": s.get("kicker", "(cover)"), "text": s["text"],
             "image": (s.get("image") or {}).get("title", "(none — drawn sigil)")}
            for n, s in enumerate(draft["slides"], start=1)]
    content.append({"type": "text", "text": f"""You are the last check before this carousel
posts publicly on @all.occult. Be strict: post only if you would be proud of it.

Review every slide (the last slide is a fixed "read the full entry" card — check
it only for legibility) and the caption. Reject an image if it doesn't show the
slide's subject or something clearly related; if its title shows it's a pun or
coincidence (e.g. a costume print called "Une Femme de Charon"); if it is
sectarian, racist or hateful propaganda; if it is gratuitous gore or nudity; or
if it is too poor to read. Reject text that is inaccurate, overclaims, misdates,
contradicts the page text without good reason, or is clumsy. Check legibility,
spelling, and that the hook would stop a scroll.

For each problem give a fix: a better "new_image_query" (1–3 words naming the
subject, for the Wellcome Collection) or "new_kicker"/"new_text". Leave fix
fields "" when that part is fine. List every slide, including fine ones.
Set "drop_slide" true for a content slide that should go — e.g. when no fitting
public-domain image is likely to exist for it — but keep the cover and at
least 4 content slides.
"approved" is true only if nothing needs fixing. "new_hashtags" is [] unless
the hashtags need changing (then exactly 12, lowercase, no #).

SLIDE DATA (with each image's museum title):
{json.dumps(meta, ensure_ascii=False, indent=1)}

CAPTION:
{draft['caption']}

HASHTAGS: {' '.join(draft['hashtags'])}

ARCHIVE PAGE TEXT (alloccult.com{draft['route']}):
{source_text or '(unavailable)'}"""})
    return _ask(VOICE, content, REVIEW_SCHEMA)


def apply_fixes(draft, verdict):
    """Edit the draft per the review. Returns a list of what changed."""
    changes = []
    slides = draft["slides"]
    drops = sorted({v["slide"] - 1 for v in verdict["slides"]
                    if v["drop_slide"] and 0 < v["slide"] - 1 < len(slides)}, reverse=True)
    if len(slides) - len(drops) >= 5:                 # cover + at least 4 content slides
        for i in drops:
            changes.append(f"slide {i + 1} dropped")
        verdict = {**verdict, "slides": [v for v in verdict["slides"] if v["slide"] - 1 not in drops]}
    else:
        drops = []
    for v in verdict["slides"]:
        i = v["slide"] - 1
        if not 0 <= i < len(slides):
            continue                                   # the fixed closing card
        s = slides[i]
        if not v["image_ok"]:
            if s.get("image"):
                s.setdefault("reject", []).append(s["image"]["key"])
            s["image"] = None
            if v["new_image_query"]:
                s["image_query"] = v["new_image_query"]
            changes.append(f"slide {i + 1} image: {v['image_problem']}")
        if not v["text_ok"]:
            if v["new_text"]:
                s["text"] = v["new_text"]
            if v["new_kicker"] and i > 0:
                s["kicker"] = v["new_kicker"]
            changes.append(f"slide {i + 1} text: {v['text_problem']}")
    for i in drops:
        del slides[i]
    if not verdict["caption_ok"] and verdict["new_caption"]:
        draft["caption"] = verdict["new_caption"]
        changes.append(f"caption: {verdict['caption_problem']}")
    if len(verdict["new_hashtags"]) == 12:
        draft["hashtags"] = [h.lower().lstrip("#") for h in verdict["new_hashtags"]]
        changes.append("hashtags updated")
    return changes

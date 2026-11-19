#!/usr/bin/env python3
"""
Turn the week's planned Reels (plan/YYYY-MM-DD.json, from planner.py) into
the structured specs the video renderer needs → queue/YYYY-MM-DD.json.

Reels are fast countdowns: a 2.5 s hook, then 5–7 numbered beats of 2.5–4.5 s.
render_reel.py renders a spec; reel_review.py checks it; post_reel.py posts
each approved Reel on its planned date.

Needs an AI key (see llm.py).
"""
import glob, json, os, sys

import llm
from carousel_ai import VOICE
from music import MOODS

QUEUE_DIR = "queue"

PROMPT = """Write the on-screen script for this Instagram Reel for @all.occult.

PLAN:
{item}

It is a fast countdown: every beat is one numbered item, counting down to the
strongest one last (e.g. "3 · The Codex Gigas…", "2 · …", "1 · …").

Rules:
- Use only facts from the plan, or ones you are certain of. Every date, name
  and number must be historically accurate.
- On-screen text uses the Latin alphabet only — transliterate Hebrew, Greek or
  Coptic words.
- "hook": on-screen opener, max 8 words, no trailing full stop; a startling,
  specific claim (the plan's hook, tightened if needed).
- "beats": 5–7 items. "text" max 12 words, starting with its number and " · ".
  "seconds" 2.5–4.5. Total of all beats 15–25 seconds.
- "image_query": 1–3 plain words a museum catalogue would match, for a
  public-domain artwork of that beat's subject — e.g. "alchemy", "astrolabe",
  "Saturn", "dance of death", "Codex Gigas", "zodiac man", "memento mori". We
  search the Wellcome Collection first (old prints, woodcuts, manuscripts on
  magic, medicine, death and religion), so name the thing itself, not a mood.
  A different query for every beat.
- "mood": one of {moods} — the soundtrack feel.
- "caption": max 90 words, short lines; opens with the hook idea, ends with the
  plan's question{site}. No giveaways or product promotion.
- "hashtags": exactly 12, lowercase, no # sign.
"""

SPEC_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["hook", "beats", "mood", "caption", "hashtags"], "properties": {
    "hook": {"type": "string"},
    "beats": {"type": "array", "items": {"type": "object", "additionalProperties": False,
              "required": ["text", "seconds", "image_query"], "properties": {
                  "text": {"type": "string"}, "seconds": {"type": "number"},
                  "image_query": {"type": "string"}}}},
    "mood": {"type": "string"},
    "caption": {"type": "string"},
    "hashtags": {"type": "array", "items": {"type": "string"}},
}}


def validate(spec):
    problems = []
    beats = spec.get("beats") or []
    if not 4 <= len(beats) <= 7:
        problems.append(f"{len(beats)} beats (want 5–7)")
    for b in beats:
        b["seconds"] = min(4.5, max(2.5, float(b.get("seconds", 3.5))))
        if not b.get("text") or not b.get("image_query"):
            problems.append("beat missing text/image_query")
    if spec.get("mood") not in MOODS:
        spec["mood"] = "drone"
    spec["hashtags"] = [h.lower().lstrip("#").replace(" ", "") for h in spec.get("hashtags", [])][:12]
    if not spec.get("hook") or not spec.get("caption"):
        problems.append("missing hook/caption")
    return problems


def compose(item):
    site = (f", then a last line pointing to alloccult.com{item['related_route']}"
            if item.get("related_route") else "")
    prompt = PROMPT.format(item=json.dumps(item, ensure_ascii=False, indent=1),
                           moods=", ".join(MOODS), site=site)
    for _ in range(2):
        try:
            spec = llm.ask_json(VOICE, prompt, SPEC_SCHEMA)
            problems = validate(spec)
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            spec, problems = None, [f"not valid spec JSON ({e})"]
        if not problems:
            return spec
        print(f"  {item['title']}: " + "; ".join(problems))
        prompt += "\n\nYour previous answer had these problems, fix them:\n" + "\n".join(problems)
    return None


def main():
    plans = sorted(glob.glob("plan/????-??-??.json"))
    if not plans:
        sys.exit("No plan in plan/ — run planner.py first.")
    plan = json.load(open(plans[-1], encoding="utf-8"))
    out = os.path.join(QUEUE_DIR, f"{plan['week']}.json")
    if os.path.exists(out):
        print(f"{out} already exists — keeping it.")
        return
    reels = []
    for item in plan["items"]:
        if item["format"] != "reel":
            continue
        print(f"Composing {item['day']} {item['date']}: {item['title']}")
        spec = compose(item)
        if not spec:
            print("  could not compose a valid spec — skipping this Reel")
            continue
        reels.append({"id": item["id"], "day": item["day"], "date": item["date"],
                      "title": item["title"], "route": item.get("related_route", ""),
                      "section": item["pillar"], "facts": item["facts"], **spec})
    if not reels:
        sys.exit("No Reel specs composed.")
    os.makedirs(QUEUE_DIR, exist_ok=True)
    json.dump({"week": plan["week"], "plan": plans[-1], "reels": reels},
              open(out, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {out}: " + "; ".join(f"{r['day'][:3]} {r['title']}" for r in reels))


if __name__ == "__main__":
    main()

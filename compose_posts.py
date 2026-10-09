#!/usr/bin/env python3
"""
Turn this week's intel report into 7 structured Reel specs.

Reads the newest reports/YYYY-MM-DD.md (written by Claude Code from
competitors/scan.json) plus archive_index.json, asks Claude for one Reel spec
per day, validates them, and writes queue/YYYY-MM-DD.json. render_reel.py
renders a spec; post_reel.py publishes the next unposted one each day.

Needs ANTHROPIC_API_KEY.
"""
import glob, json, os, re, sys, urllib.request

from post import BRAND, CLAUDE_MODEL
from music import MOODS

QUEUE_DIR = "queue"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

PROMPT = """Below is this week's competitor-intel report for @all.occult. Its
section 6 has 7 Reel scripts, Monday to Sunday. Convert each one into the JSON
spec our video renderer needs. Keep the report's ideas; tighten the wording.

Rules:
- "route" must be one of the archive routes listed below (pick the closest).
- Keep every date, name, number and quotation exactly as the report has them.
- On-screen text ("hook", beat "text") uses the Latin alphabet only —
  transliterate Hebrew, Greek or Coptic words (e.g. "NRWN QSR", "Abraxas").
- "hook": on-screen opener, max 8 words, no trailing full stop.
- "beats": 4–6 items. "text" max 14 words — one punchy line on screen.
  "seconds" 3.5–6. Total of all beats 18–32 seconds.
- "image_query": 1–3 plain words a museum catalogue would match, for a
  public-domain artwork that fits that beat — e.g. "alchemy", "astrolabe",
  "Saturn", "dance of death", "witches sabbath", "Hermes", "zodiac man",
  "memento mori", "Kabbalah", "Mithras", "skeleton", "vampire", "witch".
  The first search is the Wellcome Collection (old prints, woodcuts and
  manuscripts on magic, medicine, death and religion), so name the thing
  itself, not a scene or a mood. No modern or abstract phrases.
  Use a different query for every beat.
- "mood": one of {moods} — the soundtrack feel.
- "caption": max 90 words, ends by pointing to alloccult.com.
- "hashtags": exactly 12, lowercase, no # sign.
- Every fact must be historically accurate.

Return ONLY JSON: {{"reels": [{{"day", "title", "route", "hook", "beats":
[{{"text", "seconds", "image_query"}}], "mood", "caption", "hashtags"}}]}}
with exactly 7 reels in day order.

ARCHIVE ROUTES (route — title):
{routes}

REPORT:
{report}
"""


def claude_json(prompt, system, max_tokens=8000):
    # post.claude() caps output at 1500 tokens with a 90 s timeout — too small
    # for 7 full specs, so this call gets its own limits.
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": CLAUDE_MODEL, "max_tokens": max_tokens, "system": system,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode())
    raw = "".join(b["text"] for b in resp["content"] if b["type"] == "text")
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])


def latest_report():
    reports = sorted(glob.glob("reports/????-??-??.md"))
    if not reports:
        sys.exit("No report in reports/ — run the intel step first.")
    return reports[-1]


def validate(reels, routes):
    problems = []
    if len(reels) != 7:
        problems.append(f"expected 7 reels, got {len(reels)}")
    for i, r in enumerate(reels):
        tag = f"reel {i + 1}"
        if r.get("route") not in routes:
            problems.append(f"{tag}: unknown route {r.get('route')!r}")
        beats = r.get("beats") or []
        if not 3 <= len(beats) <= 7:
            problems.append(f"{tag}: {len(beats)} beats")
        for b in beats:
            b["seconds"] = min(6.0, max(3.5, float(b.get("seconds", 4.5))))
            if not b.get("text") or not b.get("image_query"):
                problems.append(f"{tag}: beat missing text/image_query")
        if r.get("mood") not in MOODS:
            r["mood"] = "drone"
        r["hashtags"] = [h.lower().lstrip("#").replace(" ", "")
                         for h in r.get("hashtags", [])][:12]
        if not r.get("hook") or not r.get("caption"):
            problems.append(f"{tag}: missing hook/caption")
    return problems


def main():
    path = latest_report()
    week = re.search(r"(\d{4}-\d{2}-\d{2})", path).group(1)
    archive = json.load(open("archive_index.json", encoding="utf-8"))
    routes = {e["route"]: e for e in archive}
    route_list = "\n".join(f"{e['route']} — {e['title']}" for e in archive)

    prompt = PROMPT.format(moods=", ".join(MOODS), routes=route_list,
                           report=open(path, encoding="utf-8").read())
    for attempt in range(2):
        try:
            reels = claude_json(prompt, BRAND).get("reels", [])
            problems = validate(reels, routes)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            reels, problems = [], [f"response was not valid spec JSON ({e})"]
        if not problems:
            break
        print("Spec problems:", *problems, sep="\n  ")
        prompt += ("\n\nYour previous answer had these problems, fix them:\n"
                   + "\n".join(problems))
    else:
        sys.exit("Claude could not produce valid reel specs.")

    for i, r in enumerate(reels):
        r["id"] = f"{week}-{i + 1}"
        r["day"] = DAYS[i]
        r["section"] = routes[r["route"]].get("section", "")
    os.makedirs(QUEUE_DIR, exist_ok=True)
    out = os.path.join(QUEUE_DIR, f"{week}.json")
    json.dump({"week": week, "report": path, "reels": reels},
              open(out, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {out}: " + "; ".join(f"{r['day'][:3]} {r['title']}" for r in reels))


if __name__ == "__main__":
    main()

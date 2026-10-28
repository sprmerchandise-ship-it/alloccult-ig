#!/usr/bin/env python3
"""
Weekly competitor-intel report, written by the model from competitors/scan.json.

Replaces the Claude Code step: the scan (~120 KB) is boiled down to the posts
that matter, then two requests — one for the analysis, one for the 7 Reel
scripts compose_posts.py turns into specs — each fit inside a free GitHub
Models request (~8k tokens in, ~4k out). Writes reports/YYYY-MM-DD.md.

  python intel_report.py 2026-10-26

Needs GITHUB_TOKEN (see llm.py).
"""
import glob, json, re, sys

import llm

INTRO = open("intel/analysis_prompt.md", encoding="utf-8").read().split("## Inputs")[0].strip()


def _post(p, caption_chars):
    cap = " ".join((p.get("caption") or "").split())[:caption_chars]
    out = {k: p.get(k) for k in ("handle", "permalink", "format", "timestamp", "likes",
                                  "comments", "likes_hidden", "engagement_rate", "vs_account_median")}
    out["timestamp"] = (out["timestamp"] or "")[:16]
    out["caption"] = cap
    return {k: v for k, v in out.items() if v not in (None, "", False)}


def scan_digest(scan):
    hashtags = scan.get("hashtags")
    if hashtags:
        hashtags = {tag: [_post(p, 140) for p in posts[:3]] for tag, posts in list(hashtags.items())[:6]}
    return json.dumps({
        "lookback_days": scan.get("lookback_days"),
        "posts_analysed": scan.get("posts_analysed"),
        "format_summary": scan.get("format_summary"),
        "accounts_by_median_engagement": scan.get("accounts", [])[:8],
        "top_posts": [_post(p, 200) for p in scan.get("top_posts", [])[:12]],
        "breakout_posts": [_post(p, 200) for p in scan.get("breakout_posts", [])[:8]],
        "hashtags": hashtags or "skipped this week",
    }, ensure_ascii=False, separators=(",", ":"))


def previous_reel_titles():
    reports = sorted(glob.glob("reports/????-??-??.md"))
    if not reports:
        return "none"
    text = open(reports[-1], encoding="utf-8").read()
    return "; ".join(re.findall(r"^### .*?[\"“](.+?)[\"”]", text, re.M)) or "none"


ANALYSIS = """Write sections 1–5 and 7 of this week's competitor-intel report, in
Markdown, from the competitor scan below. Section 6 (Reel scripts) is written
separately — leave it out.

Scan notes: top_posts are ranked by engagement rate ((likes + comments) /
followers). breakout_posts are far above their own account's median
(vs_account_median) — the stronger signal for what content works. Where
likes_hidden is true, engagement is comments-only and understated. Don't
over-read a single post; look for patterns across several accounts.

## 1. Summary — 3–5 bullets: the biggest takeaways.
## 2. What's working — patterns across top and breakout posts: topics, formats,
   hook styles (quote the caption's first line), caption length, posting times,
   calls to action. Link 1–3 permalinks per pattern.
## 3. Formats — Reels vs carousels vs images from format_summary.
## 4. Accounts to watch — the 5 with the highest median engagement.
## 5. Hashtags — what the top hashtag posts share, or one line saying the scan
   was skipped.
## 7. Experiments — 2–3 things to test next week and how we'll know they worked.

Use exactly those "## N. Title" headings. Tight and practical, no preamble,
under 1,200 words.

SCAN:
{scan}"""

SCRIPTS = """Write section 6 of this week's report: 7 Reel scripts for the coming
week, Monday to Sunday, for @all.occult. Base each on the analysis below and on
one archive entry from the list (cite its route). Mix topics across different
archive sections. Don't copy any competitor — adapt the pattern to our archive.
Don't repeat last week's Reels: {previous}.

Start with "## 6. Seven Reels". For each, a "### DAY — \\"Title\\"" heading, then:
- Route: the archive route
- Pattern: which observed pattern it applies (with its permalink)
- Hook: on-screen text for the first 1.5 seconds, max 8 words
- Beats: 4–6 lines of on-screen text with rough timings, 20–40 seconds total
- Visual: one line (dark, gold-on-black)
- Caption: max 90 words, ending with a pointer to alloccult.com; then 12
  lowercase hashtags
- Audio: mood only
About 220 words per Reel. Every fact must be historically accurate.

ANALYSIS:
{analysis}

ARCHIVE ROUTES (route — title):
{routes}"""


def main():
    date = sys.argv[1]
    scan = json.load(open("competitors/scan.json", encoding="utf-8"))
    archive = json.load(open("archive_index.json", encoding="utf-8"))
    routes = "\n".join(f"{e['route']} — {e['title']}" for e in archive)

    analysis = llm.ask_text(INTRO, ANALYSIS.format(scan=scan_digest(scan)[:14000]))
    scripts = llm.ask_text(INTRO, SCRIPTS.format(previous=previous_reel_titles(),
                                                 analysis=analysis[:9000], routes=routes))
    # Put section 6 back in its place, before the Experiments section.
    parts = re.split(r"(?=^## *7\b)", analysis, maxsplit=1, flags=re.M)
    body = parts[0].rstrip() + "\n\n" + scripts.strip() + "\n\n" + (parts[1] if len(parts) > 1 else "")
    out = f"reports/{date}.md"
    open(out, "w", encoding="utf-8").write(
        f"# ALLOCCULT — Competitor Intel & Reel Plan ({date})\n\n{body.strip()}\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

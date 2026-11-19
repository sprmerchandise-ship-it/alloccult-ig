#!/usr/bin/env python3
"""
Weekly competitor-intel report, written by the model from competitors/scan.json.

The scan (~120 KB) is boiled down to the posts that matter and analysed in one
request. Writes reports/YYYY-MM-DD.md; planner.py then adds section 6, the
week's content plan.

  python intel_report.py 2026-10-26

Needs an AI key (see llm.py).
"""
import json, sys

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


ANALYSIS = """Write sections 1–5 and 7 of this week's competitor-intel report, in
Markdown, from the competitor scan below. Section 6 (the week's plan) is written
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

def main():
    date = sys.argv[1]
    scan = json.load(open("competitors/scan.json", encoding="utf-8"))
    analysis = llm.ask_text(INTRO, ANALYSIS.format(scan=scan_digest(scan)[:14000]))
    # Section 6 (this week's plan) is added by planner.py.
    out = f"reports/{date}.md"
    open(out, "w", encoding="utf-8").write(
        f"# ALLOCCULT — Competitor Intel & Content Plan ({date})\n\n{analysis.strip()}\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

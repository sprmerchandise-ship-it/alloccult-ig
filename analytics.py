#!/usr/bin/env python3
"""
Pull Instagram insights for past posts, score them, and write learnings.json
(top-performing archive sections) which post.py uses to bias future topics.
Also writes insights.json as a readable performance log.

Needs IG_ACCESS_TOKEN. The token must have the 'instagram_manage_insights'
permission; if it doesn't, this script logs a notice and exits cleanly.
"""
import json, os, time, urllib.request, urllib.error
from collections import defaultdict

GRAPH = "https://graph.facebook.com/v21.0"
METRICS = "reach,saved,total_interactions"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())


def fetch_insights(post_id, token):
    url = f"{GRAPH}/{post_id}/insights?metric={METRICS}&access_token={token}"
    try:
        data = get(url)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "permission" in body.lower() or "insights" in body.lower():
            raise PermissionError(body)
        return None            # metric not available for this media type / too new
    vals = {m["name"]: m["values"][0]["value"] for m in data.get("data", [])}
    reach = vals.get("reach", 0)
    saved = vals.get("saved", 0)
    inter = vals.get("total_interactions", 0)
    vals["score"] = saved * 5 + inter * 2 + reach
    return vals


def main():
    if not os.path.exists("published.json"):
        print("No published.json yet — nothing to analyse.")
        return
    token = os.environ["IG_ACCESS_TOKEN"]
    posts = json.load(open("published.json"))

    scored, by_section = [], defaultdict(list)
    try:
        for p in posts:
            if not p.get("id"):
                continue
            ins = fetch_insights(p["id"], token)
            if not ins:
                continue
            rec = {**p, **ins}
            scored.append(rec)
            if p.get("section"):
                by_section[p["section"]].append(ins["score"])
            time.sleep(1)
    except PermissionError:
        print("Token lacks 'instagram_manage_insights' permission — skipping "
              "analytics. Add it in Graph API Explorer to enable learning.")
        return

    if not scored:
        print("No insights available yet (posts may be under 24h old).")
        return

    scored.sort(key=lambda r: r["score"], reverse=True)
    json.dump(scored, open("insights.json", "w"), indent=2, ensure_ascii=False)

    section_avg = {s: round(sum(v) / len(v), 1) for s, v in by_section.items()
                   if v}
    top_sections = sorted(section_avg, key=section_avg.get, reverse=True)[:3]
    json.dump({"top_sections": top_sections, "section_avg": section_avg,
               "updated": int(time.time())},
              open("learnings.json", "w"), indent=2, ensure_ascii=False)

    print("Top sections:", top_sections)
    print("Best post score:", scored[0]["score"], "-", scored[0].get("ref"))


if __name__ == "__main__":
    main()

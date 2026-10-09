#!/usr/bin/env python3
"""
Weekly competitor scan for @all.occult.

Pulls recent posts from the accounts in competitors/handles.txt via the
Instagram Graph API Business Discovery endpoint, ranks them by engagement rate
((likes + comments) / followers), and samples top posts for the hashtags in
competitors/hashtags.txt. Writes competitors/scan.json, which the Claude Code
analysis step (intel/analysis_prompt.md) turns into the weekly report.

Needs IG_ACCESS_TOKEN and IG_USER_ID. Only Business/Creator competitor accounts
can be read. The hashtag part needs the Public Content Access feature on the
Meta app; without it, it is skipped and the account scan still runs.
"""
import json, os, statistics, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

GRAPH = "https://graph.facebook.com/v21.0"
HANDLES_FILE = "competitors/handles.txt"
HASHTAGS_FILE = "competitors/hashtags.txt"
OUT = "competitors/scan.json"
LOOKBACK_DAYS = 30
POSTS_PER_ACCOUNT = 25
TOP_N = 40
MEDIA_FIELDS = ("id,caption,media_type,media_product_type,like_count,"
                "comments_count,timestamp,permalink")


class GraphError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:300]}")
        try:
            self.error = json.loads(body).get("error", {})
        except ValueError:
            self.error = {}


def get(path, params):
    params = {**params, "access_token": os.environ["IG_ACCESS_TOKEN"]}
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GraphError(e.code, e.read().decode())


def read_list(path):
    if not os.path.exists(path):
        return []
    items = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip().lstrip("@#")
        if line and line.lower() not in (i.lower() for i in items):
            items.append(line)
    return items


def parse_ts(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def post_record(m, handle=None, followers=None):
    likes = m.get("like_count")          # missing when the owner hides likes
    comments = m.get("comments_count") or 0
    rec = {
        "handle": handle,
        "permalink": m.get("permalink"),
        "timestamp": m.get("timestamp"),
        "format": "REEL" if m.get("media_product_type") == "REELS"
                  else m.get("media_type"),
        "likes": likes,
        "comments": comments,
        "likes_hidden": likes is None,
        "caption": (m.get("caption") or "")[:2200],
    }
    if followers:
        rec["engagement_rate"] = round(((likes or 0) + comments) / followers, 5)
    return rec


def scan_account(handle, me, cutoff):
    fields = (f"business_discovery.username({handle})"
              f"{{username,followers_count,media_count,"
              f"media.limit({POSTS_PER_ACCOUNT}){{{MEDIA_FIELDS}}}}}")
    bd = get(me, {"fields": fields})["business_discovery"]
    followers = bd.get("followers_count") or 0
    posts = [post_record(m, handle, followers)
             for m in bd.get("media", {}).get("data", [])
             if m.get("timestamp") and parse_ts(m["timestamp"]) >= cutoff]
    rates = [p["engagement_rate"] for p in posts if "engagement_rate" in p]
    return {
        "handle": handle,
        "followers": followers,
        "media_count": bd.get("media_count"),
        "posts_in_window": len(posts),
        "median_engagement_rate": round(statistics.median(rates), 5) if rates else None,
    }, posts


def scan_hashtags(tags, me):
    results = {}
    for tag in tags:
        try:
            found = get("ig_hashtag_search", {"user_id": me, "q": tag}).get("data", [])
            if not found:
                continue
            media = get(f"{found[0]['id']}/top_media", {
                "user_id": me, "limit": 25,
                "fields": "id,caption,media_type,like_count,comments_count,timestamp,permalink",
            }).get("data", [])
        except GraphError as e:
            # Error code 10 / "permission" = Public Content Access not granted.
            if e.error.get("code") == 10 or "permission" in str(e).lower():
                print("Hashtag scan skipped: app lacks Public Content Access.")
                return None
            print(f"  #{tag}: {e}")
            continue
        posts = [post_record(m) for m in media]
        posts.sort(key=lambda p: (p["likes"] or 0) + p["comments"], reverse=True)
        results[tag] = posts[:10]
        print(f"  #{tag}: {len(media)} top posts")
        time.sleep(1)
    return results


def summarise(posts):
    by_format = {}
    for p in posts:
        by_format.setdefault(p["format"], []).append(p["engagement_rate"])
    return {f: {"posts": len(v), "median_engagement_rate": round(statistics.median(v), 5)}
            for f, v in by_format.items()}


def main():
    me = os.environ["IG_USER_ID"]
    handles = read_list(HANDLES_FILE)
    if not handles:
        sys.exit(f"No handles in {HANDLES_FILE} — add 30–50 competitor accounts first.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    accounts, posts, skipped = [], [], []
    print(f"Scanning {len(handles)} accounts (last {LOOKBACK_DAYS} days)...")
    for h in handles:
        try:
            acct, acct_posts = scan_account(h, me, cutoff)
        except GraphError as e:
            # Personal accounts, typos and renamed handles all land here.
            print(f"  @{h}: skipped ({e.error.get('message', e)})")
            skipped.append({"handle": h, "reason": e.error.get("message", str(e))})
            continue
        except KeyError:
            print(f"  @{h}: skipped (no business_discovery data)")
            skipped.append({"handle": h, "reason": "no business_discovery data"})
            continue
        accounts.append(acct)
        posts.extend(acct_posts)
        print(f"  @{h}: {acct['followers']} followers, {len(acct_posts)} recent posts")
        time.sleep(1)                  # stay well under 200 calls/hour

    if not accounts:
        sys.exit("No accounts could be scanned — check the token and handles.")

    posts = [p for p in posts if "engagement_rate" in p]   # drops 0-follower edge cases
    posts.sort(key=lambda p: p["engagement_rate"], reverse=True)
    for p in posts:
        base = next(a["median_engagement_rate"] for a in accounts
                    if a["handle"] == p["handle"])
        # How far above the account's own norm — separates breakout posts from
        # accounts that are simply small and loyal.
        p["vs_account_median"] = round(p["engagement_rate"] / base, 2) if base else None
    accounts.sort(key=lambda a: a["median_engagement_rate"] or 0, reverse=True)

    hashtags = None
    tags = read_list(HASHTAGS_FILE)
    if tags:
        print(f"Sampling {len(tags)} hashtags...")
        hashtags = scan_hashtags(tags, me)

    scan = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lookback_days": LOOKBACK_DAYS,
        "accounts_scanned": len(accounts),
        "posts_analysed": len(posts),
        "format_summary": summarise(posts),
        "accounts": accounts,
        "top_posts": posts[:TOP_N],
        "breakout_posts": sorted((p for p in posts if p["vs_account_median"]),
                                 key=lambda p: p["vs_account_median"],
                                 reverse=True)[:15],
        "hashtags": hashtags,
        "skipped": skipped,
    }
    json.dump(scan, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {OUT}: {len(accounts)} accounts, {len(posts)} posts, "
          f"{len(skipped)} skipped.")


if __name__ == "__main__":
    main()

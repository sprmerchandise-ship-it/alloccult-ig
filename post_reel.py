#!/usr/bin/env python3
"""
Publish the next Reel from this week's queue to @all.occult.

Picks the first unposted spec in the newest queue/YYYY-MM-DD.json, renders it
(render_reel.py — reuses the artwork chosen for Monday's preview), uploads the
MP4 straight to Instagram with the resumable upload API (no public hosting
needed), waits for processing, and publishes. Records the post in
published.json (so analytics.py scores it) and reel_state.json.

  python post_reel.py            # render + publish next reel
  python post_reel.py --dry-run  # render only, print the caption

Needs IG_USER_ID, IG_ACCESS_TOKEN (with instagram_content_publish).
"""
import argparse, glob, json, os, sys, time, urllib.error, urllib.parse, urllib.request

from post import GRAPH, posting_switches, record_published
from render_reel import render_spec

STATE = "reel_state.json"
API_VERSION = GRAPH.rstrip("/").rsplit("/", 1)[-1]        # e.g. v21.0


def call(method, url, params=None, headers=None, body=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Instagram API error ({method} {url.split('?')[0]}): {e.read().decode()}")


def next_spec(posted):
    queues = sorted(glob.glob("queue/????-??-??.json"))
    if not queues:
        return None, None, None
    queue = json.load(open(queues[-1]))
    for i, spec in enumerate(queue["reels"]):
        if spec["id"] not in posted:
            return queues[-1], queue, i
    return queues[-1], queue, None


def caption_for(spec):
    return spec["caption"].strip() + "\n\n" + " ".join("#" + h for h in spec["hashtags"])


def publish(video, caption):
    user, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    container = call("POST", f"{GRAPH}/{user}/media", {
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "thumb_offset": "1000", "access_token": token})
    cid = container["id"]
    upload_url = container.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{cid}"
    size = os.path.getsize(video)
    print(f"Uploading {size / 1e6:.1f} MB to container {cid}...")
    with open(video, "rb") as f:
        res = call("POST", upload_url, body=f.read(), headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if not res.get("success", True):
        sys.exit(f"Upload rejected: {res}")

    for _ in range(60):                                       # up to ~10 min
        st = call("GET", f"{GRAPH}/{cid}", {"fields": "status_code,status", "access_token": token})
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            sys.exit(f"Instagram could not process the video: {st}")
        time.sleep(10)
    else:
        sys.exit("Timed out waiting for Instagram to process the video.")

    return call("POST", f"{GRAPH}/{user}/media_publish",
                {"creation_id": cid, "access_token": token})["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not posting_switches()["reels"]:
        print("Reel posting is paused (posting.json: reels=false).")
        return

    state = json.load(open(STATE)) if os.path.exists(STATE) else {"posted": []}
    qpath, queue, idx = next_spec(set(state["posted"]))
    if idx is None:
        print("Nothing to post: no queue yet, or this week's reels are all published.")
        return
    spec = queue["reels"][idx]
    print(f"Reel {spec['id']} ({spec['day']}): {spec['title']}")

    os.makedirs("out", exist_ok=True)
    video = render_spec(spec, f"out/{spec['id']}.mp4")
    json.dump(queue, open(qpath, "w"), indent=2, ensure_ascii=False)   # keep chosen images
    caption = caption_for(spec)
    if a.dry_run:
        print(f"\nDry run — rendered {video}\n\n{caption}")
        return

    media_id = publish(video, caption)
    record_published(media_id, "reel", spec["route"], spec.get("section", ""))
    state["posted"].append(spec["id"])
    json.dump(state, open(STATE, "w"), indent=2)
    print(f"Published reel {media_id}")


if __name__ == "__main__":
    main()

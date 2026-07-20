#!/usr/bin/env python3
"""
Rebuild archive_index.json from the live alloccult.com source repo.
Reads src/data/searchIndex.ts from the-occult-archive so newly published
entries are picked up automatically. Requires GH_PAT env var.
"""
import base64, json, os, re, urllib.request

SITE_REPO = "sprmerchandise-ship-it/the-occult-archive"
INDEX_PATH = "src/data/searchIndex.ts"
OUT = "archive_index.json"


def fetch_index():
    url = f"https://api.github.com/repos/{SITE_REPO}/contents/{INDEX_PATH}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {os.environ['GH_PAT']}",
        "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    return base64.b64decode(data["content"]).decode("utf-8")


def parse(ts):
    blocks = re.findall(
        r'\{\s*title:\s*"((?:[^"\\]|\\.)*)",\s*route:\s*"([^"]+)",\s*'
        r'section:\s*"([^"]+)",\s*description:\s*"((?:[^"\\]|\\.)*)",\s*'
        r'keywords:\s*\[([^\]]*)\]', ts)
    entries = []
    for title, route, section, desc, kw in blocks:
        if route.count("/") < 2:      # skip home + section landing pages
            continue
        entries.append({
            "title": title, "route": route, "section": section,
            "description": desc,
            "keywords": re.findall(r'"([^"]+)"', kw)})
    return entries


def main():
    entries = parse(fetch_index())
    if not entries:
        raise SystemExit("No entries parsed — aborting so we don't wipe the index.")
    old = json.load(open(OUT)) if os.path.exists(OUT) else []
    json.dump(entries, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"Archive rebuilt: {len(entries)} entries (was {len(old)}).")


if __name__ == "__main__":
    main()

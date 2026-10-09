#!/usr/bin/env python3
"""
Find public-domain artwork for Reels from museum open-access APIs.

Sources (no API keys needed), tried in order:
  - Wellcome Collection: alchemy, magic, astrology manuscripts (PDM / CC0 only)
  - The Met: Open Access, isPublicDomain objects
  - Art Institute of Chicago: is_public_domain artworks

find_image(query) returns {"url", "title", "credit", "source", "key"} or None.
Every result is public domain / CC0, so Reels can use it freely; the credit line
is still shown on screen as good practice.
"""
import json, urllib.error, urllib.parse, urllib.request

UA = {"User-Agent": "alloccult-reels/1.0 (+https://alloccult.com)"}
TIMEOUT = 30


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def wellcome(query, limit=15):
    url = ("https://api.wellcomecollection.org/catalogue/v2/images?"
           + urllib.parse.urlencode({"query": query, "pageSize": limit,
                                     "locations.license": "pdm,cc-0"}))
    out = []
    for r in get_json(url).get("results", []):
        loc = next((l for l in r.get("locations", [])
                    if l.get("license", {}).get("id") in ("pdm", "cc-0")), None)
        if not loc or not loc.get("url", "").endswith("/info.json"):
            continue
        title = (r.get("source") or {}).get("title", "Untitled")
        out.append({
            "key": f"wellcome:{r['id']}",
            "url": loc["url"].replace("/info.json", "/full/1600,/0/default.jpg"),
            "title": title,
            "credit": f"{title[:70]} — Wellcome Collection (public domain)",
            "source": "wellcome"})
    return out


def met(query, limit=15):
    url = ("https://collectionapi.metmuseum.org/public/collection/v1/search?"
           + urllib.parse.urlencode({"q": query, "hasImages": "true"}))
    ids = (get_json(url).get("objectIDs") or [])[:limit]
    out = []
    for oid in ids:
        try:
            o = get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        except (urllib.error.URLError, ValueError):
            continue
        if not o.get("isPublicDomain") or not o.get("primaryImage"):
            continue
        who = o.get("artistDisplayName") or o.get("culture") or ""
        title = o.get("title") or "Untitled"
        out.append({
            "key": f"met:{oid}",
            "url": o["primaryImage"],
            "title": title,
            "credit": f"{title[:60]}{', ' + who if who else ''} — The Met (public domain)",
            "source": "met"})
        if len(out) >= 5:
            break
    return out


def aic(query, limit=15):
    url = ("https://api.artic.edu/api/v1/artworks/search?"
           + urllib.parse.urlencode({"q": query, "limit": limit,
                                     "query[term][is_public_domain]": "true",
                                     "fields": "id,title,image_id,artist_title"}))
    out = []
    for a in get_json(url).get("data", []):
        if not a.get("image_id"):
            continue
        title = a.get("title") or "Untitled"
        who = a.get("artist_title") or ""
        out.append({
            "key": f"aic:{a['id']}",
            # 843px wide is the size AIC guarantees for every public-domain image.
            "url": f"https://www.artic.edu/iiif/2/{a['image_id']}/full/843,/0/default.jpg",
            "title": title,
            "credit": f"{title[:60]}{', ' + who if who else ''} — Art Institute of Chicago (public domain)",
            "source": "aic"})
    return out


SOURCES = [wellcome, met, aic]


def find_image(query, exclude=()):
    """First unused public-domain image for query; retries with a shorter query."""
    words = query.split()
    attempts = [query] + ([" ".join(words[:2])] if len(words) > 2 else [])
    for q in attempts:
        for src in SOURCES:
            try:
                for cand in src(q):
                    if cand["key"] not in exclude:
                        return cand
            except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
                print(f"  {src.__name__}({q!r}) failed: {e}")
    return None


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


if __name__ == "__main__":
    import sys
    print(json.dumps(find_image(" ".join(sys.argv[1:]) or "alchemy"), indent=2))

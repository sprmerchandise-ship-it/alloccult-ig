#!/usr/bin/env python3
"""
Fetch the readable text of an alloccult.com page from the site's source repo,
so carousels are written from (and checked against) what the archive says.

Route → component via src/App.tsx, component → src/pages/<File>.tsx, then the
prose is pulled out of string literals and JSX text. Needs GH_PAT (the same
token build_archive.py uses); returns "" if it can't be fetched.
"""
import base64, json, os, re, urllib.error, urllib.request

SITE_REPO = "sprmerchandise-ship-it/the-occult-archive"


def _fetch(path):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{SITE_REPO}/contents/{path}",
        headers={"Authorization": f"Bearer {os.environ['GH_PAT']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return base64.b64decode(json.loads(r.read().decode())["content"]).decode("utf-8")


def page_file(app_tsx, route):
    m = re.search(rf'<Route\s+path="{re.escape(route)}"\s+element={{<(\w+)', app_tsx)
    if not m:
        return None
    imp = re.search(rf'import\s+{m.group(1)}\s+from\s+"\./([^"]+)"', app_tsx)
    return f"src/{imp.group(1)}.tsx" if imp else None


def prose(tsx, limit=60000):
    """Sentences from string literals and JSX text, in page order, de-duplicated."""
    parts = re.findall(r'"((?:[^"\\]|\\.){40,})"|>\s*([^<>{}]{40,}?)\s*<', tsx)
    seen, out = set(), []
    for a, b in parts:
        t = " ".join((a or b).replace('\\"', '"').split())
        letters = sum(c.isalpha() or c.isspace() for c in t) / len(t)
        code_like = any(x in t for x in ("{", "}", "=", "<", ">", ";", "/*", "=>"))
        if (t not in seen and not code_like and letters > 0.8 and len(t.split()) >= 6
                and not t.startswith(("http", "font-", "text-", "px-", "bg-"))):
            seen.add(t)
            out.append(t)
    return "\n".join(out)[:limit]


def page_text(route):
    try:
        app = _fetch("src/App.tsx")
        f = page_file(app, route)
        return prose(_fetch(f)) if f else ""
    except (KeyError, urllib.error.URLError, ValueError) as e:
        print(f"  (couldn't fetch site source for {route}: {e})")
        return ""


if __name__ == "__main__":
    import sys
    print(page_text(sys.argv[1] if len(sys.argv) > 1 else "/death-afterlife/death-cults-psychopomps")[:3000])

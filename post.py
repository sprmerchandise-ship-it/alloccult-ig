#!/usr/bin/env python3
"""ALLOCCULT Instagram Automation v3 — bold minimal carousels."""

import html, json, os, re, sys, time, subprocess, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

ETSY_SHOP = "alloccult"
STORE_URL = f"https://{ETSY_SHOP}.etsy.com"
SITE_URL = "alloccult.com"
REPO_RAW = "https://raw.githubusercontent.com/sprmerchandise-ship-it/alloccult-ig/main"
PRODUCT_EVERY_N = 4
STATE_FILE = "state.json"
CLAUDE_MODEL = "claude-sonnet-4-6"
GRAPH = "https://graph.facebook.com/v21.0"
W, H = 1080, 1350

def load_archive():
    with open("archive_index.json", encoding="utf-8") as f:
        return json.load(f)


def http_json(url, data=None, headers=None):
    headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())

def graph_post(path, params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Graph API error on {path}: {e.read().decode()}")

def graph_get(path, fields):
    tok = os.environ["IG_ACCESS_TOKEN"]
    url = f"{GRAPH}/{path}?fields={fields}&access_token={tok}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"counter": 0, "posted_products": [], "posted_lore": []}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), indent=2)

def claude(prompt, system, max_tokens=1500):
    resp = http_json("https://api.anthropic.com/v1/messages",
        data={"model": CLAUDE_MODEL, "max_tokens": max_tokens,
              "system": system, "messages": [{"role": "user", "content": prompt}]},
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()

def claude_json(prompt, system):
    raw = claude(prompt, system).replace("```json", "").replace("```", "").strip()
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])

BRAND = (
    "You are the content brain for ALLOCCULT — a dark occult brand and "
    "forbidden-knowledge library (alloccult.com, 'The Forbidden Library'; shop: "
    "alloccult.etsy.com). Voice: dark, mysterious, esoteric; slightly forbidden, as "
    "if the reader wasn't meant to find this; authoritative but cryptic; short "
    "punchy sentences, never more than about 12 words a line. Every fact must be "
    "historically accurate — real names, dates, texts. Never cheesy or comedic. "
    "Never use the phrase 'ancient secrets'. No emojis except rarely \u2609 "
    "\u263D. Hashtags: exactly 12, lowercase, no # in the array, mixing niche "
    "(#solomonicmagic #grimoire #enochian) with broad (#occult #esoteric).")

def render_slides(hook, slides, outdir, symbol="\u2726", entry_title=""):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    def font(path, size, bold=False):
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_axes([700 if bold else 400])
        except Exception:
            pass
        return f

    HEAD, BODY = "fonts/Cinzel.ttf", "fonts/EBGaramond.ttf"
    SYM = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    GOLD, DIM, BONE, BG = (208, 175, 110), (99, 82, 50), (236, 230, 218), (9, 8, 6)

    def wrap(d, text, fnt, maxw):
        words, lines, cur = text.split(), [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=fnt) <= maxw:
                cur = t
            else:
                lines.append(cur); cur = w_
        if cur:
            lines.append(cur)
        return lines

    def base():
        img = Image.new("RGB", (W, H), BG)
        wm = Image.new("L", (W, H), 0)
        wd = ImageDraw.Draw(wm)
        try:
            wd.text((W / 2, H / 2), symbol,
                    font=ImageFont.truetype(SYM, 900), fill=26, anchor="mm")
        except Exception:
            pass
        wm = wm.filter(ImageFilter.GaussianBlur(2))
        img.paste(Image.new("RGB", (W, H), GOLD), (0, 0), wm)
        d = ImageDraw.Draw(img)
        d.rectangle([44, 44, W - 44, H - 44], outline=GOLD, width=3)
        d.rectangle([58, 58, W - 58, H - 58], outline=DIM, width=1)
        for x, y in [(58, 58), (W - 58, 58), (58, H - 58), (W - 58, H - 58)]:
            d.line([x - 22, y, x + 22, y], fill=GOLD, width=3)
            d.line([x, y - 22, x, y + 22], fill=GOLD, width=3)
        d.text((W / 2, 108), "A L L O C C U L T",
               font=font(HEAD, 32, True), fill=GOLD, anchor="mm")
        d.text((W / 2, H - 108), "The Forbidden Library",
               font=font(BODY, 28), fill=DIM, anchor="mm")
        return img, d

    def divider(d, y):
        d.line([W / 2 - 130, y, W / 2 - 30, y], fill=GOLD, width=2)
        d.line([W / 2 + 30, y, W / 2 + 130, y], fill=GOLD, width=2)
        try:
            d.text((W / 2, y), symbol,
                   font=ImageFont.truetype(SYM, 40), fill=GOLD, anchor="mm")
        except Exception:
            d.ellipse([W / 2 - 6, y - 6, W / 2 + 6, y + 6], outline=GOLD, width=2)

    paths = []

    def save(img, i):
        p = os.path.join(outdir, f"{i:02d}.jpg")
        img.save(p, "JPEG", quality=92)
        paths.append(p)

    img, d = base()
    f = font(HEAD, 92, True)
    lines = wrap(d, hook.upper(), f, W - 200)
    if len(lines) > 3:
        f = font(HEAD, 76, True)
        lines = wrap(d, hook.upper(), f, W - 200)
    lh = 118 if len(lines) < 4 else 98
    y = H / 2 - (len(lines) - 1) * lh / 2
    for ln in lines:
        d.text((W / 2, y), ln, font=f, fill=BONE, anchor="mm")
        y += lh
    divider(d, y + 30)
    d.text((W / 2, H - 210), "swipe  \u2192",
           font=font(BODY, 36), fill=GOLD, anchor="mm")
    save(img, 1)

    for i, s in enumerate(slides, start=2):
        img, d = base()
        d.text((W / 2, 230), f"{i - 1} / {len(slides)}",
               font=font(BODY, 30), fill=DIM, anchor="mm")
        hf = font(HEAD, 54, True)
        hl = wrap(d, s["heading"].upper(), hf, W - 220)
        bf = font(BODY, 52)
        bl = wrap(d, s["body"], bf, W - 250)
        block = len(hl) * 72 + 60 + len(bl) * 72
        y = (H - block) / 2 + 20
        for ln in hl:
            d.text((W / 2, y), ln, font=hf, fill=GOLD, anchor="mm")
            y += 72
        divider(d, y + 8)
        y += 60
        for ln in bl:
            d.text((W / 2, y), ln, font=bf, fill=BONE, anchor="mm")
            y += 72
        save(img, i)

    img, d = base()
    d.text((W / 2, H / 2 - 230), "READ THE FULL ENTRY",
           font=font(HEAD, 50, True), fill=GOLD, anchor="mm")
    divider(d, H / 2 - 150)
    if entry_title:
        tf = font(HEAD, 58, True)
        tl = wrap(d, entry_title.upper(), tf, W - 240)
        y = H / 2 - 60 - (len(tl) - 1) * 36
        for ln in tl:
            d.text((W / 2, y), ln, font=tf, fill=BONE, anchor="mm"); y += 72
    d.text((W / 2, H / 2 + 150), "in the ALLOCCULT archive",
           font=font(BODY, 40), fill=BONE, anchor="mm")
    d.text((W / 2, H / 2 + 235), SITE_URL,
           font=font(HEAD, 50, True), fill=GOLD, anchor="mm")
    d.text((W / 2, H / 2 + 310), "link in bio",
           font=font(BODY, 32), fill=DIM, anchor="mm")
    save(img, len(slides) + 2)
    return paths

def git_push(paths, msg):
    subprocess.run(["git", "add"] + paths, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    if staged:
        subprocess.run(["git", "-c", "user.name=alloccult-bot",
                        "-c", "user.email=bot@alloccult.com",
                        "commit", "-m", msg], check=True)
    subprocess.run(["git", "pull", "--rebase", "-q"], check=True)
    subprocess.run(["git", "push"], check=True)

def wait_ready(cid):
    for _ in range(30):
        st = graph_get(cid, "status_code").get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            sys.exit(f"Container {cid} failed processing")
        time.sleep(5)
    sys.exit("Timed out waiting for media container")

def publish_carousel(image_urls, caption):
    ig = os.environ["IG_USER_ID"]
    children = []
    for u in image_urls:
        c = graph_post(f"{ig}/media", {"image_url": u, "is_carousel_item": "true"})
        children.append(c["id"])
    for cid in children:
        wait_ready(cid)
    parent = graph_post(f"{ig}/media", {"media_type": "CAROUSEL",
                        "children": ",".join(children), "caption": caption})
    wait_ready(parent["id"])
    res = graph_post(f"{ig}/media_publish", {"creation_id": parent["id"]})
    print("Published:", res.get("id"))
    return res.get("id")

def etsy_api_products(key):
    """Etsy Open API v3. key = "keystring:shared_secret" (ETSY_API_KEY secret)."""
    base = "https://openapi.etsy.com/v3/application"
    h = {"x-api-key": key}
    shop = http_json(f"{base}/shops?shop_name={ETSY_SHOP}", headers=h)["results"][0]
    listings = http_json(f"{base}/shops/{shop['shop_id']}/listings/active?limit=100",
                         headers=h)["results"]
    out = []
    for i in range(0, len(listings), 100):
        ids = ",".join(str(l["listing_id"]) for l in listings[i:i + 100])
        for l in http_json(f"{base}/listings/batch?listing_ids={ids}&includes=Images",
                           headers=h)["results"]:
            imgs = [im["url_fullxfull"] for im in l.get("images") or []]
            if not imgs:
                continue
            price = l.get("price") or {}
            out.append({"id": l["listing_id"], "title": html.unescape(l["title"]),
                        "images": imgs[:5],
                        "price": f"{price['amount'] / price['divisor']:.2f} {price.get('currency_code', '')}"
                                 if price.get("divisor") else None,
                        "body": html.unescape(l.get("description") or "")[:500]})
    return out


def etsy_rss_products():
    """Fallback without an API key: the public shop RSS feed (one image per item)."""
    req = urllib.request.Request(f"https://www.etsy.com/shop/{ETSY_SHOP}/rss",
                                 headers={"User-Agent": "Mozilla/5.0 (alloccult-bot)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for item in root.iter("item"):
        desc = item.findtext("description") or ""
        img = re.search(r'<img[^>]+src="([^"]+)"', desc)
        m = re.search(r"/listing/(\d+)", item.findtext("link") or "")
        if not img or not m:
            continue
        price = re.search(r"([\d.,]+\s*[A-Z]{3})", desc)
        out.append({"id": int(m.group(1)),
                    "title": html.unescape(item.findtext("title") or "").split(" by ")[0],
                    "images": [re.sub(r"il_\w+?\.", "il_fullxfull.", img.group(1), count=1)],
                    "price": price.group(1) if price else None,
                    "body": re.sub(r"<[^>]+>", " ", html.unescape(desc))[:500]})
    return out


def fetch_products():
    """Active Etsy listings. Any failure returns [] so the day's post falls back
    to lore instead of failing — otherwise the counter never advances."""
    key = os.environ.get("ETSY_API_KEY", "")
    sources = ([("Etsy API", lambda: etsy_api_products(key))] if key else []) + \
              [("Etsy RSS", etsy_rss_products)]
    for name, fn in sources:
        try:
            products = fn()
            print(f"{name}: {len(products)} products")
            if products:
                return products
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError,
                IndexError, ET.ParseError) as e:
            print(f"WARNING: {name} failed ({e})")
    print("WARNING: no products available; posting lore instead.")
    return []

def pick(items, posted, keyfn):
    fresh = [i for i in items if keyfn(i) not in posted]
    if not fresh:
        posted.clear()
        fresh = items
    return fresh[int(time.time()) % len(fresh)]

def record_published(post_id, kind, ref, section=""):
    recs = []
    if os.path.exists("published.json"):
        try:
            recs = json.load(open("published.json"))
        except Exception:
            recs = []
    recs.append({"id": post_id, "kind": kind, "ref": ref,
                 "section": section, "ts": int(time.time())})
    json.dump(recs, open("published.json", "w"), indent=2, ensure_ascii=False)


def load_learnings():
    if os.path.exists("learnings.json"):
        try:
            return json.load(open("learnings.json")).get("top_sections", [])
        except Exception:
            return []
    return []


def choose_entry(state):
    """Next archive entry to feature: unposted, varied by section, biased to what performs."""
    archive = load_archive()
    recent_sections = state.get("recent_sections", [])[-5:]
    unposted = [e for e in archive if e["route"] not in state["posted_lore"]]
    if not unposted:
        state["posted_lore"].clear(); unposted = archive
    varied = [e for e in unposted if e.get("section") not in recent_sections]
    pool = varied or unposted
    top = load_learnings()
    if top:
        preferred = [e for e in pool if e.get("section") in top]
        pool = preferred or pool
    return pool[int(time.time()) % len(pool)]


def lore_post(state):
    entry = choose_entry(state)
    url = SITE_URL + entry["route"]
    prompt = (
        "You are creating an Instagram carousel that teases a specific entry in "
        "the ALLOCCULT archive. Base it ONLY on this real entry:\n"
        f"Title: {entry['title']}\n"
        f"Section: {entry['section']}\n"
        f"Description: {entry['description']}\n"
        f"Keywords: {', '.join(entry['keywords'])}\n\n"
        "Return ONLY JSON, no markdown fences, with these keys:\n"
        "hook: arresting title, max 7 words, intriguing but true\n"
        "symbol: exactly one character chosen from \u2609 \u263D \u263F "
        "\u2640 \u2642 \u2643 \u2644 \u2726\n"
        "slides: list of exactly 4 objects, each with heading (max 4 words) and "
        "body (18-28 words, ONE striking historically accurate fact drawn from "
        "this topic, a specific name, date or detail, short punchy sentences)\n"
        "caption: 80-120 words, atmospheric, ending exactly with: "
        f"Read the full entry \u2014 {url}, link in bio.\n"
        "hashtags: exactly 12 hashtags, space-separated, lowercase with #, mixing "
        "niche and broad occult tags")
    data = claude_json(prompt, BRAND)
    outdir = f"slides/{int(time.time())}"
    os.makedirs(outdir, exist_ok=True)
    paths = render_slides(data["hook"], data["slides"][:4], outdir,
                          data.get("symbol", "\u2726"), entry["title"])
    git_push(paths, f"Slides: {entry['title'][:50]}")
    urls = [f"{REPO_RAW}/{p}" for p in paths]
    pid = publish_carousel(urls, data["caption"] + "\n.\n.\n" + data["hashtags"])
    record_published(pid, "lore", entry["route"], entry.get("section", ""))
    state["posted_lore"].append(entry["route"])
    state.setdefault("recent_sections", []).append(entry.get("section", ""))
    state["recent_sections"] = state["recent_sections"][-8:]
    print("Lore post:", entry["title"], "->", url)

def product_post(state):
    products = fetch_products()
    if not products:
        return lore_post(state)
    p = pick(products, state["posted_products"], lambda x: x["id"])
    caption = claude(
        f"Instagram caption for a product carousel.\nProduct: {p['title']} "
        f"(from {p['price']}). Description: {p['body']}\n"
        "One line of true esoteric context on the symbol, one quiet line on the "
        "piece itself, then: Available in our Etsy shop \u2014 link in bio. "
        "Max 90 words, then 10 niche hashtags.", BRAND, 700)
    urls = p["images"]
    if len(urls) == 1:
        ig = os.environ["IG_USER_ID"]
        c = graph_post(f"{ig}/media", {"image_url": urls[0], "caption": caption})
        wait_ready(c["id"])
        r = graph_post(f"{ig}/media_publish", {"creation_id": c["id"]})
        pid = r.get("id")
    else:
        pid = publish_carousel(urls, caption)
    record_published(pid, "product", p["title"], "Product")
    state["posted_products"].append(p["id"])
    print("Product post:", p["title"])

def posting_switches():
    """posting.json — on/off switches committed in the repo (see its _help)."""
    defaults = {"carousels": True, "reels": True, "products": True}
    try:
        return {**defaults, **json.load(open("posting.json"))}
    except (OSError, ValueError):
        return defaults


DRAFTS = "drafts"
REVIEW_ROUNDS = 3


def _drafts():
    import glob
    return [(p, json.load(open(p))) for p in sorted(glob.glob(f"{DRAFTS}/*/draft.json"))]


def _save(path, draft):
    json.dump(draft, open(path, "w"), indent=2, ensure_ascii=False)


def new_draft(state):
    """Claude writes a carousel for the next archive entry → drafts/NNN-slug/draft.json."""
    import re
    from carousel_ai import write_draft
    from site_source import page_text
    entry = choose_entry(state)
    recent = [d["title"] for _, d in _drafts()][-10:]
    print(f"Writing a carousel for: {entry['title']} ({entry['route']})")
    draft = write_draft(entry, page_text(entry["route"]), recent)
    n = len(_drafts()) + 1
    slug = re.sub(r"[^a-z0-9]+", "-", entry["title"].lower()).strip("-")[:40]
    draft = {"id": f"{n:03d}-{slug}", "status": "draft", **draft}
    path = f"{DRAFTS}/{draft['id']}/draft.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _save(path, draft)
    return path, draft


def review_draft(path, draft):
    """Render → Claude review → fix → repeat. Marks the draft approved or rejected."""
    from carousel import render
    from carousel_ai import apply_fixes, review
    from site_source import page_text
    source = page_text(draft["route"])
    folder = os.path.dirname(path)
    log = draft.setdefault("review_log", [])
    for rnd in range(1, REVIEW_ROUNDS + 1):
        render(folder)
        draft = json.load(open(path))
        log = draft.setdefault("review_log", log)
        slides = [os.path.join(folder, f) for f in draft["slide_files"]]
        verdict = review(draft, slides, source)
        print(f"Review round {rnd}: {'APPROVED' if verdict['approved'] else 'changes needed'} — {verdict['summary']}")
        if verdict["approved"]:
            draft["status"] = "approved"
            log.append({"round": rnd, "approved": True, "summary": verdict["summary"]})
            _save(path, draft)
            return True
        changes = apply_fixes(draft, verdict)
        for c in changes:
            print("  fix:", c)
        log.append({"round": rnd, "approved": False, "summary": verdict["summary"], "fixes": changes})
        _save(path, draft)
        if not changes:
            break                                  # nothing actionable — don't loop
    draft["status"] = "rejected"
    _save(path, draft)
    print(f"{draft['id']} did not pass review — it will not be posted.")
    return False


def prepare_carousel(state):
    """Make sure an approved draft is ready: review a pending one, or write and review a new one."""
    drafts = _drafts()
    if any(d.get("status") == "approved" for _, d in drafts):
        return True
    pending = [(p, d) for p, d in drafts if d.get("status") == "draft"]
    path, draft = pending[0] if pending else new_draft(state)
    return review_draft(path, draft)


def post_approved_draft(state):
    """Publish the oldest approved draft. Returns True if one posted."""
    from carousel import caption_for
    for path, draft in _drafts():
        if draft.get("status") != "approved":
            continue
        folder = os.path.dirname(path)
        files = [os.path.join(folder, f) for f in draft.get("slide_files") or []]
        if not files or not all(os.path.exists(f) for f in files):
            print(f"{draft['id']} is approved but not rendered — skipping.")
            continue
        git_push(files + [path], f"Carousel slides: {draft['id']}")   # images must be public first
        pid = publish_carousel([f"{REPO_RAW}/{f}" for f in files], caption_for(draft))
        record_published(pid, "lore", draft["route"], draft.get("section", ""))
        draft.update(status="posted", media_id=pid, posted_at=int(time.time()))
        _save(path, draft)
        state["posted_lore"].append(draft["route"])
        state.setdefault("recent_sections", []).append(draft.get("section", ""))
        state["recent_sections"] = state["recent_sections"][-8:]
        print(f"Posted {draft['id']}: {draft['title']}")
        return True
    return False


def main():
    prepare_only = "--prepare" in sys.argv
    switches = posting_switches()
    if not switches["carousels"] and not prepare_only:
        print("Carousel posting is paused (posting.json: carousels=false).")
        return
    state = load_state()
    # Every carousel is reviewed by Claude (facts, images, legibility) before it
    # can post; one that fails review is never published.
    if not prepare_carousel(state):
        print("No carousel passed review today — nothing posted.")
        return
    if prepare_only:
        print("Prepared and approved; not posting (--prepare).")
        return
    if post_approved_draft(state):
        state["counter"] += 1
        save_state(state)

if __name__ == "__main__":
    main()

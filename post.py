#!/usr/bin/env python3
"""ALLOCCULT Instagram Automation v3 — bold minimal carousels."""

import json, os, sys, time, subprocess, urllib.request, urllib.parse

STORE_URL = "https://alloccult.store"
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

BRAND = ("You write for ALLOCCULT (alloccult.com, 'The Forbidden Library of "
         "Esoteric Knowledge' — an archive of 10,000+ esoteric texts, symbols, "
         "rituals and traditions; shop: alloccult.store). Voice: erudite, "
         "atmospheric, historically accurate, never campy. No emojis except "
         "rarely \u2609 \u263D. Hashtags: niche and relevant.")

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
    subprocess.run(["git", "-c", "user.name=alloccult-bot",
                    "-c", "user.email=bot@alloccult.com",
                    "commit", "-m", msg], check=True)
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

def fetch_products():
    data = http_json(f"{STORE_URL}/products.json?limit=250")
    out = []
    for p in data.get("products", []):
        if p.get("images"):
            out.append({"id": p["id"], "title": p["title"],
                        "images": [i["src"] for i in p["images"]][:5],
                        "price": p["variants"][0]["price"] if p.get("variants") else None,
                        "body": (p.get("body_html") or "")[:500]})
    return out

def pick(items, posted, keyfn):
    fresh = [i for i in items if keyfn(i) not in posted]
    if not fresh:
        posted.clear()
        fresh = items
    return fresh[int(time.time()) % len(fresh)]

def lore_post(state):
    archive = load_archive()
    entry = pick(archive, state["posted_lore"], lambda e: e["route"])
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
        "hashtags: 10-12 niche hashtags space-separated")
    data = claude_json(prompt, BRAND)
    outdir = f"slides/{int(time.time())}"
    os.makedirs(outdir, exist_ok=True)
    paths = render_slides(data["hook"], data["slides"][:4], outdir,
                          data.get("symbol", "\u2726"), entry["title"])
    git_push(paths, f"Slides: {entry['title'][:50]}")
    urls = [f"{REPO_RAW}/{p}" for p in paths]
    publish_carousel(urls, data["caption"] + "\n.\n.\n" + data["hashtags"])
    state["posted_lore"].append(entry["route"])
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
        "piece itself, then: Available at alloccult.store \u2014 link in bio. "
        "Max 90 words, then 10 niche hashtags.", BRAND, 700)
    urls = p["images"]
    if len(urls) == 1:
        ig = os.environ["IG_USER_ID"]
        c = graph_post(f"{ig}/media", {"image_url": urls[0], "caption": caption})
        wait_ready(c["id"])
        graph_post(f"{ig}/media_publish", {"creation_id": c["id"]})
    else:
        publish_carousel(urls, caption)
    state["posted_products"].append(p["id"])
    print("Product post:", p["title"])

def main():
    state = load_state()
    if state["counter"] % PRODUCT_EVERY_N == PRODUCT_EVERY_N - 1:
        product_post(state)
    else:
        lore_post(state)
    state["counter"] += 1
    save_state(state)

if __name__ == "__main__":
    main()

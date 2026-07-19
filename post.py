#!/usr/bin/env python3
"""
ALLOCCULT Instagram Automation v2 — carousel edition
- 3 of 4 posts: designed lore carousels (black/gold slides) on esoteric topics,
  driving readers to alloccult.com
- every 4th post: product carousel from alloccult.store
Secrets: IG_USER_ID, IG_ACCESS_TOKEN, ANTHROPIC_API_KEY
"""

import json, os, sys, time, subprocess, urllib.request, urllib.parse

STORE_URL = "https://alloccult.store"
SITE_URL = "alloccult.com"
REPO_RAW = "https://raw.githubusercontent.com/sprmerchandise-ship-it/alloccult-ig/main"
PRODUCT_EVERY_N = 4
STATE_FILE = "state.json"
CLAUDE_MODEL = "claude-sonnet-4-6"
GRAPH = "https://graph.facebook.com/v21.0"
W, H = 1080, 1350

TOPICS = [
    "The Key of Solomon and its planetary pentacles",
    "Enochian: the angelic language of John Dee and Edward Kelley",
    "The Emerald Tablet and 'as above, so below'",
    "Agrippa's Three Books of Occult Philosophy",
    "The Picatrix: astrological magic of medieval Arabia",
    "Sigil creation: from Austin Osman Spare to chaos magic",
    "The Lesser Banishing Ritual of the Pentagram",
    "Goetia: the 72 spirits of the Ars Goetia",
    "The Tree of Life in Hermetic Kabbalah",
    "Alchemy's stages: nigredo, albedo, citrinitas, rubedo",
    "The Rosicrucian manifestos and the invisible college",
    "Tarot's Major Arcana as an initiatory journey",
    "The Book of Abramelin and the Holy Guardian Angel",
    "Angel numbers: history behind the modern practice",
    "The Sworn Book of Honorius, oldest surviving grimoire",
    "Planetary hours and timing in ritual magic",
    "The Hermetic Order of the Golden Dawn's founding cipher",
    "Scrying: crystal, mirror and water divination",
    "The Sator Square: the oldest magic word puzzle",
    "Abracadabra: the healing amulet of Serenus Sammonicus",
    "The four classical elements and their elementals",
    "Necronomicon: the grimoire that never existed",
    "The Black Books of Norwegian folk magic",
    "Hekate: goddess of crossroads and keys",
    "The Corpus Hermeticum's journey to Renaissance Florence",
    "Grimorium Verum and the tools of the art",
    "Astral projection in Theosophy and beyond",
    "The Seal of Solomon: hexagram in magical tradition",
    "Kabbalistic gematria and hidden numbers in words",
    "The witch's familiar in early modern trial records",
    "John Dee's obsidian mirror and shew-stones",
    "The Long Lost Friend: Pennsylvania Dutch braucherei",
    "Eliphas Levi and the Baphomet of Mendes",
    "The Sixth and Seventh Books of Moses",
    "Runes: from Elder Futhark to divination",
    "The evil eye and apotropaic charms across cultures",
    "Palmistry's map: mounts, lines and meaning",
    "The Chymical Wedding of Christian Rosenkreutz",
    "Solomon's brazen vessel and the sealed spirits",
    "Thelema: Crowley's Book of the Law",
    "The Hand of Glory in European folk magic",
    "Mercurius: the trickster spirit of alchemy",
    "Votive tablets and curse tablets of antiquity",
    "The Zohar and the radiance of hidden meaning",
    "Geomancy: divination by earth and sixteen figures",
    "The magic circle: why magicians stand inside",
    "Talismans versus amulets: the crucial difference",
    "The Papyri Graecae Magicae: spells of Greco-Roman Egypt",
]

# ---------------- helpers ----------------

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
    txt = "".join(b["text"] for b in resp["content"] if b["type"] == "text")
    return txt.strip()

def claude_json(prompt, system):
    raw = claude(prompt, system).replace("```json", "").replace("```", "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])

BRAND = ("You write for ALLOCCULT (alloccult.com, 'The Forbidden Library of "
         "Esoteric Knowledge' — an archive of 10,000+ esoteric texts, symbols, "
         "rituals and traditions; shop: alloccult.store). Voice: erudite, "
         "atmospheric, historically accurate, never campy. No emojis except "
         "rarely \u2609 \u263D. Hashtags: niche and relevant.")

# ---------------- slide rendering ----------------

def render_slides(hook, slides, outdir):
    from PIL import Image, ImageDraw, ImageFont

    def font(path, size, bold=False):
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_axes([700 if bold else 400])
        except Exception:
            pass
        return f

    HEAD, BODY = "fonts/Cinzel.ttf", "fonts/EBGaramond.ttf"
    GOLD, BONE, BG = (201, 168, 106), (232, 226, 214), (11, 10, 8)

    def wrap(draw, text, fnt, maxw):
        words, lines, cur = text.split(), [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if draw.textlength(t, font=fnt) <= maxw:
                cur = t
            else:
                lines.append(cur); cur = w_
        if cur: lines.append(cur)
        return lines

    def base():
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([40, 40, W - 40, H - 40], outline=GOLD, width=3)
        d.rectangle([52, 52, W - 52, H - 52], outline=GOLD, width=1)
        d.text((W / 2, 95), "A L L O C C U L T", font=font(HEAD, 34, True),
               fill=GOLD, anchor="mm")
        d.text((W / 2, H - 95), "The Forbidden Library",
               font=font(BODY, 30), fill=GOLD, anchor="mm")
        return img, d

    paths = []

    def save(img, i):
        p = os.path.join(outdir, f"{i:02d}.jpg")
        img.save(p, "JPEG", quality=90)
        paths.append(p)

    # slide 1 — hook
    img, d = base()
    f = font(HEAD, 74, True)
    lines = wrap(d, hook.upper(), f, W - 220)
    y = H / 2 - (len(lines) - 1) * 48
    for ln in lines:
        d.text((W / 2, y), ln, font=f, fill=BONE, anchor="mm"); y += 96
    d.text((W / 2, H - 200), "\u2192 swipe", font=font(BODY, 34), fill=GOLD, anchor="mm")
    save(img, 1)

    # content slides
    for i, s in enumerate(slides, start=2):
        img, d = base()
        hf = font(HEAD, 46, True)
        hl = wrap(d, s["heading"].upper(), hf, W - 220)
        y = 250
        for ln in hl:
            d.text((W / 2, y), ln, font=hf, fill=GOLD, anchor="mm"); y += 62
        bf = font(BODY, 40)
        y += 40
        for ln in wrap(d, s["body"], bf, W - 240):
            d.text((W / 2, y), ln, font=bf, fill=BONE, anchor="mm"); y += 56
        save(img, i)

    # CTA slide
    img, d = base()
    d.text((W / 2, H / 2 - 120), "THE ARCHIVE IS OPEN",
           font=font(HEAD, 56, True), fill=BONE, anchor="mm")
    d.text((W / 2, H / 2 + 10), "10,000+ forbidden texts, symbols & rituals",
           font=font(BODY, 38), fill=BONE, anchor="mm")
    d.text((W / 2, H / 2 + 130), SITE_URL, font=font(HEAD, 48, True),
           fill=GOLD, anchor="mm")
    d.text((W / 2, H / 2 + 220), "link in bio", font=font(BODY, 34),
           fill=GOLD, anchor="mm")
    save(img, len(slides) + 2)
    return paths

def git_push(paths, msg):
    subprocess.run(["git", "add"] + paths, check=True)
    subprocess.run(["git", "-c", "user.name=alloccult-bot",
                    "-c", "user.email=bot@alloccult.com",
                    "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)

# ---------------- instagram ----------------

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

# ---------------- content ----------------

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
        posted.clear(); fresh = items
    return fresh[int(time.time()) % len(fresh)]

def lore_post(state):
    topic = pick(TOPICS, state["posted_lore"], lambda t: t)
    data = claude_json(
        f"Create an Instagram carousel about: {topic}\n"
        "Return ONLY JSON, no markdown fences:\n"
        '{"hook": "<arresting title, max 8 words, no clickbait-lies>",\n'
        ' "slides": [{"heading": "<max 5 words>", "body": "<40-55 words, one '
        "vivid, historically accurate idea; specific names, dates, details>\"}, "
        "... exactly 4 slides],\n"
        ' "caption": "<80-120 words, atmospheric summary that adds one detail '
        "not in the slides, ending: Full entry in the archive \u2014 "
        "alloccult.com, link in bio.>\",\n"
        ' "hashtags": "<10-12 niche hashtags space-separated>"}', BRAND)
    outdir = f"slides/{int(time.time())}"
    os.makedirs(outdir, exist_ok=True)
    paths = render_slides(data["hook"], data["slides"][:4], outdir)
    git_push(paths, f"Slides: {topic[:50]}")
    urls = [f"{REPO_RAW}/{p}" for p in paths]
    caption = data["caption"] + "\n.\n.\n" + data["hashtags"]
    publish_carousel(urls, caption)
    state["posted_lore"].append(topic)
    print("Lore post:", topic)

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
    urls = p["images"] if len(p["images"]) > 1 else p["images"]
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

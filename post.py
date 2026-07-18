#!/usr/bin/env python3
"""
ALLOCCULT Instagram Automation
Pulls products from alloccult.store (Shopify), generates captions with the
Claude API, and publishes to @all.occult via the Instagram Graph API.

Post rotation: 2 esoteric-lore posts : 1 product post (configurable below).

Required environment variables (set as GitHub Actions secrets):
  IG_USER_ID         - Instagram Business account ID
  IG_ACCESS_TOKEN    - Long-lived Meta access token
  ANTHROPIC_API_KEY  - Anthropic API key
"""

import json
import os
import sys
import time
import urllib.request

# ------------------------- Configuration -------------------------

STORE_URL = "https://alloccult.store"
PRODUCT_EVERY_N_POSTS = 3          # every 3rd post is a product post
STATE_FILE = "state.json"
CLAUDE_MODEL = "claude-sonnet-4-6"
GRAPH_API = "https://graph.facebook.com/v21.0"

BRAND_VOICE = (
    "You write Instagram captions for ALLOCCULT, a dark occult brand "
    "(alloccult.com — 'The Forbidden Library of Esoteric Knowledge', and "
    "alloccult.store — occult apparel, mugs and tote bags). Voice: mysterious, "
    "literate, reverent toward historical esoteric sources (Key of Solomon, "
    "grimoires, Hermeticism, angel numbers, astral projection). Never campy, "
    "never salesy-sounding, no emojis except at most one subtle symbol like "
    "\u2609 \u263D \u26B7. Always end with 8-12 relevant niche hashtags."
)

# ------------------------- Helpers -------------------------


def http_json(url, data=None, headers=None, method=None):
    body = None
    headers = headers or {}
    if data is not None:
        body = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def http_post_form(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


import urllib.parse  # noqa: E402


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"counter": 0, "posted_products": [], "posted_lore": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ------------------------- Content sources -------------------------


def fetch_products():
    data = http_json(f"{STORE_URL}/products.json?limit=250")
    products = []
    for p in data.get("products", []):
        if not p.get("images"):
            continue
        price = None
        if p.get("variants"):
            price = p["variants"][0].get("price")
        products.append(
            {
                "id": p["id"],
                "title": p["title"],
                "handle": p["handle"],
                "image": p["images"][0]["src"],
                "price": price,
                "tags": p.get("tags", []),
                "body": (p.get("body_html") or "")[:500],
            }
        )
    if not products:
        sys.exit("No products found in the store feed.")
    return products


def pick_unposted(items, posted_ids, key="id"):
    fresh = [i for i in items if i[key] not in posted_ids]
    if not fresh:            # everything posted once -> start a new cycle
        posted_ids.clear()
        fresh = items
    return fresh[int(time.time()) % len(fresh)]


# ------------------------- Claude caption generation -------------------------


def claude(prompt):
    resp = http_json(
        "https://api.anthropic.com/v1/messages",
        data={
            "model": CLAUDE_MODEL,
            "max_tokens": 700,
            "system": BRAND_VOICE,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
    )
    return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()


def product_caption(p):
    return claude(
        f"Write a caption for a product post.\n"
        f"Product: {p['title']}\nPrice: from {p['price']} AUD\n"
        f"Description snippet: {p['body']}\n"
        f"Weave in one line of genuine esoteric context about the symbol or "
        f"concept on the item, then a quiet call to action: 'Link in bio.' "
        f"Max 120 words before hashtags."
    )


def lore_caption(p):
    return claude(
        f"Write an educational, atmospheric lore post (NOT a product ad) about "
        f"the esoteric concept behind this artwork: '{p['title']}'. Teach the "
        f"reader something real and specific about its history or meaning in "
        f"the Western esoteric tradition. Do not mention the shop, prices, or "
        f"buying anything. Max 140 words before hashtags."
    )


# ------------------------- Instagram publishing -------------------------


def publish(image_url, caption):
    ig_user = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]

    creation = http_post_form(
        f"{GRAPH_API}/{ig_user}/media",
        {"image_url": image_url, "caption": caption, "access_token": token},
    )
    creation_id = creation.get("id")
    if not creation_id:
        sys.exit(f"Media container creation failed: {creation}")

    # give the container a moment to finish processing
    time.sleep(8)

    result = http_post_form(
        f"{GRAPH_API}/{ig_user}/media_publish",
        {"creation_id": creation_id, "access_token": token},
    )
    if "id" not in result:
        sys.exit(f"Publish failed: {result}")
    print(f"Published post {result['id']}")


# ------------------------- Main -------------------------


def main():
    state = load_state()
    products = fetch_products()

    is_product_post = state["counter"] % PRODUCT_EVERY_N_POSTS == (
        PRODUCT_EVERY_N_POSTS - 1
    )

    if is_product_post:
        p = pick_unposted(products, state["posted_products"])
        caption = product_caption(p)
        state["posted_products"].append(p["id"])
        kind = "product"
    else:
        p = pick_unposted(products, state["posted_lore"])
        caption = lore_caption(p)
        state["posted_lore"].append(p["id"])
        kind = "lore"

    print(f"Post type: {kind} | Artwork: {p['title']}")
    print(f"Caption:\n{caption}\n")

    publish(p["image"], caption)

    state["counter"] += 1
    save_state(state)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Image-led carousels, reviewed before they post.

A carousel is a draft in drafts/<id>/draft.json:

  {"id", "status": "draft" | "approved" | "posted",
   "title", "route", "section",
   "slides": [{"kicker": "PARIS · 1424", "text": "...", "image_query": "..."}],
   "caption", "hashtags": [...]}

slides[0] is the cover: its "text" is the hook; "series" (optional) is a
label above it. A closing card is added automatically: the draft's
"question" for comments when it has one, else "read the full entry". Each slide gets public-domain artwork
(museum.py; resolved choices are saved back as slide["image"] so re-renders
are stable — set "image": null to pick again, and add its key to the
slide's "reject" list so it is never picked again).

  python carousel.py render drafts/<id>     # render one draft → drafts/<id>/NN.jpg
  python carousel.py render-pending         # render every draft not yet posted

Nothing here publishes. post.py posts the oldest draft whose status is
"approved" — a person flips that after reviewing the slides.
"""
import glob, json, os, sys
from PIL import Image, ImageDraw, ImageFilter

import llm, museum
from render_reel import GOLD, PARCHMENT, DUST, _credit, contain, cover, drawable, font, sigil, wrap

W, H = 1080, 1350
BG = (9, 8, 6)
SITE = "alloccult.com"


def _art(path):
    return Image.open(path).convert("RGB") if path else None


def _text_block(d, lines, fnt, y, gap, fill):
    for ln in lines:
        d.text((W / 2, y), ln, font=fnt, fill=fill, anchor="mm")
        y += gap
    return y


def cover_slide(art, hook, credit, series=""):
    img = Image.new("RGB", (W, H), BG)
    if art:
        # Pale engravings fight the gold text: dim the art, then add a dark
        # band at the top for the wordmark and a deep gradient for the hook.
        img = Image.blend(img, cover(art, W, H), 0.62)
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        bottom = max(0, (y - H * 0.30) / (H * 0.70)) ** 0.9
        top = max(0, (140 - y) / 140)
        sd.line([(0, y), (W, y)], fill=int(250 * min(1, max(bottom, top))))
    img.paste(Image.new("RGB", (W, H), BG), (0, 0), shade)
    d = ImageDraw.Draw(img)
    d.text((W / 2, 70), "A L L O C C U L T", font=font("Cinzel", 30, 700), fill=GOLD, anchor="mm")
    f = font("Cinzel", 84, 700)
    lines = wrap(d, drawable(hook.upper(), f), f, W - 150)
    if len(lines) > 4:
        f = font("Cinzel", 68, 700)
        lines = wrap(d, drawable(hook.upper(), f), f, W - 150)
    gap = f.size + 18
    y = H - 300 - (len(lines) - 1) * gap
    if series:                                  # e.g. "THE FORBIDDEN LIBRARY · NO. 12"
        sf = font("Cinzel", 32, 700)
        sy = y - gap / 2 - 50
        label = drawable(series.upper(), sf)
        lw = d.textlength(label, font=sf)
        d.text((W / 2, sy), label, font=sf, fill=PARCHMENT, anchor="mm")
        for x0, x1 in ((W / 2 - lw / 2 - 90, W / 2 - lw / 2 - 25), (W / 2 + lw / 2 + 25, W / 2 + lw / 2 + 90)):
            d.line([(x0, sy), (x1, sy)], fill=GOLD, width=2)
    _text_block(d, lines, f, y, gap, GOLD)
    d.text((W / 2, H - 170), "swipe  →", font=font("EBGaramond", 36, 500), fill=PARCHMENT, anchor="mm")
    if credit:
        cf = font("EBGaramond", 22)
        d.text((W / 2, H - 60), _credit(d, credit, cf, W - 120), font=cf, fill=DUST, anchor="mm")
    return img


def content_slide(art, kicker, text, credit, n, total):
    img = Image.new("RGB", (W, H), BG)
    if art:
        img = Image.blend(img, cover(art, W, H).filter(ImageFilter.GaussianBlur(45)), 0.22)
    d = ImageDraw.Draw(img)
    top, box = 90, (940, 720)
    if art:
        fg = contain(art, *box)
        x, y = (W - fg.width) // 2, top + (box[1] - fg.height) // 2
        img.paste(fg, (x, y))
        d.rectangle((x - 7, y - 7, x + fg.width + 6, y + fg.height + 6), outline=GOLD, width=2)
    else:
        sigil(d, W / 2, top + box[1] / 2, 250)
    y = top + box[1] + 70
    if kicker:
        kf = font("Cinzel", 34, 700)
        d.text((W / 2, y), drawable(kicker.upper(), kf), font=kf, fill=GOLD, anchor="mm")
        y += 70
    bf = font("EBGaramond", 46, 500)
    _text_block(d, wrap(d, drawable(text, bf), bf, W - 170)[:5], bf, y, 60, PARCHMENT)
    d.text((W - 70, H - 50), f"{n} / {total}", font=font("EBGaramond", 24), fill=DUST, anchor="rm")
    if credit:
        cf = font("EBGaramond", 20)
        d.text((70, H - 50), _credit(d, credit, cf, W - 230), font=cf, fill=DUST, anchor="lm")
    return img


def question_slide(question, series=""):
    """Closing card: the question to answer in the comments, then save/share."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    sigil(d, W / 2, 300, 140)
    if series:
        d.text((W / 2, 510), drawable(series.upper(), font("Cinzel", 30, 700)),
               font=font("Cinzel", 30, 700), fill=DUST, anchor="mm")
    qf = font("Cinzel", 64, 700)
    lines = wrap(d, drawable(question, qf), qf, W - 180)
    if len(lines) > 4:
        qf = font("Cinzel", 52, 700)
        lines = wrap(d, drawable(question, qf), qf, W - 180)
    y = _text_block(d, lines, qf, 640, qf.size + 20, GOLD)
    d.text((W / 2, y + 50), "Answer in the comments", font=font("EBGaramond", 42), fill=PARCHMENT, anchor="mm")
    d.text((W / 2, y + 120), "save this  ·  send it to someone who needs it",
           font=font("EBGaramond", 34), fill=DUST, anchor="mm")
    d.text((W / 2, H - 110), SITE, font=font("Cinzel", 40, 700), fill=GOLD, anchor="mm")
    return img


def closing_slide(title, route):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    sigil(d, W / 2, 380, 170)
    d.text((W / 2, 650), "READ THE FULL ENTRY", font=font("Cinzel", 46, 700), fill=GOLD, anchor="mm")
    tf = font("Cinzel", 58, 700)
    y = _text_block(d, wrap(d, title.upper(), tf, W - 200), tf, 750, 74, PARCHMENT)
    d.text((W / 2, y + 40), "in the Forbidden Library", font=font("EBGaramond", 40), fill=PARCHMENT, anchor="mm")
    d.text((W / 2, y + 130), SITE, font=font("Cinzel", 50, 700), fill=GOLD, anchor="mm")
    d.text((W / 2, y + 200), "link in bio  ·  save this for later", font=font("EBGaramond", 32), fill=DUST, anchor="mm")
    return img


def _choose(slide, draft, used):
    """The model picks among museum candidates when it can; otherwise the first match."""
    query = slide.get("image_query") or draft["title"]
    if not llm.available():
        return museum.find_image(query, used)
    from carousel_ai import choose_image
    return choose_image(slide.get("kicker", ""), slide["text"], query, used,
                        slide.setdefault("reject", []))


def resolve_images(draft, tmp):
    """Make sure each slide has a downloadable image; returns local paths."""
    used = {s["image"]["key"] for s in draft["slides"] if s.get("image")}
    # Images a reviewer turned down stay out for good ("reject": [keys]).
    used |= {k for s in draft["slides"] for k in s.get("reject", [])}
    paths = []
    for n, s in enumerate(draft["slides"]):
        p = os.path.join(tmp, f"art{n}.jpg")
        for _ in range(6):
            if not s.get("image"):
                s["image"] = _choose(s, draft, used)
                if not s["image"]:
                    break
            used.add(s["image"]["key"])
            try:
                museum.download(s["image"]["url"], p)
                Image.open(p).verify()
                break
            except Exception as e:                         # noqa: BLE001
                print(f"  slide {n + 1}: download failed ({e}); trying another")
                s["image"] = None
        paths.append(p if s.get("image") else None)
        print(f"  slide {n + 1}: {s['image']['credit'] if s.get('image') else '(no image — sigil)'}")
    return paths


def render(draft_dir):
    import tempfile
    path = os.path.join(draft_dir, "draft.json")
    draft = json.load(open(path))
    print(f"Rendering {draft['id']}: {draft['title']}")
    for old in glob.glob(os.path.join(draft_dir, "[0-9][0-9].jpg")):
        os.remove(old)
    tmp = tempfile.mkdtemp(prefix="carousel_")
    arts = resolve_images(draft, tmp)
    # A content slide with no fitting image is dropped rather than shown as a
    # bare sigil — as long as the cover and 4 content slides remain.
    missing = [i for i, a in enumerate(arts) if i > 0 and a is None]
    if missing and len(draft["slides"]) - len(missing) >= 5:
        for i in reversed(missing):
            print(f"  dropping slide {i + 1} ({draft['slides'][i].get('kicker', '')}): no fitting image")
            del draft["slides"][i], arts[i]
    slides = draft["slides"]
    total = len(slides) + 1
    out = []
    for n, (s, a) in enumerate(zip(slides, arts)):
        credit = s["image"]["credit"] if s.get("image") and a else ""
        img = (cover_slide(_art(a), s["text"], credit, draft.get("series", "")) if n == 0 else
               content_slide(_art(a), s.get("kicker", ""), s["text"], credit, n + 1, total))
        out.append(img)
    out.append(question_slide(draft["question"], draft.get("series", ""))
               if draft.get("question") else closing_slide(draft["title"], draft["route"]))
    files = []
    for n, img in enumerate(out, start=1):
        f = os.path.join(draft_dir, f"{n:02d}.jpg")
        img.save(f, "JPEG", quality=92)
        files.append(f)
    draft["slide_files"] = [os.path.basename(f) for f in files]
    json.dump(draft, open(path, "w"), indent=2, ensure_ascii=False)
    print(f"  wrote {len(files)} slides")
    return files


def caption_for(draft):
    return draft["caption"].strip() + "\n.\n.\n" + " ".join("#" + h.lstrip("#") for h in draft["hashtags"])


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "render":
        render(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "render-pending":
        for p in sorted(glob.glob("drafts/*/draft.json")):
            if json.load(open(p)).get("status") != "posted":
                render(os.path.dirname(p))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

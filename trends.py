#!/usr/bin/env python3
"""
What's happening this week, for the weekly content plan (planner.py).

  python trends.py 2026-11-23        # writes trends/2026-11-23.json

Three free sources, each optional (a failed source is logged and skipped):

1. wikipedia — the most-read English Wikipedia articles over the last 7 days
   (Wikimedia pageviews API, no key). This is what the public is curious about
   right now: films, deaths, anniversaries, news. planner.py has the model pick
   the few with a real occult / myth / history angle.
2. calendar — the next 3 weeks of sky and folk dates, computed, not guessed:
   moon phases, solstices / equinoxes and Sun sign changes (PyEphem), Mercury
   retrograde stations, Friday the 13ths, and a curated list of folk and
   occult feast days.
3. instagram — the top recent posts under our hashtags and the competitors'
   breakout posts, from competitors/scan.json (written by competitor_scan.py).
"""
import datetime as dt, json, os, sys, urllib.request
from collections import Counter

UA = "alloccult-bot/1.0 (https://alloccult.com)"
SKIP_PREFIXES = ("Special:", "Wikipedia:", "Portal:", "File:", "Help:", "Category:",
                 "Template:", "Talk:", "User:", "Main_Page", "-")
SKIP_WORDS = ("xnxx", "xvideos", "pornhub", "xhamster", ".xxx", "onlyfans", "cleavage")

# (month, day, name, one line of what it is). Only well-attested dates.
FOLK_DAYS = [
    (1, 5, "Twelfth Night", "end of the Twelve Days; wassailing and the Lord of Misrule"),
    (1, 6, "Epiphany", "the Magi; chalking the door and blessing the house"),
    (2, 1, "Imbolc", "Gaelic feast of St Brigid, first stirrings of spring"),
    (2, 2, "Candlemas", "candles blessed; weather divination"),
    (3, 20, "Ostara (spring equinox, approx.)", "modern pagan equinox festival"),
    (4, 30, "Walpurgis Night", "witches gather on the Brocken, in German folklore"),
    (5, 1, "Beltane / May Day", "Gaelic fire festival, start of summer"),
    (6, 23, "St John's Eve", "midsummer fires, fern seed and herb gathering"),
    (8, 1, "Lughnasadh / Lammas", "first harvest; the loaf-mass"),
    (10, 31, "Samhain / Halloween", "the Gaelic year turns; the dead walk"),
    (11, 1, "All Saints / Día de Muertos begins", "feast of the saints; Mexican Day of the Dead"),
    (11, 2, "All Souls' Day", "prayers for the dead; soul cakes"),
    (11, 25, "St Catherine's Day", "the wheel saint; spinsters' divination"),
    (11, 30, "St Andrew's Eve", "love divination across Eastern Europe"),
    (12, 5, "Krampusnacht", "Krampus comes for the wicked, in Alpine folklore"),
    (12, 6, "St Nicholas' Day", "gifts in shoes; the saint and his dark companion"),
    (12, 13, "St Lucy's Day", "light in the longest dark; Lussi and the wild night"),
    (12, 17, "Saturnalia begins", "Roman feast of Saturn; masters serve slaves"),
    (12, 24, "Mōdraniht", "'Mothers' Night', named by Bede for the pagan English"),
    (12, 25, "Christmas / Yule", "the Twelve Days begin; the Wild Hunt rides"),
    (12, 31, "Hogmanay / New Year's Eve", "first-footing; omens for the year"),
]
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
         "Sagittarius", "Capricorn", "Aquarius", "Pisces"]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- Wikipedia

def wikipedia(today, days=7, keep=400):
    views = Counter()
    for back in range(1, days + 1):
        d = today - dt.timedelta(days=back)
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/"
               f"all-access/{d:%Y/%m/%d}")
        try:
            arts = _get(url)["items"][0]["articles"]
        except Exception as e:                      # noqa: BLE001 — day not published yet etc.
            print(f"  wikipedia {d}: skipped ({e})")
            continue
        for a in arts:
            t = a["article"]
            if not t.startswith(SKIP_PREFIXES) and not any(w in t.lower() for w in SKIP_WORDS):
                views[t] += a["views"]
    return [{"title": t.replace("_", " "), "views": v} for t, v in views.most_common(keep)]


# ---------------------------------------------------------------- calendar

def _ecl_lon(body, when):
    import ephem
    body.compute(when)
    # Apparent position in the coordinates of the date (tropical zodiac), not J2000.
    eq = ephem.Equatorial(body.ra, body.dec, epoch=when)
    return float(ephem.Ecliptic(eq, epoch=when).lon) * 57.29577951308232


def _when(d):
    """ephem date → 'YYYY-MM-DD HH:MM UTC'."""
    return d.datetime().strftime("%Y-%m-%d %H:%M UTC")


def _refine(fn, lo, hi):
    """Bisect to the minute where fn(t) changes value between lo and hi."""
    import ephem
    a = fn(lo)
    while hi - lo > ephem.minute:
        mid = ephem.Date((lo + hi) / 2)
        lo, hi = (mid, hi) if fn(mid) == a else (lo, mid)
    return ephem.Date(hi)


def calendar(today, days=21):
    import ephem
    start, end = ephem.Date(today), ephem.Date(today + dt.timedelta(days=days))
    events = []
    for name, fn in (("New Moon", ephem.next_new_moon), ("First Quarter Moon", ephem.next_first_quarter_moon),
                     ("Full Moon", ephem.next_full_moon), ("Last Quarter Moon", ephem.next_last_quarter_moon)):
        d = fn(start)
        while d < end:
            moon = ephem.Moon(d)
            sign = SIGNS[int(_ecl_lon(moon, d) // 30)]
            events.append({"when": _when(d), "event": f"{name} in {sign}"})
            d = fn(ephem.Date(d + 1))
    for name, fn in (("Solstice", ephem.next_solstice), ("Equinox", ephem.next_equinox)):
        d = fn(start)
        if d < end:
            events.append({"when": _when(d), "event": name})
    # Sun sign changes and Mercury stations: step hourly through the window.
    sun, merc = ephem.Sun(), ephem.Mercury()
    prev_sign, prev_dir, prev_lon = None, None, None
    t = start
    while t < end:
        s = int(_ecl_lon(sun, t) // 30)
        if prev_sign is not None and s != prev_sign:
            at = _refine(lambda x: int(_ecl_lon(sun, x) // 30), ephem.Date(t - ephem.hour * 6), t)
            events.append({"when": _when(at), "event": f"Sun enters {SIGNS[s]} ({SIGNS[s]} season begins)"})
        prev_sign = s
        lon = _ecl_lon(merc, t)
        if prev_lon is not None:
            step = (lon - prev_lon + 540) % 360 - 180
            direction = "direct" if step >= 0 else "retrograde"
            if prev_dir and direction != prev_dir:
                events.append({"when": _when(t), "event": f"Mercury stations {direction} in {SIGNS[int(lon // 30)]}"})
            prev_dir = direction
        prev_lon = lon
        t = ephem.Date(t + ephem.hour * 6)
    # Folk days and Friday the 13ths.
    for back in range(days):
        d = today + dt.timedelta(days=back)
        for m, day, name, what in FOLK_DAYS:
            if (d.month, d.day) == (m, day):
                events.append({"when": f"{d:%Y-%m-%d}", "event": f"{name}: {what}"})
        if d.day == 13 and d.weekday() == 4:
            events.append({"when": f"{d:%Y-%m-%d}", "event": "Friday the 13th"})
    return sorted(events, key=lambda e: e["when"])


# ---------------------------------------------------------------- Instagram

def instagram(scan_path="competitors/scan.json", top=15):
    try:
        scan = json.load(open(scan_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"  instagram: skipped ({e})")
        return {}
    def slim(p):
        return {"handle": p.get("handle"), "format": p.get("format"), "date": (p.get("timestamp") or "")[:10],
                "likes": p.get("likes"), "comments": p.get("comments"),
                "x_median": p.get("vs_account_median"),
                "caption": " ".join((p.get("caption") or "").split())[:180]}
    seen, tags = set(), []
    for tag, posts in (scan.get("hashtags") or {}).items():
        for p in posts:
            if p["permalink"] not in seen:
                seen.add(p["permalink"])
                tags.append({"tag": tag, **slim(p)})
    tags.sort(key=lambda p: -((p["likes"] or 0) + (p["comments"] or 0)))
    return {"format_summary": scan.get("format_summary"),
            "hashtag_top": tags[:top],
            "breakouts": [slim(p) for p in scan.get("breakout_posts", [])[:10]]}


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    today = dt.date.fromisoformat(date)
    out = {"date": date}
    print("Wikipedia top articles...")
    out["wikipedia"] = wikipedia(today)
    print(f"  {len(out['wikipedia'])} articles")
    print("Calendar...")
    try:
        out["calendar"] = calendar(today)
    except ImportError:
        print("  skipped (pip install ephem)")
        out["calendar"] = []
    print(f"  {len(out['calendar'])} dates")
    out["instagram"] = instagram()
    os.makedirs("trends", exist_ok=True)
    path = f"trends/{date}.json"
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

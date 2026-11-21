#!/usr/bin/env python3
"""
The week's content plan: 4 Reels + 3 carousels, chosen from what's trending.

  python planner.py 2026-11-23      # needs trends/2026-11-23.json (trends.py)

Writes:
  plan/2026-11-23.json   seven dated items (Mon–Sun) that post.py and
                         compose_posts.py turn into carousels and Reels
  and appends "## 6. This week's plan" to reports/2026-11-23.md if it exists.

Five pillars (see PILLARS). The archive at alloccult.com is one source among
many: an item links to an archive page only when one really fits.
Never plans giveaways, contests or product promotions.

Needs an AI key (see llm.py).
"""
import datetime as dt, glob, json, os, re, sys

import llm
from carousel_ai import VOICE

# Weekday (Monday = 0) → format. Reels lead while the account is small: Instagram
# shows them to non-followers, and our October Reels reached 77–116 accounts
# where carousels reached 0–1. Carousels win per follower (2.6× in our niche),
# so shift toward them once the account has a following (insights.json).
SLOTS = ["reel", "carousel", "reel", "carousel", "reel", "reel", "carousel"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

PILLARS = {
    "forbidden_library": "The Forbidden Library — a numbered series on one real manuscript, "
        "object or archive with a mystery (Voynich, Codex Gigas, John Dee's obsidian mirror, the "
        "Copiale cipher…). Where it is now (institution, shelfmark), what it is, why it is strange; "
        "hold the strangest fact back for the last slides.",
    "behind_the_trend": "Occult behind the trend — take something people are reading about this "
        "week (a film, series, game, anniversary, discovery) and show the real occult, mythic or "
        "historical thread behind it. Only connections that are documented; never claim a creator "
        "intended something unless they said so.",
    "cosmic_calendar": "Cosmic calendar — a date in the coming days (moon phase, Sun sign change, "
        "solstice, a folk feast). The folklore, ritual and history attached to it, with the exact "
        "date/time from the calendar. Posts on or just before the date.",
    "myth_vs_history": "Myth vs history — 4–7 popular beliefs about magic, witches or occult "
        "history set against what the sources actually say (e.g. Victorian inventions sold as "
        "ancient). Each with the real date or source.",
    "find_yours": "Find yours — a lookup list from one named historical source (a grimoire, "
        "almanac, herbal, lapidary): e.g. each birth month's stone in a 1500s lapidary, each zodiac "
        "sign's planetary ruler and herb in Culpeper. Ends: comment yours.",
}

ITEM = {"type": "object", "additionalProperties": False, "required": [
    "day", "format", "pillar", "title", "hook", "angle", "why_now", "facts", "related_route", "question"],
    "properties": {
        "day": {"type": "string"},
        "format": {"type": "string", "enum": ["carousel", "reel"]},
        "pillar": {"type": "string", "enum": list(PILLARS)},
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "angle": {"type": "string"},
        "why_now": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "related_route": {"type": "string"},
        "question": {"type": "string"},
    }}
PLAN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["theme", "items"],
               "properties": {"theme": {"type": "string"}, "items": {"type": "array", "items": ITEM}}}
PICKS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["picks"],
                "properties": {"picks": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["title", "angle"],
                    "properties": {"title": {"type": "string"}, "angle": {"type": "string"}}}}}}


def trending_picks(wiki):
    """The few most-read Wikipedia articles with a real occult / myth / history angle."""
    if not wiki:
        return []
    titles = "\n".join(a["title"] for a in wiki[:400])
    prompt = f"""These are this week's most-read English Wikipedia articles, most-read
first. Pick up to 10 that give an occult / esoteric / mythology / folklore /
history-of-magic account a genuine, historically grounded angle — e.g. a film
or series about witches, a saint's feast, an anniversary, an archaeological
find, a figure with real occult connections.

Leave out: recent deaths, tragedies, crimes, disasters, elections and
politics, and living people's private lives. A weak or forced link is worse
than none; return fewer picks rather than stretch.

"angle": one sentence on the real connection.

ARTICLES:
{titles}"""
    try:
        return llm.ask_json(VOICE, prompt, PICKS_SCHEMA, model=llm.FAST_MODEL)["picks"][:10]
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"  trending picks failed ({e}); planning without them")
        return []


def recent_titles(weeks=4):
    """Titles from the last few plans, so nothing repeats."""
    out = []
    for p in sorted(glob.glob("plan/????-??-??.json"))[-weeks:]:
        out += [i["title"] for i in json.load(open(p))["items"]]
    return out


def carousel_pillars():
    """This week's carousel pillars: the next ones in a fixed rotation, so all
    five come round every ~2 weeks."""
    order = list(PILLARS)
    done = sum(i["format"] == "carousel" for p in glob.glob("plan/????-??-??.json")
               for i in json.load(open(p))["items"])
    n = SLOTS.count("carousel")
    return [order[(done + k) % len(order)] for k in range(n)]


def next_series_no():
    nos = []
    for p in glob.glob("plan/????-??-??.json"):
        nos += [i.get("series_no", 0) for i in json.load(open(p))["items"]]
    return max(nos, default=0) + 1


def plan_prompt(start, trends, picks, routes, recent, series_no, analysis, pillars_now):
    slots = "\n".join(f"- {DAYS[d.weekday()]} {d:%d %b}: {SLOTS[d.weekday()]}" for d in _days(start))
    pillars = "\n".join(f"- {k}: {v}" for k, v in PILLARS.items())
    ig = trends.get("instagram") or {}
    return f"""Plan the next 7 days of posts for @all.occult (Instagram), one per day, in this order:
{slots}

PILLARS:
{pillars}

Rules:
- The 3 carousels use these pillars, one each, on whichever carousel day fits
  best: {', '.join(pillars_now)}.
- The 4 Reels are fast countdowns ("3 objects…", "5 signs…") from any pillar
  except find_yours. They are how new people find us, so pick the most
  shareable subjects: our best Reels so far were about vampires, gematria and
  the Goetia's demons.
- A forbidden_library carousel is "No. {series_no}" in its series: put it in the title.
- behind_the_trend (when used) must come from TRENDING below; if nothing there is strong,
  use the calendar or a hashtag-feed topic instead and say so in why_now.
- cosmic_calendar (when used) uses a date from CALENDAR and goes on that day or 1–2 days
  before it. Copy the date/time exactly.
- Hooks follow what works in our niche: a startling, specific, true claim, or
  a withheld reveal ("Yale has a secret. And it's been locked behind marble
  walls for 60 years" got 292k likes). Max 9 words. No questions as hooks.
- "facts": 5–8 specific, checkable facts the post will use — names, dates,
  places, shelfmarks, primary sources. Nothing you are not sure of.
- "question": the closing question, one people can actually answer in a word
  or a number (e.g. "Which month are you?"), not a vague mood question.
- "related_route": an archive route from the list ONLY if it is closely about
  the same subject, else "".
- Never plan giveaways, contests, discounts or product promotions.
- Don't repeat these recent posts: {'; '.join(recent) or 'none'}.

TRENDING (most-read Wikipedia articles with an angle):
{json.dumps(picks, ensure_ascii=False) or 'none this week'}

CALENDAR (next 3 weeks, UTC):
{json.dumps(trends.get('calendar', [])[:30], ensure_ascii=False)}

WHAT'S WORKING ON INSTAGRAM (top hashtag posts, competitor breakouts):
{json.dumps({'hashtag_top': ig.get('hashtag_top', [])[:8], 'breakouts': ig.get('breakouts', [])[:6]}, ensure_ascii=False)[:5000]}

THIS WEEK'S COMPETITOR ANALYSIS (summary):
{analysis[:2500] or '(none)'}

ARCHIVE ROUTES (route — title):
{routes}"""


def _days(start):
    return [start + dt.timedelta(days=n) for n in range(7)]


def validate(items, start, routes, pillars_now):
    problems = []
    if len(items) != 7:
        problems.append(f"expected 7 items, got {len(items)}")
    for i, d in zip(items, _days(start)):
        i["format"] = SLOTS[d.weekday()]
    carousels = [i for i in items[:7] if i["format"] == "carousel"]
    if sorted(i.get("pillar") for i in carousels) != sorted(pillars_now):
        problems.append(f"the carousels must use these pillars once each: {', '.join(pillars_now)}")
    for i, d in zip(items, _days(start)):
        n = d.weekday()
        if i.get("related_route") and i["related_route"] not in routes:
            i["related_route"] = ""
        if len(i.get("facts") or []) < 4:
            problems.append(f"{DAYS[n]}: needs 5–8 facts")
        if i["format"] == "reel" and i.get("pillar") == "find_yours":
            problems.append(f"{DAYS[n]}: a Reel can't be find_yours")
    return problems


def report_section(plan):
    lines = [f"## 6. This week's plan\n\n**Theme:** {plan['theme']}\n"]
    for i in plan["items"]:
        lines.append(f"### {i['day']} {i['date']} · {i['format']} · {i['pillar']} — \"{i['title']}\"\n"
                     f"- Hook: {i['hook']}\n- Angle: {i['angle']}\n- Why now: {i['why_now']}\n"
                     f"- Closing question: {i['question']}\n"
                     + (f"- Archive: alloccult.com{i['related_route']}\n" if i["related_route"] else ""))
    return "\n".join(lines)


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    path = f"trends/{date}.json"
    trends = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    # The plan covers the 7 days from today (the weekly run is on Mondays).
    start = dt.date.fromisoformat(date)
    archive = json.load(open("archive_index.json", encoding="utf-8"))
    routes = {e["route"] for e in archive}
    route_list = "\n".join(f"{e['route']} — {e['title']}" for e in archive)
    report = f"reports/{date}.md"
    analysis = ""
    if os.path.exists(report):
        m = re.search(r"^## *1\..*?(?=^## *2\.|\Z)", open(report, encoding="utf-8").read(), re.S | re.M)
        analysis = m.group(0) if m else ""

    print("Picking trending topics...")
    picks = trending_picks(trends.get("wikipedia"))
    for p in picks:
        print(f"  {p['title']}: {p['angle']}")
    series_no = next_series_no()
    pillars_now = carousel_pillars()
    prompt = plan_prompt(start, trends, picks, route_list, recent_titles(), series_no, analysis, pillars_now)
    for attempt in range(2):
        try:
            plan = llm.ask_json(VOICE, prompt, PLAN_SCHEMA)
            problems = validate(plan["items"], start, routes, pillars_now)
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            plan, problems = None, [f"response was not valid plan JSON ({e})"]
        if not problems:
            break
        print("Plan problems:", *problems, sep="\n  ")
        prompt += "\n\nYour previous answer had these problems, fix them:\n" + "\n".join(problems)
    else:
        if not plan or len(plan.get("items", [])) < 7:
            sys.exit("The model could not produce a valid plan.")
    for n, (i, d) in enumerate(zip(plan["items"], _days(start))):
        i.update(id=f"{start}-{n + 1}", day=DAYS[d.weekday()], date=f"{d}")
        if i["pillar"] == "forbidden_library" and i["format"] == "carousel":
            i["series_no"] = series_no
    plan = {"week": f"{start}", "made": date, "theme": plan["theme"], "trending": picks,
            "items": plan["items"][:7]}
    os.makedirs("plan", exist_ok=True)
    out = f"plan/{start}.json"
    json.dump(plan, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {out}:")
    for i in plan["items"]:
        print(f"  {i['day'][:3]} {i['format']:8} {i['pillar']:17} {i['title']}")
    if os.path.exists(report):
        text = open(report, encoding="utf-8").read()
        text = re.sub(r"^## *6\..*?(?=^## *7\.|\Z)", "", text, flags=re.S | re.M)
        parts = re.split(r"(?=^## *7\.)", text, maxsplit=1, flags=re.M)
        text = parts[0].rstrip() + "\n\n" + report_section(plan) + "\n\n" + (parts[1] if len(parts) > 1 else "")
        open(report, "w", encoding="utf-8").write(text.rstrip() + "\n")


if __name__ == "__main__":
    main()

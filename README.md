# ALLOCCULT Instagram Automation

Automatically posts to **@all.occult** on a schedule: every week, 4 Reels
and 3 carousels planned from what's trending (see "The weekly plan" below),
written, illustrated and fact-checked by an AI model (see "AI model"). Product
posts from the Etsy shop (alloccult.etsy.com) can be switched on in
`posting.json`.

## One-time setup

### 1. Instagram / Meta side (~20 min)

1. **Convert @all.occult to a Professional account** (Business or Creator):
   Instagram app → Settings → Account type and tools → Switch to professional
   account.
2. **Link it to a Facebook Page** (create a blank "ALLOCCULT" Page if you don't
   have one): Instagram → Settings → Business tools and controls → Connect a
   Facebook Page.
3. **Create a Meta app** at https://developers.facebook.com → My Apps → Create
   App → type **Business**. Add the **Instagram Graph API** product.
4. **Get a long-lived access token**:
   - Open Graph API Explorer (Tools → Graph API Explorer), select your app.
   - Add permissions: `instagram_basic`, `instagram_content_publish`,
     `pages_show_list`, `business_management`.
   - Generate a User Token, then extend it: Tools → Access Token Debugger →
     paste token → "Extend Access Token" (gives ~60 days).
5. **Find your Instagram user ID**: in Graph API Explorer call
   `me/accounts` → copy your Page ID → call
   `{page-id}?fields=instagram_business_account` → the `id` inside
   `instagram_business_account` is your `IG_USER_ID`.

### 2. GitHub side (~5 min)

1. Create a new GitHub repository (private is fine) and upload these files.
2. Repo → Settings → Secrets and variables → Actions → add two secrets:
   - `IG_USER_ID`
   - `IG_ACCESS_TOKEN`
3. Repo → Actions tab → enable workflows.

### AI model: Gemini (free) or Anthropic (paid)

All writing and reviewing goes through `llm.py`. Add **one** of these repo
secrets (Settings → Secrets and variables → Actions → New repository secret):

- `GEMINI_API_KEY` — free. Create a key at aistudio.google.com (Get API key).
  Defaults: `gemini-2.5-flash` for writing and the vision reviews,
  `gemini-2.5-flash-lite` for image picks. The free tier's daily limits are set
  per project and shown in AI Studio; if one is hit, that run fails and the
  next scheduled run picks up.
- `ANTHROPIC_API_KEY` — paid per use (console.anthropic.com). Defaults:
  `claude-opus-5-5` for writing and reviews, `claude-haiku-5-5` for image picks.

If both are set, Gemini is used; set the repo variable `LLM_PROVIDER` to
`anthropic` to force Anthropic. To try other models, set the repo variables
`LLM_MODEL` / `LLM_FAST_MODEL` (Settings → Secrets and variables → Actions →
Variables).

(Until November 2026 this used GitHub Models, which GitHub retired on 30 July
2026; every request then got a bare "OK" back and nothing could post.)

Requests are kept small for the free tier: archive page text is capped at
12,000 characters, review images go in low detail, and carousels and Reels get
at most 2 review rounds.

### 3. Test it

Actions tab → "ALLOCCULT Instagram Post" → **Run workflow**. Check the log,
then check @all.occult. If it worked, you're done — it now posts daily at
18:00 UTC.

## Adjusting

- **Schedule**: edit the `cron` line in `.github/workflows/post.yml`.
- **Product/lore ratio**: `PRODUCT_EVERY_N_POSTS` in `post.py` (3 = every third
  post is a product).
- **Voice**: edit `BRAND_VOICE` and the two caption prompts in `post.py`.
- **History**: `state.json` tracks what's been posted so nothing repeats until
  a full cycle completes. Delete it to reset.

## Important limits & maintenance

- The long-lived token **expires after ~60 days**. Set a reminder to repeat
  step 1.4 and update the `IG_ACCESS_TOKEN` secret (~2 minutes). 
- Instagram allows max 25 API-published posts per 24 h — far above this
  schedule.
- **Products come from Etsy** (`ETSY_SHOP` in `post.py`). With the optional
  `ETSY_API_KEY` secret (`keystring:shared_secret` from
  https://www.etsy.com/developers/your-apps), product posts use the Etsy Open
  API and include up to 5 photos per listing. Without it, they read the public
  shop RSS feed (1 photo per listing). If neither works, that day's product post
  becomes a lore post instead of failing.

## The weekly plan

**Every Monday ~07:50 UTC** — `.github/workflows/competitor-intel.yml`:

1. `competitor_scan.py` reads the last 30 days of posts from every account in
   `competitors/handles.txt` (Graph API Business Discovery), ranks them by
   engagement rate ((likes + comments) / followers), flags "breakout" posts that
   beat their own account's median, and samples top posts for
   `competitors/hashtags.txt`. → `competitors/scan.json`
2. `trends.py` collects what's happening, free: the most-read English
   Wikipedia articles of the past week, the next 3 weeks of sky and folk dates
   (moon phases, Sun sign changes, solstices, Mercury stations — computed with
   PyEphem — plus feast days like Krampusnacht and St Lucy's), and the top
   hashtag posts. → `trends/YYYY-MM-DD.json`
3. `intel_report.py` writes the competitor analysis → `reports/YYYY-MM-DD.md`.
4. `planner.py` has the model pick the trending topics with a real occult or
   history angle, then plan the 7 days → `plan/YYYY-MM-DD.json`, also added to
   the report as section 6:

   | Day | Format | What |
   |---|---|---|
   | Mon, Wed, Fri, Sat | Reel | fast countdowns ("3 cursed books…") on the most shareable subjects |
   | Tue, Thu, Sun | carousel | 3 of the 5 pillars, rotating so all five come round every ~2 weeks |

   The pillars: **The Forbidden Library** (a numbered series on one real
   manuscript or object), **The Occult Behind It** (the real history behind
   something trending), **Cosmic Calendar** (a coming sky or folk date),
   **Myth vs History**, **Find Yours** (a lookup list from one historical
   source; "comment yours").

   Reels lead while the account is small: Instagram shows them to people who
   don't follow you yet. The October posts showed it (Reels reached 77–116
   accounts, carousels 0–1). Carousels get ~2.6× the engagement per follower
   in this niche, so shift `SLOTS` in `planner.py` toward them once the
   account has a following — `insights.json` (weekly) shows when.
   alloccult.com is one source among many: a post links to an archive page
   only when one really fits. The planner never proposes giveaways, contests or
   product promotions.
5. `compose_posts.py` turns the 4 planned Reels into specs (hook, 5–7 numbered
   beats, image search terms, music mood, caption, 12 hashtags). →
   `queue/YYYY-MM-DD.json`
6. `reel_review.py` renders and reviews them; the bundle is uploaded as the
   **posts-YYYY-MM-DD** artifact (Actions → the run → Artifacts).

To plan right away instead of waiting for Monday: Actions → Weekly Competitor
Intel → Run workflow. The plan always covers the 7 days from the day it runs.

## Carousels: written and reviewed by the model before they post

Every day at 18:00 UTC, `post.py`:

1. **Posts an approved draft** if one is waiting (`drafts/<id>/draft.json` with
   `"status": "approved"`).
2. Otherwise it **reviews the next pending draft**, or the model writes today's
   planned carousel (`carousel_ai.write_plan_draft`): 7–9 slides built the way
   its pillar works, from the plan's facts (and the archive page, if it links
   one). On a Reel day it does nothing. With no plan at all it falls back to
   the next archive entry (`carousel_ai.write_draft`).
3. **Renders it** (`carousel.py`): public-domain art on every slide, the series
   label and hook on the cover, and a closing card with the question to answer
   in the comments.
4. **The model reviews the rendered slides** (`carousel_ai.review`, with vision).
   It checks facts against the plan's notes and established history, checks
   that each image shows the subject and suits the brand (no puns or
   coincidences, no propaganda, no gore), and checks legibility and the hook.
   Problems are fixed: new text, or the image is rejected and searched again.
   It then re-renders and re-reviews, up to 2 rounds.
5. **Posts it only if it passes.** A draft that still fails is marked
   `"rejected"` and never published. Every round is kept in the draft's
   `review_log`.

Manual run: Actions → ALLOCCULT Instagram Post → Run workflow with
"prepare_only" to write and review today's carousel without posting it.
`posting.json` turns carousels, Reels and product posts on or off. Needs the
`GH_PAT` secret (to read archive page text).

## Reels with music

**The model reviews every Reel** (`reel_review.py`) right after rendering: stills
from each segment are checked like carousels (facts, image fit, legibility,
hook, caption), fixed, re-rendered and re-checked (up to 2 rounds). Only Reels
marked `"status": "approved"` are ever posted. "Reel Review Check" (Actions) is
a manual live test that changes nothing.

**Every day 15:00 UTC** — `.github/workflows/reel.yml` runs `post_reel.py`:
on a planned Reel day (Monday, Wednesday, Friday, Saturday; a missed one
catches up the next day) it renders that Reel (same artwork as the preview), uploads it straight to Instagram (resumable upload — no hosting
needed), and publishes it. It is recorded in `published.json`, so
`analytics.py` scores Reels alongside carousels.

**Scheduled Reels are on.** To pause them, set the repo variable
`REELS_ENABLED` to `false` (Settings → Secrets and variables → Actions →
Variables). Manual runs (Actions → ALLOCCULT Daily Reel → Run workflow, with an
optional "dry run") always work.

**Watch the week's Reels** on the `previews` branch (open an `.mp4` → View
raw), refreshed after every weekly run. After editing a `queue/*.json` by
hand, run Actions → Publish Reel Previews with no run ID to re-render it.

### How the videos are made

- **Artwork:** public-domain / CC0 images only, searched in this order:
  Wellcome Collection (alchemy, magic and astrology manuscripts), The Met Open
  Access, and the Art Institute of Chicago (`museum.py`). Each beat sits inside
  a thin gold frame, with the credit on screen. If no image is found, the beat
  falls back to a drawn gold heptagram card.
- **Motion ("living painting", `motion.py`, free):** a small open depth model
  (Depth Anything V2, run on the runner's CPU) works out what is near and far in
  each artwork. A virtual camera then dollies in, drifts or rises, and near
  parts move more than far ones, so the shot travels *into* the engraving.
  Drifting smoke, gold dust motes, candle flicker, a vignette and film grain
  are drawn on top. Nothing is generated: the artwork's own pixels are only
  displaced by a few percent, so faces and lettering stay intact. The model
  (~100 MB, from GitHub) is downloaded once and cached by the workflows. If it
  can't be loaded, a simpler built-in depth guess is used; if motion fails
  altogether, that segment falls back to the flat Ken Burns zoom. Set
  `"motion": "kenburns"` in `posting.json` to turn it off. Tune strength with
  the knobs at the top of `motion.py` (`PARALLAX`, `SMOKE`, `DUST`, `FLICKER`,
  `GRAIN`, `VIGNETTE`). Test on one image:
  `python motion.py art.jpg out/test.mp4 5`.
- **Text:** hook in Cinzel (gold), beats in EB Garamond, and a closing
  alloccult.com card. Cuts fade through black.
- **Music:** `music.py` generates an original dark-ambient track per Reel
  (moods: `drone`, `ritual` heartbeat drum, `bells`, `choir`), so there are
  never copyright claims. To use your own tracks instead, drop them in
  `music/` named `<mood>_anything.mp3` (e.g. `music/ritual_01.mp3`). Only use
  tracks you have the rights to.
  Instagram's API **cannot** attach songs from Instagram's in-app music
  library, so API-posted Reels show "Original audio". If you want a trending
  song on a specific Reel, download it from the bundle and post it from the app.
- **Carousels with music:** the API can't add music to image or carousel
  posts either. To turn a carousel into a music Reel instead, run:
  `python render_reel.py --slides slides/<id> out/reel.mp4 --mood bells`

### Setup

1. `competitors/handles.txt` is pre-filled with 34 researched accounts
   (October 2026). After the first run, look at `skipped` in
   `competitors/scan.json`: those are personal accounts or renamed handles.
   Remove or replace them.
2. Hashtag sampling needs the **Instagram Public Content Access** feature on
   the Meta app. Without it, that part is skipped and the account scan still
   runs. Instagram allows 30 unique hashtags per rolling 7 days.
3. Secrets are the existing ones: `IG_USER_ID`, `IG_ACCESS_TOKEN`. If the scan fails with a permission error, add
   `pages_read_engagement` and `instagram_manage_insights` to the token in
   Graph API Explorer.

### Run locally

```bash
sudo apt install ffmpeg && pip install pillow numpy fonttools opencv-python-headless onnxruntime ephem anthropic
mkdir -p fonts   # then download Cinzel.ttf + EBGaramond.ttf as in post.yml
export IG_USER_ID=... IG_ACCESS_TOKEN=... GEMINI_API_KEY=...   # or ANTHROPIC_API_KEY
python competitor_scan.py
DATE=$(date -u +%F)
python trends.py "$DATE"
python intel_report.py "$DATE"
python planner.py "$DATE"
python compose_posts.py
python render_reel.py "queue/$DATE.json" all "out/posts-$DATE"   # preview bundle
python post_reel.py --dry-run                                     # render next, don't post
```

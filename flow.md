# How the code runs

This document explains where execution starts, the order things happen in, and which function calls which. It covers the backend (Python) and the browser (JS).

The reasons behind the design choices are in [Decision.md](Decision.md). Function names are real and can be searched for in the code. Line numbers aren't given, because they change with every edit.

---

## Contents

0. [The big picture](#0-the-big-picture)
1. [Entry points](#1-entry-points)
2. [Startup order](#2-startup-order-python-apppy)
3. [Every HTTP request passes these first](#3-every-http-request-passes-these-first)
4. [Flow: Search Internships](#4-flow-search-internships-the-main-one)
5. [Flow: the scam check](#5-flow-the-scam-check-moderation)
6. [Flow: Load 5 more](#6-flow-load-5-more)
7. [Flow: the browser side](#7-flow-the-browser-side)
8. [Threads, all together](#8-threads-all-together)
9. [Where data lives](#9-where-data-lives)
10. [Status of a post](#10-status-of-a-post-moderation_status)
11. [File map](#11-file-map-who-imports-whom-main-paths-only)

---

## 0. The big picture

```
 Browser (templates + static/*.js)
    │  fetch('/api/...')            ▲ polls every 1.5–5 s
    ▼                                │
 app.py (Flask on waitress) ── guards ─┐
    │                                  │
    ├─ POST /api/scrape ──► thread ──► scraper.run_scrapers ──► sites/*.py (6 at a time)
    │                                         │
    │                                         ▼
    │                         filters / genuine ──► output_handler.sync_listings ──► internships.csv
    │                                         │                                        ▲
    │                                         └─► moderation.notify.start_scam_check   │
    │                                                     │ wake()                     │
    │                                                     ▼                            │
    │                               thread "scam-check": pipeline.runner.check_waiting │
    │                                 rules → vectors → judge → fuse ──► save_verdict ─┘
    │                                                                        │
    │                                       thread "second-look": agent ◄────┤ (review only)
    │                                                                        ▼
    │                                                       supabase_sync.publish_later ──► Supabase
    └─ GET /api/internships ──► output_handler.read_all_rows ──► CSV
```

---

## 1. Entry points

| How it starts | File | What runs |
|---|---|---|
| `python app.py` | `app.py` → `if __name__ == "__main__"` | **The app.** Web server, scam-check worker and Supabase backfill. Normal use. |
| `python scraper.py --source internshala --dry-run` | `scraper.py` → `__main__` | Scrapes from the terminal, with no dashboard. `--dry-run` prints instead of saving. |
| `python test_sites.py` | `test_sites.py` | Dry-runs every site one by one and prints a summary. |
| `python -m moderation.pipeline [--sample \| --one]` | `moderation/pipeline/__main__.py` | Runs the scam check by hand (`--sample` uses 3 made-up posts and saves nothing). |
| `python -m moderation.build_index` | `moderation/build_index.py` | Embeds `scam_patterns.json` into `pattern_index.json`. **Run this once, and again after editing the phrases.** |
| `python -m moderation.recheck [--all \| --source X]` | `moderation/recheck.py` | Puts judged posts back in the queue. |
| `python -m moderation.check_azure` | `moderation/check_azure.py` | Live check that the Azure keys and deployments work. |
| `python -m moderation.eval_judge` | `moderation/eval_judge.py` | Measures the AI judge on 9 scam and 9 genuine test posts. |
| `python -m supabase_sync` | `supabase_sync.py` | Pushes every judged row to Supabase. |
| `pytest` | `tests/` | 177 tests. No live APIs (recorded answers). |

In the browser, the entry points are the three pages Flask renders:

| URL | Template | Scripts, in load order |
|---|---|---|
| `/` | `templates/site.html` | `theme.js` → CDN (Tailwind, Phosphor, three.js, supabase-js) → `background.js` → `site.js` |
| `/app`, `/app/applications` | `templates/index.html` (user mode) | `theme.js` → CDN → `background.js` → `profile_options.js` → `app_radar.js` → `onboarding.js` (`avatars.js` is lazy-loaded) |
| `/admin`, `/admin/applications` | same template, admin mode (laptop only) | same |

---

## 2. Startup order (`python app.py`)

Module import runs first, top to bottom:

1. `from scraper import run_scrapers`. This imports every `sites/*.py` scraper, plus `filters`, `genuine` and `output_handler`.
2. `moderation.env.load_env()` reads `.env` into `os.environ`. `.env` values override variables already set in Windows.
3. `app = Flask(...)` is created. Then the hooks are registered:
   - `before_request` (`guard_hosts`, `guard_cross_site`, `guard_writes`, `same_origin_for_sign_in`)
   - `after_request` (`security_headers`)
   - the routes

Then the `__main__` block runs:

```
_hold_old_listings()            # output_handler.hold_unreleased(): unchecked rows → "held"
start_publish_loop()            # thread "supabase-backfill": supabase_sync.publish(all rows), every 15 min
moderation.pipeline.start_worker()   # thread "scam-check": runner._loop(), waits for wake() or 30 min
waitress.serve(app, 127.0.0.1:PORT, threads=8)   # blocks here; each request runs on a waitress thread
```

Nothing scrapes at startup. `autopilot.start()` exists, but nothing calls it.

---

## 3. Every HTTP request passes these first

```
request
  → guard_hosts()            Host must be localhost / 127.0.0.1 / [::1] / INREAL_ALLOWED_HOSTS   (403)
  → guard_cross_site()       /api: Sec-Fetch-Site + Origin not cross-site; POST needs X-InReal   (403)
  → guard_writes()           /api/moderation/* (not status), protected POSTs and /api/logs, /api/autopilot:
                             laptop (loopback) or admin token only; a tunnelled visitor gets a read-only view
  → same_origin_for_sign_in() GET of /, /app or /app/applications on 127.0.0.1 → redirect to localhost (Google sign-in returns there)
  → the route function
  → security_headers(resp)   CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy
```

`X-InReal: 1` is added in the browser by the `fetch` wrapper in `static/theme.js`, which loads first on every page.

---

## 4. Flow: Search Internships (the main one)

**Browser (`app_radar.js`, `bindEventHandlers` → search form submit):**

```
config = { regions, sources, field, limit: FIRST_BATCH }
fetch('POST /api/scrape', config)
startNewView(run_tag)              # the page shows only this search's tag from now on
```

**Server, `app.trigger_scrape()`** (request thread, returns at once):

1. Refuses the request if `sources` is empty (400). Returns `running` if a scrape thread is already alive.
2. A new search gets a run tag `YYYYMMDD-HHMMSS`, and `output_handler.prune_old()` runs (deletes posts unseen for 3 days). "Search more" sends the existing tag instead.
3. Starts a background thread with `scrape_job(cfg)`, which sets `cfg["first_show"] = 10` and calls **`scraper.run_scrapers(config=cfg)`**.

**`scraper.run_scrapers(config)`** (scraper thread):

```
RUN_PROGRESS.update(...)                    # read by GET /api/scrape/status → the scan panel
fields.set_current(config.field)            # every site searches for this field
RUN_TAG["value"] = run_tag
registry.scrapers_for(sources)              # ticked sites → scraper functions (ALL_SCRAPERS)
per_site = min(15, limit / n_sites)         # posts kept per site
_release["left"] = first_show (10)
budget.start(per_site * 2, seen_ids)        # each site stops once it has this many unseen posts
ThreadPoolExecutor(max 6), sites sorted by site_speed_rank (API sites first, Chrome-window sites last)
  └─ run_one(name, fn) → _run_one
       ├─ fetch(): fn() or fn(config=…)     # sites/<site>.py → list of record dicts
       │     Naukri/Foundit/SimplyHired/Careerjet hold the visible_chrome lock (one at a time)
       │     dropped connection → wait 3 s, try once more
       └─ process_and_save(name, listings, per_site)
budget.stop(); update_run_history(); RUN_PROGRESS.finished = True
```

**Inside one site scraper** (example `sites/internshala.scrape_internshala`):

```
Playwright page → urls_for_field() (fields.search_terms) → parse_list_page(html)
  → budget.enough()? stop paging
  → open job pages → parse_detail_page(html) (full description, stipend)
  → records built by sites/_common.record(...)      # same dict shape for every site
```

API-based sites (Unstop, LinkedIn, Foundit, government) call the site's JSON endpoint through `_common.get` / `post_json`. `sites/details.fill_details` reads the full post where the search page gave only a snippet.

**`scraper.process_and_save(source, raw, max_new)`:**

```
evaluate(source, raw)
  ├─ mark_repeated_posts(raw)                         # same post in 3+ locations
  └─ for each item:
       filters.internship_rejection_reason(...)       # not an internship / wrong field (fields.matches)
       experience ≥ 3 years?                          # dropped
       filters.stipend_rejection_reason(...)
       UNPAID_RE                                      # marks the stipend "Unpaid"
       genuine.check_listing(item)                    # money asked → drop; softer issues → trust_flags
  flag_other_posts_of_training_sellers(results)
  collapse_copies(results)                            # 3+ copies shown once
item["field"] = fields.current()
sort by match_score
output_handler.sync_listings(kept, dropped_ids, max_new, hold=True, run_tag)
    # under _CSV_LOCK: new → added as "held"; seen before → fields refreshed, verdict kept
    # unless the text changed; dropped on re-check → removed
release_held(_release["left"], run_tag)               # the first 10 of a new search → queue ("")
moderation.notify.start_scam_check(source)            # → pipeline.wake(): checks this site now
```

So the first site's posts are being checked while the next sites are still being scraped.

---

## 5. Flow: the scam check (`moderation/pipeline`)

**Trigger:** `notify.start_scam_check()` → `runner.wake()` sets an event. The **scam-check** thread (`runner._loop`) wakes up, and calls `check_waiting()` repeatedly until a round checks nothing.

**`runner.check_waiting()`:**

```
bank = vectors.load_bank()                      # pattern_index.json (cached by mtime)
under _round_lock:
  rows = output_handler.pending_moderation(10, claim=True)
        # round-robin across sites; a person's posts before "auto-" ones; marked "checking"
  verdicts = judge_posts(rows)
  for v: output_handler.save_verdict(id, status, risk, reasons)
        # approved + approval_doubts() → review; writes CSV; _share() → supabase_sync.publish_later (thread)
if any "review": agent.look_later(ids)         # second-look thread, see below
on any exception: every claimed row → save_verdict(..., "retry")  (back in the queue)
```

**`runner.judge_posts(rows)`**, the three stages:

```
link_check.resolve(apply_link) ×10 in parallel   # safe_http.safe_get, each redirect hop checked
  dead/closed link → fuse.expired_verdict        (not a scam judgement)
rules.analyse(row, link)                          # stage 0: link_signals, text_signals, chunk_text
vectors.pack → embed_call (≤4 parallel) → unpack  # stage 1: search() vs scam + honest phrases, gate()
  gate = block → fuse.stage1_verdict              (near-copy of a known scam; no AI call)
judge.pack(items, provider, 5)                    # stage 2: build_request (fence, FORGED_LINE)
judge.call(request) ×2 in parallel                # Azure gpt-4o, strict JSON schema
fuse.fuse_batches(batches, answers)
  └─ split_batch → fuse(listing, item, resp)
       parse_llm → verify_evidence (quotes must be in the post) → injection_phrase
       risk = 0.6·LLM + 0.25·vector + 0.15·signals → decide(risk) → approved / review / blocked
```

**Second look** (thread `second-look`, `agent._loop`): it takes one id at a time from a queue (max 200).

```
_save(id) → row still "review"? → second_look(row)
  build_graph(model) → LangGraph: think ⇄ act (tools: open_apply_link, search_web, read_web_page) ≤ 6 steps
  → submit_verdict → apply_second_look(row, answer, sources)   # code decides; quotes must be from fetched pages
→ save_verdict(...)
```

---

## 6. Flow: Load 5 more

```
browser: fetch('POST /api/moderation/load-more', {count: 5, run_tag, show})
app.moderation_load_more()
  load_more.busy()? → 409
  ids = output_handler.release_held_ids(5, run_tag)     # held → "checking", round-robin
  thread: notify.start_scam_check("load more")
  load_more.start(ids, …)  → thread "load-more": fill()
       loop: _wait_for(batch) until every verdict is in (≤150 s)
             shown += verdicts that the page's filter shows
             short = 5 − shown;  stop if ≤ 0, or 15 checked, or nothing held
             batch = release_held_ids(min(room, short × 2)); wake()
browser: pollModeration() reads /api/moderation/status → .load_more {shown, checked, running}
```

---

## 7. Flow: the browser side

### Landing page (`/`, `static/site.js`)

```
start():
  background.initGlassTranslucentBackground()
  newSpotRound(); watchSteps()
  supabase.auth.getSession() → signed in? location.replace('/app')
  showLanding()                        # ticker and numbers from Supabase listings
Sign-in button → signIn() → supabase.auth.signInWithOAuth('google', redirectTo '/')
  → Google → back to '/' → session → /app
```

### Dashboard (`/app`, `static/app_radar.js`)

Top-level code runs as soon as the file loads: constants, `CFG = window.INREAL`, `USER_MODE`, the supabase client `sb`, and `document` listeners.

On `DOMContentLoaded`:

```
initGlassTranslucentBackground()
bindEventHandlers()                     # every button, filter, keyboard shortcut, search form
USER_MODE ? requireSignIn() : (admin, laptop only)
  requireSignIn():
    sb.auth.getSession() → none? location.replace('/')
    sb.from('profiles').select(COLS) → missing row? recreate it
    profile / identity filled; renderAvatars()
  → startDashboard()
       initProfile()                    # profile form, onboarding.js for a first visit
       dropStaleView()                  # remembered search older than 6 h → forget, offer "Search again"
       updateViewNote()
       startSession()                   # POST /api/session/new (prunes only)
       pollScraperStatus()   ─┐
       pollAlerts()           ├─ each re-schedules itself with setTimeout
       pollModeration()      ─┘
       updateBookmarkCounter()
       loadApplications()               # Supabase applications (or localStorage on /admin)
```

The page is refreshed by its polling loops. Nothing is pushed from the server.

| Loop | Every | Calls | Then |
|---|---|---|---|
| `pollScraperStatus` | 3.5 s | `GET /api/scrape/status` | `handleScrapeProgress` → `renderScanPanel`, site popups |
| `pollAlerts` | 3 s | `GET /api/alerts` | action banner (for example "solve the check in the Chrome window") |
| `pollModeration` | 1.5 s while work waits, else 5 s | `GET /api/moderation/status` | `updateHeldUI` (Load 5 more bar). If the judged count changed → `loadData()` |

```
loadData()  → GET /api/internships → allInternships
            → announceNewlyVerified() → populateSourceFilter() → applyFiltersAndRender()
applyFiltersAndRender() → view (this search / last 3 days / saved) + filters + profile rules
            → renderListings(items) → cards (data-id) ; renderOverviewStats()
card click  → openDetailDrawer(id) → updateDrawerApplied(), updateDrawerBookmarkIcon()
```

### Applied tracker (section 20 of `app_radar.js`)

```
click #drawer-apply-link → pendingApply = {item, at, away:false}
blur / tab hidden        → wentAway()
focus / visible / first mouse move or key → cameBack()
     away ≥ 1.5 s → showApplyAsk(item)     # mandatory card, focus trapped
"Yes, I applied" → markApplied(item) → sb.from('applications').insert(...) → refreshApplied()
refreshApplied() → applyFiltersAndRender() + updateDrawerApplied() + fillProfileMenu() + renderAppsList() if the page is open
```

### My applications page

```
avatar menu → toggleProfileMenu() → [data-pm=apps] → showAppsPage()
   renderAppsList(); body.page-apps (hides <main>); history.pushState('/app/applications')
Back link / browser Back / logo → leaveAppsPage() → history.back() → popstate → hideAppsPage()
Direct load of /app/applications → DOMContentLoaded → showAppsPage(false)
```

### My profile (section 21)

```
openMeModal() → fillMe() → renderMeSummary()
photo:    uploadPhoto(file) → openCropper(bmp) → saveCrop() → savePhotoBlob() → Supabase Storage avatars/{uid}/… → saveIdentity()
character: renderCharacters() → loadAvatarLib() (lazy /static/avatars.js) → chooseCharacter() → savePhotoBlob()
banner:   chooseBanner(key) | uploadBanner → openCropper(bmp,'banner') → saveBannerBlob()
avatars everywhere: renderAvatars() → sharpenAvatars() → thumbFor(src, px)   (again when the zoom changes)
```

---

## 8. Threads, all together

| Thread | Started by | Lives | Does |
|---|---|---|---|
| waitress workers (8) | `serve()` | always | HTTP requests |
| `supabase-backfill` | `start_publish_loop()` at startup | always | `supabase_sync.publish(all rows)` every 15 min |
| `scam-check` | `pipeline.start_worker()` at startup | always | `runner._loop` → `check_waiting()` on `wake()` or every 30 min |
| scraper | `/api/scrape` | one search | `run_scrapers` + up to 6 site threads inside it |
| `load-more` | `/api/moderation/load-more` | one click | `load_more.fill` |
| `second-look` | first `agent.look_later()` | always after that | one review post at a time |
| short publish threads | `save_verdict` → `publish_later` | one upsert | Supabase |

The scraper and the scam check both write `internships.csv`. Every read and write takes `output_handler._CSV_LOCK` (an RLock). `pending_moderation(claim=True)` marks rows "checking" so that two overlapping rounds never take the same posts.

---

## 9. Where data lives

| Data | Where | Written by | Read by |
|---|---|---|---|
| Listings and verdicts | `internships.csv` | `output_handler.sync_listings`, `save_verdict`, `release_held_ids`, `prune_old` | `/api/internships`, the pipeline |
| Seen IDs, run history | `internships_log.json` | `sync_listings`, `update_run_history` | `budget.start`, `/api/logs` |
| Scam phrase vectors | `moderation/pattern_index.json` | `build_index` | `vectors.load_bank` |
| Shared judged list | Supabase `listings` | `supabase_sync.publish` (secret key, laptop) | landing page, `/app` |
| Profiles, bookmarks, applications | Supabase tables (RLS) | the browser (publishable key) | the browser |
| Photos and banners | Supabase Storage `avatars` | the browser | `<img>` |
| Remembered search, theme, panel sizes | browser `localStorage` | `app_radar.js`, `theme.js` | same |

---

## 10. Status of a post (`moderation_status`)

```
(new from a site) ── held ──Load 5 more / first 10──► "" (waiting) ──claim──► checking
                                                                     │
                       approved ◄── fuse/decide ─────────────────────┤
                       review   ◄───────────────────────────────────┤ ──agent──► approved / blocked / review
                       blocked  ◄───────────────────────────────────┤
                       expired  ◄── dead/closed link ────────────────┘
                       retry → back to "" (API down)
blocked ──Unblock button (/api/moderation/unblock)──► approved
```

---

## 11. File map (who imports whom, main paths only)

```
app.py ─► scraper ─► sites/* ─► sites/_common, sites/details, sites/budget, fields, filters
       │          ├► filters ─► fields
       │          ├► genuine
       │          └► output_handler ─► supabase_sync
       ├► moderation/notify ─► moderation/pipeline/runner
       │                         ├► rules ─► (link result from moderation/link_check ─► safe_http)
       │                         ├► vectors (pattern_index.json)
       │                         ├► judge
       │                         ├► fuse
       │                         └► agent ─► safe_http, langgraph, langchain-openai
       ├► moderation/load_more ─► output_handler
       └► moderation/env (load .env), sites/registry, fields
```

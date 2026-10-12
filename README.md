# 🤖 AI/ML Internship Radar
### *Your personal robot that hunts down AI internships while you sleep.*

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/flask-3.x-green.svg)](https://flask.palletsprojects.com)
[![Playwright](https://img.shields.io/badge/playwright-stealth-blueviolet.svg)](https://playwright.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **InReal** by Team Chiranjeevi (CodeX 3.0, PIET Panipat, Oct 2026): we took the open-source *AI/ML Internship Radar* (MIT licence), updated its scrapers to the portals' current page structure, and added a genuine-only check that removes listings asking for money, task-for-money schemes and mass "internship" programmes. The first commit in this repo is the original code, unchanged; every later commit is our work.

---

## � The Problem

You're a CS/AI student trying to land an internship for summer 2026.

So you open 17 tabs — LinkedIn, Internshala, Naukri, Unstop, some obscure university portal — spend 3 hours copy-pasting, and realize half the listings are from 2024.

**There's a better way.**

---

## � What This Does

This project is a **fully automated web scraping system** that:

- 🕷️ **Scrapes 60+ platforms simultaneously** — India AND worldwide
- 🧠 **Filters by actual AI/ML relevance** — not just "software" jobs
- 🚫 **Auto-rejects closed, expired, and past-year listings** — no 2024 garbage slipping through
- 📊 **Scores every listing from 0–100** based on your profile
- �️ **Streams everything to a beautiful dashboard** at `http://localhost:5000`
- ⏰ **Runs daily at 8 AM automatically** (set it, forget it)

You click one button. The robot does the rest.

---

## � The Dashboard

It looks like something Bloomberg would build:

- 🌍 **Region Tabs** — Everything / 🇮🇳 India / 🌐 Global / 📡 Remote — click to instantly switch
- 🔥 **Match Score Badges** — Glowing green means high AI/ML relevance. Red means meh.
- ⚡ **Live Log Terminal** — Watch the scraper work in real-time right inside the browser
- 🗑️ **Clear Database Button** — Red trash icon wipes everything so you can start 100% fresh

Cards are sorted and rendered using CSS Grid `order` properties — which means **zero flickering**, even with 300+ listings live-updating every 4 seconds. Butter smooth.

---

## ⚠️ But Wait — Some Sites Are Sneaky

LinkedIn, Naukri, and Unstop have bot blockers. So the scraper:

1. Opens these browsers **visibly** (not headless) so you can see what's happening
2. Shows you a glowing orange **"Action Required"** banner in the dashboard if a CAPTCHA appears
3. Waits **45 seconds** for you to solve it (or it auto-skips and moves on)
4. You click **Done** → banner disappears → scraper resumes silently

It's like pair-programming with a robot.

---

## �️ Where It Scrapes (60+ Sources)

### 🇮🇳 India
| Platform | How | Notes |
|----------|-----|-------|
| **Internshala** | Playwright stealth | India's #1 internship platform |
| **Unstop** | Playwright headless=False | Scans for "closed" tags — won't waste your time |
| **Naukri.com** | Playwright headless=False | India's largest job board |
| **LinkedIn Jobs** | Playwright headless=False | 100+ search configs across Indian cities |
| **Shine / Foundit / Apna / CutShort** | Requests + BS4 | Four aggregators at once |
| **DRDO, ISRO, Govt Labs** | Requests | Real government research portals |
| **DuckDuckGo Dorks** | DDG API | Hidden `.ac.in` and `.res.in` gems |

### 🌐 International
| Platform | How | Coverage |
|----------|-----|----------|
| **LinkedIn Jobs** | Playwright | 15+ EU countries, US, Asia |
| **Remotive + WeWorkRemotely** | RSS + Playwright | Best remote AI/ML listings |
| **DuckDuckGo University Search** | DDG API | **54 search queries** — see list below |
| **BigTech Careers** | Requests | Google, Meta, Microsoft, Apple, Amazon |
| **Niche AI Boards** | Requests | ML-specific boards you've never heard of |

### 🎓 University & Research Lab Discovery

The university scraper fires **54 live DuckDuckGo searches** every run. No hardcoded links. It dynamically discovers current positions at:

🇮🇳 `IIT, IISc, IIIT, TIFR, DRDO, ISRO`
🇩🇪 `DAAD RISE, Max Planck, TU Munich, ETH Zurich, EPFL`
🇬🇧 `Oxford, Cambridge, UCL, Imperial`
🇺🇸 `MIT, Stanford, CMU, Berkeley, Cornell, NSF REU, DOE SULI`
🌐 `OpenAI, DeepMind, Anthropic, Google DeepMind, Meta FAIR, NVIDIA`
🇨🇦 `Mitacs, Mila, Vector Institute, UBC`
🇸🇬 `NUS, NTU, A*STAR, AI Singapore`
🌍 `CERN, ESA, KAUST, Technion, KAIST, RIKEN AIP, CSIRO`

Every run = fresh results. Zero maintenance.

---

## ⚙️ How the Filtering Works (The Smart Part)

### 🔑 AI/ML Keyword Gate
Every listing must contain at least one of **50+ AI/ML terms** to even get in the door:
`machine learning` / `deep learning` / `computer vision` / `LLM` / `generative AI` / `NLP` / `transformers` / `reinforcement learning` / `AI research` and more.

And if the title says `senior`, `5+ years`, `manager`, `PhD required`, or `full-time` — **auto-rejected.** You're looking for internships, not a job for someone with a decade of experience.

### 📅 Past Year Defense
Aggregator sites often surface old 2024/2025 listings in their search results. The filter dynamically reads `datetime.now()`, computes the current target year, and then **physically scans the raw listing text** for any stale year string. If it finds `2024` or `2025` hiding in there — the card is shredded before it ever hits your screen.

### 🗓️ Summer Date NLP
- Listings must start **on or after May 20** of the upcoming summer
- But terms like `"immediately"`, `"rolling"`, `"ASAP"`, or `"flexible"` are always allowed — because a good opportunity isn't date-dependent
- Powered by `dateparser`, a real NLP date extraction library

### 💰 Stipend Check
- **India**: Minimum ₹5,000/month (or unspecified = OK)
- **International**: Any compensation is fine
- Explicit `"Unpaid"` or `0` always filtered out

### 🛡️ Genuine-Only Check (`genuine.py`)
A listing is **removed** only for things a real internship never does:
- it asks the candidate to pay (registration / training / security fee, deposit, "pay ₹999 to book your slot")
- it is a task-for-money scheme (like / review / prepaid tasks)
- it is a mass programme, not a selective internship (for example 4 lakh people "hired" from 1,800 posts)

Softer warnings are **kept** and written to the `trust_flags` column: very short duration, a brand-new employer with no hires yet, an employer that posts a lot but hires few, or no stated stipend. Big real companies can look odd on one number, so these never delete a listing on their own.

### 🔎 Scam Moderation Pipeline (n8n)
After every scrape, an n8n workflow checks each new listing in three stages: rules on the apply link and contact details, a vector search of every sentence against known scam phrases (and honest ones, so "no fee" doesn't match "pay the fee"), and one LLM call that must quote the post. Quotes are checked against the real text and the scores are combined, so the LLM alone can never block a post. Verdicts appear on each card. Setup and design: [N8N_SETUP.md](N8N_SETUP.md).

### 🧪 Test One Platform
```bash
python scraper.py --source internshala --dry-run
```
Nothing is saved to `internships.csv`. It prints how many listings were kept or dropped and why, and writes every listing with its reason to `test_output/internshala.csv`. Offline parser tests (saved copies of the live pages): `python -m pytest tests -q`.

### 🔧 Selector Upgrade Status
| Platform | Checked on live site | Status |
|---|---|---|
| Internshala | 12 Oct 2026 | Selectors updated (title is now `h2 a.job-title-href`, location `.row-1-item.locations`, duration by calendar icon, last page by `#isLastPage`); detail page adds employer activity |
| Unstop, Naukri, LinkedIn, Shine, Foundit, Apna, Govt (AICTE) | 12 Oct 2026 | Upgraded; see [SELECTOR_TRACKER.md](SELECTOR_TRACKER.md) for each site's test results |
| Cutshort, RSS, WWR | — | Not re-checked yet |

---

## �️ How to Set It Up (Actually Simple)

**You need:** Python 3.9+ and Google Chrome. That's it.

```bash
# 1. Clone the project
git clone https://github.com/abhishekgoswami0720/InReal.git
cd InReal

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux

# 3. Install everything
pip install -r requirements.txt
python -m playwright install chromium

# 4. Run it
python app.py
```

Open **http://localhost:5000** → click **"Run Scraper Now"** → go make tea ☕

---

## 🎮 Using the Dashboard

**Buttons in the top-right corner:**

| Button | What it does |
|--------|-------------|
| 🔄 Refresh | Reload the current data from CSV |
| 🗑️ Trash (red) | Wipe the entire database and start fresh |
| ℹ️ Info | Open the usage guide modal |

**Sidebar filters** let you drill down by:
- 🌍 Location (India / Remote / Global)
- 💵 Stipend bracket (Any / Paid / >₹10K / >₹20K / >₹50K)
- 🏛️ Org type (Company / Institution / Government)
- 🔬 Role type (Research Core / Applied Engineering)
- 📡 Source platform (per-source dropdown)

**Match Score legend:**
- 🟢 **≥80** — Dream listing. Apply immediately.
- 🟡 **60–79** — Good match. Worth a look.
- 🔴 **<60** — Peripheral. Only if you're desperate.

---

## 🥷 Anti-Bot Tactics

The scraper doesn't act like a robot (ironically). It uses:

- **Playwright Stealth Plugin** — patches browser fingerprints, defeats bot detection
- **Random human delays** — 1.5–4.5 second waits between clicks
- **Rotating User-Agents** — realistic Chrome UA strings on Windows/Mac
- **Random scrolling** — simulates actually reading the page
- **Visible browser for protected sites** — you intervene when needed
- **Exponential backoff retries** — fails gracefully on network blips

---

## 🗂️ Project Structure (If You Want to Poke Around)

```
internship_scraper/
├── app.py                 ← Flask server + all API endpoints
├── scraper.py             ← Orchestrator: runs all scrapers in sequence
├── filters.py             ← The brain: NLP keyword + date + stipend filters
├── output_handler.py      ← Deduplication engine + CSV writer
├── scraper_utils.py       ← Shared tools: delays, headers, stealth args
│
├── sites/
│   ├── internshala.py     ← Playwright stealth scraper
│   ├── unstop.py          ← Playwright + closed-card detection
│   ├── naukri.py          ← CAPTCHA-aware visible browser
│   ├── linkedin.py        ← 100+ config LinkedIn public jobs scraper
│   ├── rss_feeds.py       ← Remotive + WeWorkRemotely RSS
│   ├── government.py      ← DRDO, ISRO, govt portals
│   ├── misc_india.py      ← Shine, Foundit, Apna, CutShort
│   ├── international.py   ← WeWorkRemotely Playwright
│   ├── bigtech.py         ← FAANG career pages
│   ├── niche.py           ← AI-specific job boards
│   ├── search_engine.py   ← 8 DuckDuckGo dork queries (geo-filtered)
│   └── universities.py    ← 54 DDG searches, global university discovery
│
├── templates/index.html   ← The dashboard
├── static/style.css       ← Bloomberg dark aesthetic, glassmorphism
├── static/script.js       ← Live filtering, polling, XSS-safe card rendering
│
├── internships.csv        ← The database (gitignored)
├── internships_log.json   ← Scraper memory for deduplication (gitignored)
├── scraper_run.log        ← What the scraper did (gitignored)
└── scraper_errors.log     ← What went wrong (gitignored)
```

---

## � Trouble? Read This First.

**"No listings showing for Naukri / Unstop"**
→ A CAPTCHA appeared and the timer ran out. Just run the scraper again and solve it when the browser pops up. You have **45 seconds**.

**"LinkedIn is showing 0 results"**
→ LinkedIn probably showed a sign-in popup. Close it manually when the visible browser opens.

**"DuckDuckGo returned nothing"**
→ DDG rate-limits aggressive requests. Wait 5 minutes and try again. Or increase the delay in `scraper_utils.py` → `human_delay()`.

**"Port 5000 is already in use"**
→ Change the last line in `app.py` to `app.run(debug=True, port=5001)`.

**"Clear button did nothing"**
→ The scraper was probably still running. Wait for it to finish first, then clear.

---

## 📊 Output Format

Every discovered internship is saved to `internships.csv` with:

| Field | Description |
|-------|-------------|
| `id` | MD5 hash for deduplication |
| `role_title` | Job title |
| `company_name` | Company or institution |
| `location` | City / Country |
| `location_type` | `India` / `International` / `Remote` |
| `stipend` | Raw text (e.g., "₹15,000/month") |
| `stipend_numeric` | Parsed number |
| `apply_link` | Direct URL |
| `source_platform` | Which scraper found it |
| `date_scraped` | When it was discovered |
| `org_type` | `Company` / `Institution` / `Government` |
| `role_type` | `Research` / `Applied` |
| `match_score` | 0–100 relevance score |

---

## ⏰ Running on a Schedule

**Windows (Task Scheduler):**
```powershell
schtasks /create /tn "AI Radar" /tr "python C:\path\to\internship_scraper\scraper.py" /sc DAILY /st 08:00
```

**Mac/Linux (Cron):**
```bash
0 8 * * * cd /path/to/internship_scraper && python scraper.py >> cron.log 2>&1
```

---

## 📜 License

MIT — do whatever you want with it.

---

## ⚠️ Disclaimer

This was built for personal use to find internships. Please don't hammer servers at high frequency or use this commercially. The rate limiting is there for a reason — be a decent human to the websites you're scraping.

## Share a public link (demo)

On the laptop, double-click **`run_public.bat`** (needs `winget install --id Cloudflare.cloudflared` once).
It starts the app with the `waitress` server (debug off) and prints a `https://….trycloudflare.com` link.

- Anyone with the link sees the dashboard **read-only**: no scrape button, and every write endpoint
  (`/api/scrape`, `/api/clear`, `/api/moderation/*`) returns 403 for them.
- Scraping and n8n still work from the laptop itself (`http://127.0.0.1:5000`), unchanged.
- The link changes every time the tunnel restarts, and stops when the laptop sleeps.
- Optional: set `INREAL_ADMIN_TOKEN` in `.env` to allow writes from elsewhere with the `X-InReal-Token` header.
- `set INREAL_DEBUG=1` brings back Flask's debug server, for local development only, never with a tunnel.

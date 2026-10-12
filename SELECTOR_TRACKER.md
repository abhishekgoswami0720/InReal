# Selector Tracker

Every HTML selector and URL the old code depends on, platform by platform, and what is left to fix.
Websites change their page structure often, so when a scraper suddenly returns 0 listings, start here.

**Status:** ✅ updated and tested on laptop · 🟡 updated, waiting for laptop test · 🔴 old selectors, not checked yet · ⚪ not a real listing scraper

**Test one platform** (nothing is saved, the reasons go to `test_output/<source>.csv`):
```
python scraper.py --source <name> --dry-run
```

## Test round 2: latest code, terminal + web (started 12 Oct 06:06)

No new sites until all 7 upgraded sites pass both checks on the laptop. The filters changed after the first runs (unpaid in title, copies shown once, new flags), so every site is tested again.

| Site | Terminal `--dry-run` | Web dashboard (only this site ticked) |
|---|---|---|
| Internshala | ✅ 06:11 — 393 read, 81 kept; 4 posts now flagged "one post listed for 6–11 towns" | ✅ 06:27 — 81 saved to `internships.csv` (same as terminal), every card has title, company and link, 29 with warnings (incl. new "100 openings for one internship" ×2) |
| Unstop | ✅ 06:37 — 589 read, 15 kept (one fewer than round 1: a post that says unpaid) | ✅ 06:37 — 15 saved, same as terminal; 3 flagged "stipend not stated", 1 commission pay, 1 training wording |
| Naukri | ⚠️ 06:49 — 40 read, 13 kept, "page 3 did not load". 06:57 (one search per pay range) — "page 2 did not load". Cause: Naukri fetches every page after the first through its job API, which now wants a reCAPTCHA token; in the browser neither "Next" nor "2" changed the list, and a direct "-2?…" URL bounces to page 1. Fixed: read only first pages, of 20 narrower searches (4 keywords × 5 pay ranges). Re-test | ✅ 06:52 — 13 saved, same as terminal; 4 flagged as copied from another site |
| LinkedIn | ⏳ | ⏳ |
| Shine | ⏳ | ⏳ |
| Foundit | ⏳ | ⏳ |
| Govt portal (AICTE) | ✅ 06:44 (after the fix) — 165 read, **17 kept**, incl. **5 Indian Army internships** (HQ Southern Command ×3, Central Command, Western Command, ₹30,000–75,000); 90 unpaid dropped; training sellers flagged ("Master Artificial Intelligence", "Machine Learning with Python", 100–200 openings) | ✅ 06:48 — re-run after the fix saved 8 more: **17** on the dashboard, same as terminal; 5 of them have org type Government (the Army posts), so the dashboard's "Government" filter shows them |
| Apna | ✅ 06:07 — 49 read, 12 kept (IQVIA, Apple, Micron, Novartis, Sprinklr…), no flags; one sales role ("Artificial Intelligence Sales Intern", ByteDance) passes the AI/ML rule on its title | ⏳ |

Dashboard settings now have one checkbox per site; the not-upgraded ones are listed separately and unticked.

## Summary

| # | Platform | `--source` | File | How it reads the site | Status |
|---|---|---|---|---|---|
| 1 | Internshala | `internshala` | `sites/internshala.py` | Playwright + HTML | ✅ |
| 2 | Unstop | `unstop` | `sites/unstop.py` | Playwright + site's JSON API (HTML fallback) | ✅ |
| 3 | Naukri | `naukri` | `sites/naukri.py` | Playwright (visible Chrome) + HTML + schema.org JSON on detail pages | ✅ |
| 4 | LinkedIn (guest search) | `linkedin` | `sites/linkedin.py` | LinkedIn's guest job API (HTML cards) | ✅ |
| 5 | Shine | `shine` | `sites/shine.py` | Playwright + HTML (server-rendered) + schema.org JSON on job pages | ✅ |
| 6 | Foundit | `foundit` | `sites/foundit.py` | Visible Chrome + Foundit's JSON endpoints | ✅ |
| 7 | Apna | `apna` | `sites/apna.py` | Playwright + HTML (server-rendered) + schema.org JSON on job pages | ✅ |
| 8 | Cutshort | `cutshort` | `sites/misc_india.py` | Playwright + HTML | 🔴 |
| 9 | We Work Remotely (search page) | `international` | `sites/international.py` | Playwright + HTML | 🔴 |
| 10 | Remotive (RSS) | `remotive` | `sites/rss_feeds.py` | RSS feed, no selectors | 🔴 feed URL check only |
| 11 | We Work Remotely (RSS) | `weworkremotely` | `sites/rss_feeds.py` | RSS feed, no selectors | 🔴 feed URL check only |
| 12 | DuckDuckGo search | `search` | `sites/search_engine.py` | `ddgs` package, no selectors | 🔴 package check only |
| 13 | Universities (DuckDuckGo) | `universities` | `sites/universities.py` | `ddgs` package, no selectors | 🔴 package check only |
| 14 | Big tech career pages | `bigtech` | `sites/bigtech.py` | Adds a "go check this page" link | ⚪ |
| 15 | Government portal (AICTE National Internship Portal) | `government` | `sites/government.py` | Portal's public JSON endpoint | 🟡 |
| 16 | Niche boards / aggregators | `niche`, `aggregators` | `sites/niche.py` | Adds a "go check this page" link | ⚪ |

---

## 1. Internshala ✅

URL: `https://internshala.com/internships/artificial-intelligence-ai,data-science,deep-learning,machine-learning,natural-language-processing-nlp-internship/` (pages: `page-2/`, `page-3/` …)
Checked on the live site: 12 Oct 2026.

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `div.individual_internship` | `div.individual_internship[internshipid]` | ✅ found 50 per page |
| Title | `h3.job-internship-name` | `h2.job-internship-name a.job-title-href` | ❌ old one gone, fixed |
| Company | `p.company-name` | `p.company-name` | same |
| Location | `div#location_names` / `.loc_container a` | `.row-1-item.locations` (home icon `i.ic-16-home` = work from home) | ❌ old one gone, fixed |
| Start date | `div.item_body` (1st) | not on the card any more; detail page `#start-date-first` | ❌ fixed |
| Duration | `div.item_body` (2nd) | `.row-1-item` that contains `i.ic-16-calendar` | ❌ old one gone, fixed |
| Stipend | `span.stipend` | `span.stipend` | same |
| Link | `a` inside title / `a.view_detail_button` | card attribute `data-href` | ❌ fixed |
| Skills | not read | `.job_skills .job_skill` | new |
| Posted | not read | `.color-labels span` ("2 days ago") | new |
| Part time | not read | `.gray-labels span` | new |
| Last page | "fewer than 40 cards" | `input#isLastPage` value `1` | ❌ page 1 has 50, later pages 40; fixed |
| Employer activity (detail page) | not read | `.activity_container .activity` (hiring since / posted / hired) | new, used by `genuine.py` |
| Openings (detail page) | not read | `.section_heading` "Number of openings" → next element | new |

**Laptop test, 12 Oct 2026, 00:43:** 393 listings scraped from 10 pages, 146 of 147 detail pages read, 0 failures.
With the tighter AI/ML rule (below) the same data gives **81 kept**.
**Laptop test 2, 01:27, latest code:** 393 scraped, **81 kept** (confirmed, same as the estimate), 80 of 81 detail pages read. Flags on kept listings: 13 new employers with no hires yet, 5 very short, 5 "posts a lot, hires few", 1 commission/performance pay. 264 were not AI/ML, 21 unpaid, 21 under ₹5,000, 4 had excluded title words and 2 were mass programmes (Reducate.ai: 21,755 people "hired" from 1,189 posts).

What the first run taught us: about half of the 147 kept listings were not AI/ML at all (Digital Marketing, Graphic Design, HR, Video Editor) and got in only because Internshala tags them with the skill "Artificial intelligence". Now a listing needs AI/ML in the title, or at least two real ML skill tags (Machine Learning, Deep Learning, NLP, PyTorch, OpenCV …).

No listing on Internshala mentioned a fee. That fits Internshala's rule against charging candidates, but it also means the fee check has not been proven on real data yet.

## 2. Unstop ✅

Checked on the live site: 12 Oct 2026.

**The real problem was the URLs, not the selectors.** Both kinds of old URL (`?domain=tech&specialization=ai-ml` and `?query=machine+learning`) now redirect to `https://unstop.com/internship?oppstatus=open` and the filter is lost. So the old scraper read the same ~20 unfiltered cards (Social Media Marketing, Telesales …) seven times. The page only renders about 20 cards at a time.

**New approach:** Unstop's own page loads its list from a public JSON API. We call that API from inside the page (same as the site does) and filter for AI/ML ourselves:
`/api/public/opportunity/search-result?opportunity=internships&oppstatus=open&per_page=250&page=N`
On 12 Oct it returned 590 open internships, each with the full description, skills and stipend. Its `searchTerm` parameter is unreliable ("Machine Learning" returned 2 unrelated results), so we don't use it.

| Field | Old selector | New source (API field) | HTML fallback | Status |
|---|---|---|---|---|
| URL | 7 filtered URLs | API above, all open internships | `https://unstop.com/internships` | ❌ old URLs lose the filter, fixed |
| Card | `a.item` | each item in `data.data` | `a.item` | old selector still works |
| Link | card `href` | `public_url` | card `href` | still works |
| Title | `h3` | `title` | `h3` | still works |
| Company | `p` after the `h3` | `organisation.name` | `p` | still works |
| Location | `span.job_location` | `jobDetail.type` (wfh / hybrid / in_office) + `locations[].city` | `span.job_location` | still works |
| Stipend | `.cash_widget strong` | `jobDetail.min_salary` / `max_salary` / `paid_unpaid` / `show_salary` | `.cash_widget` | ❌ old one read only "12 K -" of "12 K - 15 K/Month", fixed |
| Skills | not read | `required_skills[].skill_name` | — | new |
| Description | not read | `details` (HTML), used by the fee check | — | new |
| Deadline | not read | `end_date` | — | new |
| Closed | text "closed/expired" on the card | `status` = LIVE and `regnRequirements.reg_status` = STARTED | text check | fixed |

**Laptop test, 12 Oct 2026, 01:07:** 3 API pages, 589 open internships read in 26 seconds, **16 kept**. Dropped: 542 not AI/ML, 16 "Lead Generation" titles, 11 "Manager" titles, 3 unpaid, 1 senior. Flags on kept: 3 with no stated stipend (Zycus ×2, Sprinto), 1 "performance-based stipend" (VEYRA AI, whose description also says applications go to its own website). No real fee demand was found in the 590 descriptions; the 8 that mention fees all say "no registration fee" or talk about the employer's own business, and the check correctly ignores them. New soft flag from Unstop data: pay that depends on commission or "performance".

Risk: this is an internal API, not a promised one. If it changes, the scraper logs a warning and falls back to the ~20 cards on the page.

## 3. Naukri ✅

URL: `https://www.naukri.com/ai-ml-internship-jobs-in-india?qcstipend=0To10&qcstipend=10To20&qcstipend=20To30&qcstipend=30To40&qcstipend=40To50` (paid internships only)
Checked on the live site: 12 Oct 2026. The page is built in the browser (the raw HTML has no cards), so Playwright is needed.

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `.srp-jobtuple-wrapper` | same (`data-job-id` attribute = stable id) | still works |
| Title + link | `a.title` | same | still works |
| Company | `a.comp-name` | same (+ rating `a.rating .main-2`) | still works |
| Location | `span.locWdth` | same | still works |
| Stipend | `span` **next to** `span.ni-job-tuple-icon-srp-rupee` | `span` **inside** it: `.ni-job-tuple-icon-srp-rupee span` | ❌ old one always empty, fixed |
| Duration | (not read) | `.ni-job-tuple-icon-srp-duration span` | new |
| Experience | `span.expwdth` | not on internship cards any more (kept for job cards) | ❌ gone |
| Skills | `ul.tags-gt li` | not on internship cards; read from the detail page instead | ❌ gone |
| Start | (not read) | `.job-post-day` ("Starts within 1 month") | new |
| Pages | page 1 only (20 of 594) | click `#lastCompMark a:has-text('Next')` | ❌ fixed |
| Detail page | (not read) | `script[type="application/ld+json"]` JobPosting: description, skills, datePosted, validThrough | new |
| Openings / applicants | (not read) | `[class*=styles_jhc__stat]` | new |

What we found:
- 531 of the 594 "AI ML internship" results are marked **Unpaid**. Some of these are probably not really unpaid: Tower Research Capital's AI/ML intern post says "Unpaid" but is a copied post. We can't check the real pay, so we ask Naukri for paid ones only: 59 results, 3 pages.
- Many posts say *"This job posting has been aggregated from external source"*. Naukri copied them from somewhere else. We keep them but add the flag "Copied by the portal from another site, so confirm on the company's own page".
- Loading page 2 or 3 directly with the filter in the URL drops the filter (it showed 0 results), so the scraper clicks "Next" like a person.
- Naukri's own job API answers `recaptcha required`, so we don't use it.
- **Laptop test 1 (01:17): blocked.** Headless Chromium got no job cards in 20 s. Naukri now runs in a visible window of the installed Google Chrome (falls back to Playwright's Chromium), without a fake user agent. If a check appears, the scraper waits 60 s for you to solve it, and saves `test_output/naukri_blocked.png` + `.html` so we can see what Naukri showed.
- **Laptop test 2 (01:50, visible Chrome): passed.** 3 pages, 58 paid listings, **15 kept**, 15 detail pages read; 4 kept posts are flagged as copied from another site. One earlier web run stopped after page 2 ("page 3 did not load"), so the Next-page step can be flaky.
- CSS classes on the detail page are hashed (`styles_jhc__stat__PgY67`) and change on every Naukri release, so we read the schema.org JSON block instead, plus partial class matches.

## 4. LinkedIn (guest search) ✅

Checked on the live site: 12 Oct 2026.

**The real problem: the old URL now hits a sign-up wall.** `https://www.linkedin.com/jobs/search/?keywords=…` redirects a logged-out visitor to `/authwall` ("Join LinkedIn"), so the old scraper found 0 cards. The card selectors themselves still work, on LinkedIn's guest API:

- Search: `/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=…&location=…&f_JT=I&f_E=1&start=0,10,…` (10 cards per call)
- Details: `/jobs-guest/jobs/api/jobPosting/<id>` (description, employment type, industry, applicants)

| Field | Old selector | New selector | Status |
|---|---|---|---|
| URL | `/jobs/search/?keywords=…` | guest search API above | ❌ authwall, fixed |
| Card | `div` class containing `base-card` | `div.base-card` (id in `data-entity-urn`) | still works |
| Title | `h3.base-search-card__title` | same | still works |
| Company | `h4.base-search-card__subtitle` | same | still works |
| Location | `span.job-search-card__location` | same | still works |
| Link | `a.base-card__full-link` | same (tracking params removed) | still works |
| Posted | (not read) | `time[datetime]` | new |
| Stipend | made up: 5000 INR / 1500 USD "Check Listing" | `.job-search-card__salary-info` if present, else empty | ❌ old one invented pay, fixed |
| Popups | `button[action-type='ACCEPT']`, `button.modal__dismiss` | not needed with the API | removed |
| Description, employment type, industry, applicants | (not read) | `.show-more-less-html__markup`, `.description__job-criteria-item`, `.num-applicants__caption` | new |

What we found in one live search ("machine learning internship", India, 10 cards):
- "Sparks To Ideas", an "IT training" company in the *Staffing and Recruiting* industry, posted the same "Machine Learning Internship" in Amreli and in Porbandar, while the description says the work is on-site in Ahmedabad. The post ends with "This job is provided by Shine.com". New flags for this: **Same post repeated in N locations** (3 or more, works for every portal) and **Copied by the portal from another site**.
- "Applied Scientist" (Meril) shows up under the Internship filter; our "must say intern" rule drops it.

Limits: LinkedIn rate-limits guests. The scraper runs up to 65 searches × 2 pages and at most 60 detail calls, waits 20 s on HTTP 429/999, and if it is refused again stops LinkedIn and keeps what it has.

**Laptop test, 12 Oct 02:12–02:20:** 65 searches, **854 unique cards, 339 kept** (60 in India; the rest in Singapore, Canada, USA, Europe …). Dropped: 230 not AI/ML, 208 not labelled as internships, 68 PhD-only. LinkedIn answered HTTP 429 four times; each time the scraper waited and carried on. Flags on kept posts: 2 "pay depends on commission or performance" (Devryxa, Vortenza Systems).

**Lesson from this run:** the first version of "Same post repeated in N locations" also hit DoorDash, Amazon, Qualcomm, Crowe and Kinaxis, which normally post one internship in several big cities. It now fires only when all the places are in one state (Sparks To Ideas: Amreli, Porbandar, Gandhinagar, Surendranagar, all Gujarat) or a copy of the post is known to be aggregated or from a staffing firm. On the same 854 cards it now flags only Sparks To Ideas.

## 5. Shine ✅

URL: `https://www.shine.com/job-search/ai-machine-learning-internship-jobs` (page N: `…-jobs-N`). Checked on the live site: 12 Oct 2026. Code moved to `sites/shine.py`.

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `div` class matching `jobCardNova_bigCard` | `article[class*="result-card_card"]` (schema.org ListItem) | ❌ old one gone (0 on the page), fixed |
| Link | first `a` in the card | `meta[itemprop="url"]` (fallback `a[class*="result-card_hit"]`) | ❌ fixed |
| Title | `h3` | `h3[itemprop="name"]` | still an h3 |
| Company | `span` matching `jobCardNova_bigCardTopTitleName` | `[class*="result-card_company"]` | ❌ fixed |
| Location | `div` matching `jobCardNova_bigCardCenterListLoc` | 3rd `[class*="result-card_meta-text"]` | ❌ fixed |
| Experience / salary | (not read) | 1st and 2nd `[class*="result-card_meta-text"]` | new (cards needing 3+ years are skipped) |
| Skills | (not read; old code wrote "AI/ML" on every card) | `[class*="result-card_skills-item"]` | new |
| Posted | (not read) | `[class*="result-card_posted"]` | new |
| Job page | (not read) | `script[type="application/ld+json"]` JobPosting: description, skills, dates, industry | new |

Class names are CSS-module hashes (`result-card_role__tUHBe`); the part after `__` changes on Shine releases, so we match the prefix only.

What we found: Shine's search is loose (7,132 results) and full of training institutes. Example: Maxgen Technologies' "MACHINE LEARNING AI INTERNSHIP AT AHMEDABAD" says *"machine learning program with job placement … Career oriented Program"*, and its "Generative Ai Internship in Pune" lists 8 towns (Yavatmal, Akola, Pune, Amravati, Nanded, Satara, Jalna, Sangli). New flags, for every portal: **Sounds like a training programme sold as an internship** (placement guarantee / certification programme / course-fee wording) and **One post listed for N towns** (6 or more). No fee was written in the description we read.

Scope: first 5 pages (100 cards, sorted by relevance), at most 80 job pages read.

**Laptop test, 12 Oct 02:28:** 5 pages, 85 cards, 40 job pages read, 60 kept. The kept list showed four problems, fixed the same night:
1. Two posts said "(Unpaid Internship)" and "(Non Paid)" in the title but were kept, because Shine hides pay ("Not Disclosed"). Posts that say unpaid in the title or description are now dropped on every portal (this also drops one LinkedIn post, "AI engineering unpaid internship").
2. "1.0 - 2.0 Lakh/Yr" was read as ₹1/month and the post was dropped. Lakh amounts are now converted (≈ ₹8,333/month).
3. Every card got "Stipend amount not stated" because almost every Shine card says "Not Disclosed". That flag is now skipped on Shine (and LinkedIn), where it carries no information.
4. "Data Science & Generative AI Training & Internship" was not flagged; "training & internship" wording now counts as a training programme. Job pages read raised from 40 to 80.

Same data with the fixes: **59 kept**, 2 dropped as unpaid; flags: one post listed for 7, 8 and 10 towns (Maxgen ×2, Sparks To Ideas), 1 training programme.

## 6. Foundit ✅

Checked on the live site: 12 Oct 2026. Code moved to `sites/foundit.py`.

**The old URL was broken by Foundit itself.** `https://www.foundit.in/srp/results?query=ai+ml+internship` shows "1 result", because the page passes the `+` signs literally to its own search ("ai+ml+internship"). The old selectors (`job-tuple`, `company-name`, `details`) match nothing.

**New approach:** the page loads results from `/middleware/jobsearch?sort=1&limit=60&query=<words>` and descriptions from `/middleware/jobdetail/<id>`. We call both from inside a real Chrome window (Foundit uses Akamai bot checks, like Naukri), for 7 AI/ML queries. Results per query on 12 Oct: 1–47.

| Field | Old selector | New source (JSON field) | Status |
|---|---|---|---|
| Card | `div` matching `job-tuple` | `jobSearchResponse.data[]` | ❌ fixed |
| Title | `h3` | `title` | ❌ fixed |
| Company | `span` matching `company-name` | `companyName` | ❌ fixed |
| Location | `div` matching `details` | `locations` | ❌ fixed |
| Link | first `a` | `seoJdUrl` | ❌ fixed |
| Stipend | (not read) | `minimumSalary/maximumSalary.absoluteMonthlyValue` ("0-0" = hidden) | new |
| Skills, experience, posted, deadline, applicants | (not read) | `skills`, `exp`, `postedBy`, `closedAt`, `totalApplicants` | new |
| Posted by | (not read) | `employerTypes` ("Consultant" = recruiter) | new |
| Description | (not read) | `/middleware/jobdetail/<id>` → `jobDetailResponse.description` | new |

The endpoint also returns the recruiter's name and phone number; we never store them.

What we found: Sparks To Ideas again, now as "Free AI/ML Internship", posted by a *Consultant*, ₹4,167–8,333/month (dropped: under ₹5,000) and in 4 more copies under "machine learning internship". Maxgen lists "DATA SCIENCE INTERNSHIP" at ₹2.5–5 lakh a year. New flag: **Posted by a recruiter or consultant, not the company itself**.

**Laptop test, 12 Oct 05:51:** 7 searches, 108 posts, 60 descriptions read, 88 kept. But **about 50 of the 88 were Maxgen Technologies**: the same "DATA SCIENCE INTERNSHIP AT PUNE / AHMEDABAD" posted again and again with different three-town lists, some copies with the company name hidden as "**********". New rule for every portal: when one company posts the same internship (same first two title words) 3 or more times, it is shown once with "(+N more)" places and every warning found on any copy; 6 or more copies also get **Same company posted N copies of this internship**. Hidden names get **Company name hidden**. Same data after the rule: **38 kept**, Maxgen's 39 data-science copies are one card. Different roles from one company (Codeatrix on Internshala) are not merged.

## 7. Apna ✅

Checked on the live site: 12 Oct 2026. Code moved to `sites/apna.py`.

**The old URL ignores its filters.** `https://apna.co/jobs?category=internship&q=ai+ml` lists all 81,222 jobs (first result "Assistant General Manager"). The search that works is `/jobs?search=true&text=ai%20ml%20internship` (42 results), page N with `&page=N`. We run 4 AI/ML queries, 2 pages each.

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `a[href*=/job/]` holding `[data-testid=job-title]` | `a[data-testid="job-card"]` | ❌ fixed |
| Title | `[data-testid=job-title]` | `h2` in the card | ❌ gone, fixed |
| Company | `[data-testid=company-title]` | `span` right after the `h2` | ❌ gone, fixed |
| Location | `[data-testid=job-location]` | `span` next to `svg[data-testid="LocationOnIcon"]` | ❌ gone, fixed |
| Pay | `[data-testid=job-salary]` | `span` next to `svg[data-testid="PaymentsIcon"]` | ❌ gone, fixed |
| Work type | (not read) | chips: "Work from Office", "Full Time", "Freshers only" | new |
| Job page | (not read) | `script[type="application/ld+json"]` JobPosting: description, dates, industry | new |

Trap: every card row has an inline `<style>` tag, so reading the whole row gives ".css-q7mezt{user-select:none…}Kochi". We remove `<style>` tags and read only the span.

What we saw: this search returns mostly big-company internships (IQVIA, HPE, Apple, Micron, Sprinklr, LinkedIn), nearly all with pay "Not disclosed". **Laptop test, 12 Oct 06:07:** 49 cards from 4 searches, 12 kept, 37 dropped (30 not AI/ML, 4 not internships, 3 PhD-only).

## 8. Cutshort 🔴

URL: `https://cutshort.io/jobs/ai-ml?type=internship`

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `div` class matching `job-card` | | 🔴 |
| Title | `div` class matching `title` | | 🔴 |
| Company | `div` class matching `company` | | 🔴 |
| Location | `div` class matching `location` | | 🔴 |
| Link | first `a` in the card | | 🔴 |

Check: whether the list is visible without logging in.

## 9. We Work Remotely, search page 🔴

URL: `https://weworkremotely.com/remote-jobs/search?term=internship+machine+learning`

| Field | Old selector | New selector | Status |
|---|---|---|---|
| Card | `li.feature` | | 🔴 |
| Title | `h3.new-listing__header__title` (fallback `span.title`) | | 🔴 |
| Company | `p.new-listing__company-name` (fallback `span.company`) | | 🔴 |
| Link | `a[href]` starting with `/remote-jobs/` | | 🔴 |

Check: `li.feature` may only match featured (paid) posts, not all results.

## 10–11. RSS feeds 🔴 (no selectors)

- Remotive: `https://remotive.com/remote-jobs/feed?category=software-dev&keywords=machine+learning`, `…category=data&keywords=machine+learning`, `…category=software-dev&keywords=artificial+intelligence`
- We Work Remotely: `https://weworkremotely.com/categories/remote-programming-jobs.rss`, `…/remote-data-science-and-analytics-jobs.rss`

Check: each feed still returns items. Code issue: in `rss_feeds.py` the function `scrape_linkedin` actually reads Remotive and `scrape_indeed` actually reads We Work Remotely; rename them so nobody gets confused.

## 12–13. DuckDuckGo search and universities 🔴 (no selectors)

Uses the `ddgs` package (falls back to `duckduckgo_search`). Check: the package still returns results and is not rate-limited; `universities.py` runs 54 queries in one go.

**Web run on the laptop, 12 Oct 01:52 (not asked for yet, but it ran):** `universities` saved 52 "matches" to `internships.csv`. Most are **not internship posts**: blog lists ("15 AI and Machine Learning Internship Programs"), guides ("Google DeepMind AI Research Internship 2026: Complete Guide"), a GitHub list, a 2025 PDF, an Internshala category page, a Foundit career-advice article. Only a handful are direct job posts (NVIDIA, SmartRecruiters, Wellfound, ByteDance, iCIMS). These must not appear in a "genuine internships" list until there is a "direct job post only" rule. `government` saved 1 placeholder ("AI/ML Internship Opportunities (AICTE Internship Portal)").

## 15. Government portal: AICTE National Internship Portal 🟡

Checked on the live site: 12 Oct 2026. `https://internship.aicte-india.org` (Government of India, Ministry of Education).

**The old code never scraped a government internship.** For AICTE, C-DAC and DRDO it checked whether the page contained a word like "machine learning" and wrote one made-up card per portal ("AI/ML Internship Opportunities (AICTE)", stipend "Govt Norms" = ₹5,000).

**New approach:** the portal loads its listings from `/api/v1/catalogue/internships?q=<words>&page=N&pageSize=60`. We run 7 AI/ML searches plus every listing from the Government, Army and TULIP categories. Each item says who posted it (`category`), whether the portal verified the employer, stipend, deadline, openings and description.

What is on the portal (12 Oct): 1,236 live internships: 785 MSME, 390 Corporate, 34 Army, 18 NGO, 6 TULIP (urban missions), 3 "Government". The AI/ML listings are mostly small firms, many selling training: "Artificial Intelligence Internship with Guaranteed Certification - Www.applymyinternship.com", "Python - Ai - Ml - Data Science - Genai - Web Development Internship" (unpaid), "Fullstack Developer Training and Internship" with 70 openings. New flags: **Employer not verified by the portal**, **N openings for one internship** (50+), **Advertises another website in the title**, and "guaranteed certification" now counts as a training programme. Cards from Government/Army/TULIP posters get `org_type = Government`.

Not possible to scrape: C-DAC's dashboard on the portal shows only statistics (1,812 posted, no listings), and DRDO's internship scheme is run lab by lab with no list.

**Laptop test, 12 Oct:** first run (06:21) failed on every call because the portal answers in Brotli when it is offered and Python had no Brotli decoder; fixed by sending gzip/deflate only. Second run (06:38): 165 listings, 9 kept, including two Indian Army (HQ Southern Command) internships: "Artificial Intelligence and Machine Learning Intern" (up to ₹30,000) and "AI Enabled Geospatial Terrain Analysis Intern" (up to ₹75,000). 78 were unpaid.

## 14, 16. Link-only sources ⚪

`bigtech.py` (Microsoft, Google, Meta, Apple, NVIDIA) and `niche.py` (AIJobs.net, MLOps Community, DeepLearning.AI, KDnuggets, SimplyHired, CareerJet, Talent.com) do not read any listing. They add one placeholder record per site saying "go check this page". These are not internships, so they stay unticked on the dashboard until rebuilt.

---

## Code problems found so far (not selectors)

| Problem | Where | Status |
|---|---|---|
| `NameError: scrapers` at the end of every run | `scraper.py` | ✅ fixed |
| `--source` crashed (`specific_source` was not a parameter) | `scraper.py` | ✅ fixed |
| `--dry-run` only printed a count | `scraper.py` | ✅ now prints kept/dropped with reasons |
| Skills like "Leadership" rejected real listings (word `lead`) | `filters.py` | ✅ exclusions now check the title only |
| A single "Artificial intelligence" skill tag let marketing/HR roles in | `filters.py` | ✅ title match or 2 real ML skills |
| "Competitive stipend" was treated as unpaid | `filters.py` | ✅ fixed |
| `schedule` package missing from requirements | `requirements.txt` | ✅ added |
| `wait_for_human` is defined twice | `scraper_utils.py` | ✅ removed the copy |
| Naukri `stipend_numeric` always 0 (and stipend text always empty) | `sites/naukri.py` | ✅ fixed |
| RSS functions named after the wrong sites | `sites/rss_feeds.py` | 🔴 |
| Link-only sources mixed in with real listings | `bigtech.py`, `government.py`, `niche.py` | 🔴 decide: remove or rebuild |

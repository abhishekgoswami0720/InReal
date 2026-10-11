"""
LinkedIn internship scraper (no login).

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The public search page https://www.linkedin.com/jobs/search/?keywords=...
    now redirects a logged-out visitor to the sign-up wall (/authwall), so the
    old scraper found 0 cards.
  - LinkedIn's guest pages still load their results from
        /jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=..&location=..&f_JT=I&f_E=1&start=N
    which answers with the same job cards (10 per call). The card selectors
    (div.base-card, h3.base-search-card__title, h4.base-search-card__subtitle,
    span.job-search-card__location, a.base-card__full-link) still work there.
  - Each job's details come from /jobs-guest/jobs/api/jobPosting/<id>:
    description, employment type, industry, applicants, and a line like
    "This job is provided by Shine.com" when LinkedIn copied the post.
  - The old code wrote a made-up stipend (5000 INR / 1500 USD, "Check Listing")
    so every LinkedIn post passed the stipend rule. LinkedIn cards don't show
    pay, so we now leave the stipend empty and say so.
"""
import hashlib
import re
import urllib.parse
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score, internship_rejection_reason
from scraper_utils import get_playwright_stealth_args, human_delay

# ── Every major location × every major AI/ML keyword ─────────────────────────
# LinkedIn's f_JT=I = Internship job type, f_E=1 = Entry level
SEARCH_CONFIGS = [
    # ── WORLDWIDE BROAD ───────────────────────────────────────────────────────
    ("machine learning internship",               "Worldwide",      "Global · ML"),
    ("artificial intelligence internship",        "Worldwide",      "Global · AI"),
    ("deep learning internship",                  "Worldwide",      "Global · DL"),
    ("data science internship",                   "Worldwide",      "Global · DS"),
    ("computer vision internship",                "Worldwide",      "Global · CV"),
    ("natural language processing internship",    "Worldwide",      "Global · NLP"),
    ("AI research intern",                        "Worldwide",      "Global · Research"),
    ("generative AI internship",                  "Worldwide",      "Global · GenAI"),
    ("large language model internship",           "Worldwide",      "Global · LLM"),
    ("reinforcement learning internship",         "Worldwide",      "Global · RL"),
    ("robotics AI internship",                    "Worldwide",      "Global · Robotics"),
    ("machine learning engineer intern",          "Worldwide",      "Global · MLE"),

    # ── INDIA ─────────────────────────────────────────────────────────────────
    ("AI ML internship",                          "India",          "India · AI/ML"),
    ("machine learning internship",               "India",          "India · ML"),
    ("data science internship",                   "India",          "India · DS"),
    ("artificial intelligence internship",        "India",          "India · AI"),
    ("deep learning internship",                  "India",          "India · DL"),
    ("computer vision internship",                "India",          "India · CV"),
    ("NLP internship",                            "India",          "India · NLP"),
    ("AI research intern",                        "India",          "India · Research"),
    ("machine learning internship",               "Bangalore, India",   "Bangalore · ML"),
    ("machine learning internship",               "Hyderabad, India",   "Hyderabad · ML"),
    ("machine learning internship",               "Mumbai, India",      "Mumbai · ML"),
    ("machine learning internship",               "Delhi, India",       "Delhi · ML"),
    ("machine learning internship",               "Pune, India",        "Pune · ML"),
    ("AI internship",                             "Chennai, India",     "Chennai · AI"),
    ("research intern AI",                        "India",          "India · Uni Research"),

    # ── UNITED STATES ─────────────────────────────────────────────────────────
    ("machine learning intern",                   "United States",  "USA · ML"),
    ("AI research intern",                        "United States",  "USA · Research"),
    ("deep learning intern",                      "San Francisco Bay Area", "SF Bay · DL"),
    ("machine learning intern",                   "New York, United States", "NYC · ML"),
    ("AI intern",                                 "Seattle, Washington, United States", "Seattle · AI"),
    ("machine learning intern",                   "Boston, Massachusetts, United States", "Boston · ML"),

    # ── EUROPE ────────────────────────────────────────────────────────────────
    ("machine learning internship",               "Europe",         "Europe · ML"),
    ("AI research intern",                        "Europe",         "Europe · Research"),
    ("machine learning intern",                   "United Kingdom", "UK · ML"),
    ("AI ML internship",                          "Germany",        "Germany · AI/ML"),
    ("machine learning internship",               "France",         "France · ML"),
    ("AI research intern",                        "Netherlands",    "Netherlands · AI"),
    ("machine learning intern",                   "Switzerland",    "Switzerland · ML"),
    ("AI internship",                             "Sweden",         "Sweden · AI"),
    ("machine learning internship",               "Denmark",        "Denmark · ML"),
    ("AI research intern",                        "Finland",        "Finland · AI"),  # Aalto area
    ("machine learning intern",                   "Netherlands",    "Netherlands · ML"),
    ("AI intern",                                 "Spain",          "Spain · AI"),
    ("machine learning intern",                   "Italy",          "Italy · ML"),
    ("AI research intern",                        "Belgium",        "Belgium · AI"),
    ("deep learning intern",                      "Austria",        "Austria · DL"),

    # ── ASIA-PACIFIC ──────────────────────────────────────────────────────────
    ("machine learning intern",                   "Singapore",      "Singapore · ML"),
    ("AI internship",                             "Singapore",      "Singapore · AI"),
    ("machine learning intern",                   "Japan",          "Japan · ML"),
    ("AI research intern",                        "South Korea",    "Korea · AI"),
    ("machine learning internship",               "China",          "China · ML"),
    ("AI intern",                                 "Hong Kong",      "HK · AI"),
    ("machine learning internship",               "Australia",      "Australia · ML"),
    ("AI research intern",                        "Australia",      "Australia · Research"),
    ("machine learning intern",                   "New Zealand",    "NZ · ML"),

    # ── CANADA ────────────────────────────────────────────────────────────────
    ("machine learning intern",                   "Canada",         "Canada · ML"),
    ("AI research intern",                        "Toronto, Canada","Toronto · AI"),
    ("machine learning internship",               "Montreal, Canada","Montreal · ML"),  # Mila area
    ("deep learning intern",                      "Vancouver, Canada","Vancouver · DL"),

    # ── MIDDLE EAST & AFRICA ──────────────────────────────────────────────────
    ("machine learning internship",               "United Arab Emirates", "UAE · ML"),
    ("AI internship",                             "Saudi Arabia",   "Saudi · AI"),
    ("machine learning intern",                   "South Africa",   "SA · ML"),
    ("AI research intern",                        "Israel",         "Israel · AI"),

    # ── LATIN AMERICA ─────────────────────────────────────────────────────────
    ("machine learning internship",               "Brazil",         "Brazil · ML"),
    ("AI internship",                             "Mexico",         "Mexico · AI"),

    # ── REMOTE (ANYWHERE) ─────────────────────────────────────────────────────
    ("machine learning intern",                   "Remote",         "Remote · ML"),
    ("AI research intern",                        "Remote",         "Remote · Research"),
    ("deep learning intern",                      "Remote",         "Remote · DL"),
    ("data science intern",                       "Remote",         "Remote · DS"),
]

SEARCH_API = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
              "?keywords={kw}&location={loc}&f_JT=I&f_E=1&start={start}")
DETAIL_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
PAGES_PER_SEARCH = 2      # 10 cards per page
MAX_DETAILS = 60          # detail pages per run, to stay under LinkedIn's rate limit

SEL = {
    "card": "div.base-card",
    "title": "h3.base-search-card__title",
    "company": "h4.base-search-card__subtitle",
    "location": "span.job-search-card__location",
    "link": "a.base-card__full-link",
    "date": "time[datetime]",
    "salary": ".job-search-card__salary-info",
    # detail
    "d_desc": ".show-more-less-html__markup, .description__text",
    "d_criteria": ".description__job-criteria-item",
    "d_criteria_key": ".description__job-criteria-subheader",
    "d_criteria_val": ".description__job-criteria-text",
    "d_applicants": ".num-applicants__caption",
    "d_posted": ".posted-time-ago__text",
}
PROVIDED_BY_RE = r"This job is provided by\s+(.{2,60}?)\.?(?:\s+Show more|\s*$)"
INDIA_WORDS = ["india", "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai", "gurgaon", "noida"]


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def query_wanted(kw: str, loc: str, req_regions, req_topics) -> bool:
    """Same region/topic rules as the old scraper, so the dashboard checkboxes still work."""
    kw_l, loc_l = kw.lower(), loc.lower()
    is_india = "india" in loc_l
    is_remote = "remote" in loc_l or "anywhere" in loc_l
    is_worldwide = "worldwide" in loc_l
    is_europe = any(w in loc_l for w in ["europe", "kingdom", "germany", "france", "netherlands", "switzerland",
                                          "sweden", "denmark", "finland", "spain", "italy", "belgium", "austria"])
    is_usa = any(w in loc_l for w in ["united states", "bay area", "seattle", "boston", "york"])
    region = (("india" in req_regions and is_india) or ("usa" in req_regions and is_usa)
              or ("europe" in req_regions and is_europe) or ("remote" in req_regions and is_remote)
              or ("worldwide" in req_regions and (is_worldwide or not (is_india or is_usa or is_europe or is_remote))))
    if not region:
        return False
    if not req_topics:
        return True
    t = req_topics
    return any([
        "ai" in t and ("artificial intelligence" in kw_l or re.search(r"\bai\b", kw_l) or "robotics" in kw_l),
        "ml" in t and ("machine learning" in kw_l or "reinforcement" in kw_l),
        "ds" in t and "data science" in kw_l,
        "cv" in t and "computer vision" in kw_l,
        "nlp" in t and ("natural language" in kw_l or "nlp" in kw_l),
        "research" in t and "research" in kw_l,
        "llm/genai" in t and ("generative" in kw_l or "large language" in kw_l),
        "dl" in t and "deep learning" in kw_l,
    ])


def parse_search_html(html: str, label: str):
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select(SEL["card"]):
        try:
            title = _text(card.select_one(SEL["title"]))
            if not title:
                continue
            urn = card.get("data-entity-urn", "")
            job_id = urn.rsplit(":", 1)[-1] if urn else ""
            link_el = card.select_one(SEL["link"])
            link = (link_el.get("href", "") if link_el else "").split("?")[0]
            if not job_id:
                m = re.search(r"-(\d{6,})$", link)
                job_id = m.group(1) if m else ""
            location = _text(card.select_one(SEL["location"]))
            loc_l = location.lower()
            location_type = ("Remote" if "remote" in loc_l
                             else "India" if any(w in loc_l for w in INDIA_WORDS) else "International")
            salary = _text(card.select_one(SEL["salary"]))
            date_el = card.select_one(SEL["date"])
            records.append({
                "id": hashlib.md5(f"linkedin-{job_id or title + location}".encode()).hexdigest(),
                "job_id": job_id,
                "company_name": _text(card.select_one(SEL["company"])) or "Unknown",
                "role_title": title,
                "location": location,
                "location_type": location_type,
                "duration": "",
                "stipend": salary,
                "stipend_numeric": 0.0,
                "stipend_currency": "INR" if location_type == "India" else "USD",
                "stipend_hidden_by_site": not salary,
                "required_skills": "",
                "application_deadline": "",
                "apply_link": link,
                "source_platform": f"LinkedIn ({label})",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": "Research" if "research" in title.lower() else "Applied",
                "match_score": calculate_match_score(title, [], "Company", 0.0),
                "posted": date_el.get("datetime", "") if date_el else "",
                "description": "",
            })
        except Exception as e:
            logger.exception(f"LinkedIn: could not parse a card: {e}")
    return records


def parse_detail_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out = {}
    desc = _text(soup.select_one(SEL["d_desc"]))
    if desc:
        out["description"] = desc[:4000]
        m = re.search(PROVIDED_BY_RE, desc)
        if m:
            out["aggregated"] = True
            out["provided_by"] = m.group(1).strip()
    for item in soup.select(SEL["d_criteria"]):
        key = _text(item.select_one(SEL["d_criteria_key"])).lower()
        val = _text(item.select_one(SEL["d_criteria_val"]))
        if key and val:
            out[key.replace(" ", "_")] = val   # seniority_level, employment_type, industries, job_function
    out["applicants"] = _text(soup.select_one(SEL["d_applicants"]))
    return out


FETCH_JS = """async (url) => {
    const r = await fetch(url, {credentials: 'omit'});
    return {status: r.status, text: r.status === 200 ? await r.text() : ''};
}"""


def scrape_linkedin(config=None):
    config = config or {}
    req_regions = [r.lower() for r in (config.get("regions") or ["india", "worldwide", "usa", "europe", "remote"])]
    req_topics = [t.lower() for t in (config.get("topics") or [])]
    searches = [(kw, loc, label) for kw, loc, label in SEARCH_CONFIGS if query_wanted(kw, loc, req_regions, req_topics)]
    logger.info(f"LinkedIn: {len(searches)} searches selected by the dashboard settings")

    all_internships = []
    seen = set()
    rate_limited = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        # Any linkedin.com page gives us the right origin for fetch(); the authwall is fine
        in_page = True
        try:
            page.goto("https://www.linkedin.com/jobs", timeout=45000, wait_until="domcontentloaded")
        except Exception as e:
            logger.warning(f"LinkedIn page did not open ({e}); calling the API directly")
            in_page = False

        def fetch(url):
            if in_page:
                try:
                    return page.evaluate(FETCH_JS, url)
                except Exception as e:
                    logger.warning(f"LinkedIn in-page fetch failed ({e}); calling the API directly")
            resp = context.request.get(url, timeout=30000)
            return {"status": resp.status, "text": resp.text() if resp.status == 200 else ""}

        def get(url):
            nonlocal rate_limited
            for attempt in range(2):
                res = fetch(url)
                if res["status"] == 200:
                    return res["text"]
                if res["status"] in (429, 999) and attempt == 0:  # 999 = LinkedIn's "looks like a bot"
                    logger.warning(f"LinkedIn: HTTP {res['status']} (rate limit), waiting 20 s")
                    human_delay(20, 25)
                    continue
                if res["status"] in (429, 999):
                    rate_limited = True
                logger.warning(f"LinkedIn: HTTP {res['status']} for {url[:120]}")
                return None
            return None

        for kw, loc, label in searches:
            if rate_limited:
                break
            for page_no in range(PAGES_PER_SEARCH):
                url = SEARCH_API.format(kw=urllib.parse.quote(kw), loc=urllib.parse.quote(loc), start=page_no * 10)
                html = get(url)
                if not html:
                    break
                records = parse_search_html(html, label)
                new = [r for r in records if r["id"] not in seen]
                seen.update(r["id"] for r in new)
                all_internships.extend(new)
                logger.info(f"LinkedIn [{label}] page {page_no + 1}: {len(records)} cards, {len(new)} new")
                human_delay(1.0, 2.0)
                if len(records) < 10:
                    break

        wanted = [r for r in all_internships if internship_rejection_reason(r["role_title"], [], "linkedin") is None]
        wanted = wanted[:MAX_DETAILS]
        logger.info(f"LinkedIn: reading {len(wanted)} job details for the genuineness checks")
        for i, rec in enumerate(wanted, 1):
            if rate_limited or not rec["job_id"]:
                continue
            html = get(DETAIL_API.format(job_id=rec["job_id"]))
            if html:
                rec.update(parse_detail_html(html))
                rec["detail_checked"] = True
            if i % 10 == 0:
                logger.info(f"  ...{i}/{len(wanted)} details read")
            human_delay(0.8, 1.6)

        browser.close()

    if rate_limited:
        logger.warning(f"LinkedIn stopped early because of rate limiting; keeping {len(all_internships)} cards")
    logger.info(f"LinkedIn: {len(all_internships)} unique cards")
    return all_internships

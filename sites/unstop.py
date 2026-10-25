"""
Unstop internship scraper.

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - All 7 old URLs (?domain=tech&specialization=ai-ml, ?query=machine+learning, ...)
    now redirect to https://unstop.com/internship?oppstatus=open and the filter is
    lost, so the old scraper read the same ~20 unfiltered cards seven times.
  - The page only renders 18-20 cards at a time. The site's own front end loads
    them from a public JSON API:
        /api/public/opportunity/search-result?opportunity=internships&oppstatus=open
    which returns every open internship (590 on 12 Oct) with title, company,
    stipend, skills and the full description. We read that API, 250 per page,
    and do the AI/ML filtering ourselves (its searchTerm is unreliable:
    "Machine Learning" returned 2 unrelated results).
  - The HTML card selectors still work (a.item, h3, p, span.job_location,
    .cash_widget strong); they are kept as a fallback if the API stops answering.
"""
import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score
from scraper_utils import get_playwright_stealth_args, human_delay
from sites import budget

BASE = "https://unstop.com"
LIST_PAGE = "https://unstop.com/internships"
API = ("https://unstop.com/api/public/opportunity/search-result"
       "?opportunity=internships&oppstatus=open&per_page=250&page={page}")
MAX_PAGES = 20  # safety stop (3 pages of 250 on 12 Oct 2026)

SEL = {  # HTML fallback
    "card": "a.item",
    "title": "h3",
    "company": "p",
    "location": "span.job_location",
    "stipend": ".cash_widget",  # old: ".cash_widget strong" only got "12 K -" of "12 K - 15 K/Month"
}

FETCH_JS = """async (url) => {
    const r = await fetch(url, {headers: {Accept: 'application/json'}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
}"""


def _html_to_text(html: str) -> str:
    from sites._common import html_to_text
    return html_to_text(html, limit=100000)


def _stipend(job: dict):
    """Returns (display text, monthly number). Number 0 means not stated."""
    if (job.get("paid_unpaid") or "").lower() == "unpaid":
        return "Unpaid", 0.0
    lo, hi = job.get("min_salary"), job.get("max_salary")
    if not job.get("show_salary") or job.get("not_disclosed") or not (lo or hi):
        return "", 0.0
    lo = lo or hi
    hi = hi or lo
    per = "year" if job.get("pay_in") == "annually" else "month"
    text = f"₹ {lo:,.0f} /{per}" if lo == hi else f"₹ {lo:,.0f} - {hi:,.0f} /{per}"
    monthly = float(lo)
    if per == "year" and lo >= 60000:  # some "annually" posts are really monthly amounts
        monthly = round(lo / 12)
    return text, monthly


def parse_api_record(x: dict):
    """One API record -> our record, or None if it is closed."""
    reg = x.get("regnRequirements") or {}
    if x.get("status") != "LIVE" or reg.get("reg_status") not in (None, "STARTED"):
        return None

    job = x.get("jobDetail") or {}
    title = (x.get("title") or "").strip()
    company = ((x.get("organisation") or {}).get("name") or "Unknown").strip()

    cities = [l.get("city") for l in (x.get("locations") or []) if l.get("city")] or job.get("locations") or []
    work_type = job.get("type") or ""
    if work_type == "wfh":
        location, location_type = "Work from home", "Remote"
    else:
        location = ", ".join(cities) or "India"
        if work_type == "hybrid":
            location += " (Hybrid)"
        location_type = "India"

    stipend, stipend_numeric = _stipend(job)
    skills = [s.get("skill_name") or s.get("skill") for s in (x.get("required_skills") or [])]
    skills = [s for s in skills if s]
    public_url = x.get("public_url") or ""

    return {
        "id": hashlib.md5(f"unstop-{x.get('id')}".encode()).hexdigest(),
        "company_name": company,
        "role_title": title,
        "location": location,
        "location_type": location_type,
        "duration": "",
        "stipend": stipend,
        "stipend_numeric": stipend_numeric,
        "stipend_currency": "INR",
        "required_skills": ", ".join(skills),
        "application_deadline": (x.get("end_date") or "")[:10],
        "apply_link": f"{BASE}/{public_url.lstrip('/')}" if public_url else (x.get("seo_url") or ""),
        "source_platform": "Unstop",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
        "org_type": "Company",
        "role_type": "Research" if "research" in title.lower() else "Applied",
        "match_score": calculate_match_score(title, skills, "Company", stipend_numeric),
        "posted": (x.get("approved_date") or "")[:10],
        "part_time": job.get("timing") == "part_time",
        "description": _html_to_text(x.get("details"))[:4000],
    }


def parse_api_page(payload: dict):
    """Returns (records, last_page)."""
    data = payload.get("data") or {}
    records = [r for r in (parse_api_record(x) for x in data.get("data") or []) if r]
    return records, int(data.get("last_page") or 1)


def _parse_card_stipend(text: str) -> float:
    """'10 K/Month' -> 10000, '25,000' -> 25000."""
    text = (text or "").replace(",", "").upper()
    m = re.search(r"(\d+(?:\.\d+)?)\s*K", text)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"(\d+)", text)
    return float(m.group(1)) if m else 0.0


def parse_list_html(html: str):
    """Fallback: read the cards rendered on the list page."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select(SEL["card"]):
        h3 = card.select_one(SEL["title"])
        href = card.get("href", "")
        if not h3 or not href:
            continue
        text = card.get_text(" ", strip=True).lower()
        if "no longer accepting" in text or "expired" in text:
            continue
        title = h3.get_text(" ", strip=True)
        company_el = h3.find_next("p") or card.select_one(SEL["company"])
        loc_el = card.select_one(SEL["location"])
        location = loc_el.get_text(" ", strip=True) if loc_el else "India"
        stip_el = card.select_one(SEL["stipend"])
        stipend = stip_el.get_text(" ", strip=True) if stip_el else ""
        stipend_numeric = _parse_card_stipend(stipend)
        link = BASE + href if href.startswith("/") else href
        records.append({
            "id": hashlib.md5(f"unstop-{href.rstrip('/').split('-')[-1]}".encode()).hexdigest(),
            "company_name": company_el.get_text(" ", strip=True) if company_el else "Unknown",
            "role_title": title,
            "location": location,
            "location_type": "Remote" if "work from home" in location.lower() else "India",
            "duration": "",
            "stipend": stipend,
            "stipend_numeric": stipend_numeric,
            "stipend_currency": "INR",
            "required_skills": "",
            "application_deadline": "",
            "apply_link": link,
            "source_platform": "Unstop",
            "date_scraped": datetime.now().strftime("%Y-%m-%d"),
            "org_type": "Company",
            "role_type": "Research" if "research" in title.lower() else "Applied",
            "match_score": calculate_match_score(title, [], "Company", stipend_numeric),
            "posted": "",
            "description": "",
        })
    return records


def scrape_unstop():
    all_internships = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        # Open the real page first so the site sets its cookies, like a normal visit
        logger.info(f"Opening Unstop: {LIST_PAGE}")
        page.goto(LIST_PAGE, timeout=45000, wait_until="domcontentloaded")
        human_delay(1.0, 1.5)

        api_ok = False
        last_page = 1
        page_num = 1
        while page_num <= min(last_page, MAX_PAGES):
            url = API.format(page=page_num)
            try:
                # fetch() from inside the page, exactly like Unstop's own front end does
                payload = page.evaluate(FETCH_JS, url)
                records, last_page = parse_api_page(payload)
            except Exception as e:
                logger.warning(f"Unstop API page {page_num} failed: {e}")
                break
            api_ok = True
            new = [r for r in records if r["id"] not in seen]
            seen.update(r["id"] for r in new)
            all_internships.extend(new)
            logger.info(f"Unstop API page {page_num}/{last_page}: {len(records)} open, {len(new)} new")
            page_num += 1
            # a page has 250 posts of every field; about 1 in 4 fits the field searched
            if budget.enough(all_internships, factor=4):
                break
            human_delay(1.0, 2.0)

        if not api_ok:
            logger.warning("Unstop: API did not answer, reading the cards on the page instead (about 20)")
            try:
                page.wait_for_selector(SEL["card"], timeout=20000)
                for _ in range(4):
                    page.mouse.wheel(0, 1200)
                    human_delay(1.0, 2.0)
                all_internships = parse_list_html(page.content())
            except Exception as e:
                browser.close()
                raise RuntimeError(f"Unstop: no API and no cards on the page: {e}")

        browser.close()

    logger.info(f"Unstop: {len(all_internships)} open internships read")
    return all_internships

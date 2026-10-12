"""
Internshala scraper.

Selectors checked against the live site on 12 Oct 2026. What changed since
the old version:
  - title moved from <h3> to <h2 class="job-internship-name"><a class="job-title-href">
  - location is now ".row-1-item.locations" (old #location_names / .loc_container gone)
  - duration is the ".row-1-item" with the calendar icon (old .item_body gone)
  - start date is no longer on the list card (only on the detail page)
  - page 1 shows 50 cards, later pages 40; the last page has
    <input id="isLastPage" value="1">, so we stop on that instead of "< 40 cards"
  - the detail page has "Activity on Internshala" (hiring since / posts / hired),
    which genuine.py uses to spot mass "internship" programmes
"""
import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score, internship_rejection_reason, stipend_rejection_reason
from scraper_utils import get_playwright_stealth_args, human_delay

BASE = "https://internshala.com"
URLS = [
    "https://internshala.com/internships/artificial-intelligence-ai,data-science,deep-learning,machine-learning,natural-language-processing-nlp-internship/"
]
MAX_PAGES = 30  # safety stop
MAX_PAGES_OTHER_FIELDS = 5   # keyword searches for other fields: first pages are the relevant ones


def urls_for_field():
    """AI/ML: the category page above. Other fields: Internshala's keyword search, one per search word."""
    import fields
    if fields.current() == fields.DEFAULT:
        return URLS, MAX_PAGES
    return [f"{BASE}/internships/keywords-{fields.slug(t)}/" for t in fields.search_terms()], MAX_PAGES_OTHER_FIELDS

SEL = {
    "card": "div.individual_internship[internshipid]",
    "title": "a.job-title-href, .job-internship-name a, .job-internship-name",
    "company": "p.company-name",
    "location": ".row-1-item.locations",
    "stipend": "span.stipend",
    "row_item": ".detail-row-1 .row-1-item",
    "skills": ".job_skills .job_skill",
    "posted": ".color-labels span",
    "snippet": ".about_job .text",
    "gray_labels": ".gray-labels span",
    "last_page": "input#isLastPage",
    # detail page
    "d_about": ".internship_details .text-container",
    "d_activity": ".activity_container .activity",
    "d_heading": ".section_heading",
    "d_start": "#start-date-first",
}


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def parse_stipend(stipend_str: str):
    """'₹ 5,000 - 8,000 /month' -> (5000.0, 'INR'). Uses the lower end of a range."""
    s = stipend_str or ""
    currency = "USD" if "$" in s else "INR"
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", s)]
    if not nums:
        return 0.0, currency
    value = nums[0]
    if "/week" in s.lower():
        value = round(value * 4.33)
    return value, currency


def parse_list_page(html: str):
    """Returns (records, is_last_page)."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select(SEL["card"]):
        try:
            title_el = card.select_one(SEL["title"])
            role_title = _text(title_el)
            if not role_title:
                continue
            company_name = _text(card.select_one(SEL["company"])) or "Unknown"

            loc_el = card.select_one(SEL["location"])
            location = _text(loc_el) or "India"
            is_wfh = bool(loc_el and loc_el.select_one("i.ic-16-home")) or "work from home" in location.lower()
            location_type = "Remote" if is_wfh else "India"

            stipend = _text(card.select_one(SEL["stipend"]))
            stipend_numeric, currency = parse_stipend(stipend)

            duration = ""
            for item in card.select(SEL["row_item"]):
                if item.select_one("i.ic-16-calendar"):
                    duration = _text(item)
                    break

            skills = [_text(s) for s in card.select(SEL["skills"])]
            posted_el = card.select_one(SEL["posted"])
            posted = _text(posted_el)
            labels = [_text(s) for s in card.select(SEL["gray_labels"])]

            href = card.get("data-href") or (title_el.get("href") if title_el and title_el.name == "a" else "")
            apply_link = BASE + href if href.startswith("/") else href

            internship_id = card.get("internshipid", "")
            role_type = "Research" if "research" in role_title.lower() else "Applied"
            records.append({
                "id": hashlib.md5(f"internshala-{internship_id or company_name + role_title}".encode()).hexdigest(),
                "company_name": company_name,
                "role_title": role_title,
                "location": location,
                "location_type": location_type,
                "duration": duration,
                "stipend": stipend,
                "stipend_numeric": stipend_numeric,
                "stipend_currency": currency,
                "required_skills": ", ".join(skills),
                "application_deadline": "",
                "apply_link": apply_link,
                "source_platform": "Internshala",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": role_type,
                "match_score": calculate_match_score(role_title, skills, "Company", stipend_numeric),
                "posted": posted,
                "part_time": any("part time" in l.lower() for l in labels),
                "description": _text(card.select_one(SEL["snippet"])),
            })
        except Exception as e:
            logger.exception(f"Internshala: could not parse a card: {e}")

    last = soup.select_one(SEL["last_page"])
    is_last = bool(last and last.get("value") == "1")
    return records, is_last


def _int(s: str):
    m = re.search(r"\d[\d,]*", s or "")
    return int(m.group(0).replace(",", "")) if m else None


def parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out = {}

    # "Hiring since November 2025", "327 opportunities posted", "191 candidates hired"
    for el in soup.select(SEL["d_activity"]):
        t = _text(el).lower()
        if t.startswith("hiring since"):
            out["employer_since"] = _text(el)[len("Hiring since"):].strip()
        elif "posted" in t:
            out["employer_posted"] = _int(t)
        elif "hired" in t:
            out["employer_hired"] = _int(t)
    if "employer_since" in out:
        out.setdefault("employer_posted", 0)
        out.setdefault("employer_hired", 0)

    for h in soup.select(SEL["d_heading"]):
        if "openings" in _text(h).lower():
            sib = h.find_next_sibling()
            out["openings"] = _int(_text(sib))
            break

    start = soup.select_one(SEL["d_start"])
    if start:
        desktop = start.select_one(".start_immediately_desktop")
        out["start_date"] = _text(desktop) if desktop else _text(start)

    about = soup.select(SEL["d_about"])
    if about:
        out["description"] = " ".join(_text(a) for a in about)[:4000]
    return out


def _wanted(rec: dict):
    """Cheap filters first, so we only open detail pages for listings we'd keep."""
    skills = [s.strip() for s in rec["required_skills"].split(",") if s.strip()]
    return (internship_rejection_reason(rec["role_title"], skills, "internshala") is None
            and stipend_rejection_reason(rec["stipend"], rec["stipend_numeric"],
                                         rec["stipend_currency"] == "INR") is None)


def scrape_internshala():
    all_internships = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        base_urls, max_pages = urls_for_field()
        for base_url in base_urls:
            for page_num in range(1, max_pages + 1):
                url = f"{base_url}page-{page_num}/" if page_num > 1 else base_url
                logger.info(f"Scraping Internshala: {url}")
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_selector(SEL["card"], timeout=15000)
                except Exception as e:
                    if page_num == 1:
                        raise RuntimeError(f"Internshala page 1 did not load: {e}")
                    logger.warning(f"Internshala page {page_num} failed, stopping here: {e}")
                    break

                records, is_last = parse_list_page(page.content())
                new = [r for r in records if r["id"] not in seen]
                seen.update(r["id"] for r in new)
                all_internships.extend(new)
                logger.info(f"Internshala page {page_num}: {len(records)} cards, {len(new)} new")

                if is_last or not new:
                    break
                human_delay(1.5, 3.0)

        # Detail pages: only for listings that pass the cheap filters
        wanted = [r for r in all_internships if _wanted(r)]
        logger.info(f"Internshala: reading {len(wanted)} detail pages for genuineness checks")
        for i, rec in enumerate(wanted, 1):
            try:
                resp = context.request.get(rec["apply_link"], timeout=30000)
                if resp.ok:
                    rec.update(parse_detail_page(resp.text()))
                    rec["detail_checked"] = True
            except Exception as e:
                logger.warning(f"Internshala detail failed for {rec['apply_link']}: {e}")
            if i % 10 == 0:
                logger.info(f"  ...{i}/{len(wanted)} detail pages read")
            human_delay(0.3, 0.8)

        browser.close()

    return all_internships

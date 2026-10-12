"""
Naukri internship scraper.

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The search page still uses .srp-jobtuple-wrapper, a.title, a.comp-name and
    span.locWdth, but:
      * the stipend is now INSIDE span.ni-job-tuple-icon-srp-rupee (the old code
        looked for a sibling span, so every stipend came back empty)
      * internships show a duration (.ni-job-tuple-icon-srp-duration span), not
        experience (span.expwdth is gone on internship cards)
      * skill tags (ul.tags-gt) are not shown on internship cards
  - The old code read only page 1 (20 of 594). 531 of the 594 are marked "Unpaid",
    so we ask Naukri for paid internships only (qcstipend filter, 59 on 12 Oct,
    3 pages) and move through pages by clicking "Next", like a visitor. Loading
    page 2 or 3 directly with the filter in the URL loses the filter.
  - Many Naukri internships are "aggregated from external source": Naukri copied
    them from somewhere else. The detail page says so, and it carries a
    schema.org JobPosting block (description, skills, dates) that we read
    instead of CSS classes, which are hashed (styles_xyz__AbC12) and change often.
"""
import hashlib
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score, internship_rejection_reason, stipend_rejection_reason
from scraper_utils import action_required, action_resolved, human_delay, launch_browser, save_debug

PAID_RANGES = ["0To10", "10To20", "20To30", "30To40", "40To50"]
SLUGS = [
    "ai-ml-internship-jobs-in-india",
    "machine-learning-internship-jobs",
    "data-science-internship-jobs",
    "artificial-intelligence-internship-jobs",
]
# Only the FIRST page of a Naukri search is reliable. Later pages are fetched by the
# page through Naukri's job API, which now wants a reCAPTCHA token: on 12 Oct the
# laptop runs failed at page 3 (06:49, 06:51), then at page 2 (06:57), and in the
# browser neither "Next" nor the "2" link changed the list; loading ".../-2?…"
# directly bounces back to page 1. So instead of paging we open the first page of
# several narrower searches: 4 keywords × 5 pay ranges, 20 cards each.
URLS = [f"https://www.naukri.com/{slug}?qcstipend={r}" for slug in SLUGS for r in PAID_RANGES]
URL = URLS[0]
# Naukri blocks headless browsers (tested 12 Oct 2026: no cards within 20 s).
# A visible Chrome window passes; if a check still appears, solve it in the window.
HEADLESS = False
WAIT_FOR_HUMAN_S = 60

SEL = {
    "card": ".srp-jobtuple-wrapper",
    "title": "a.title",
    "company": "a.comp-name",
    "rating": "a.rating .main-2",
    "reviews": "a.review",
    "duration": ".ni-job-tuple-icon-srp-duration span",
    "stipend": ".ni-job-tuple-icon-srp-rupee span",
    "location": "span.locWdth",
    "start": ".job-post-day",
    "experience": "span.expwdth",   # job cards only
    "skills": "ul.tags-gt li",       # job cards only
    "next": "#lastCompMark a:has-text('Next')",
    # detail page
    "d_jsonld": 'script[type="application/ld+json"]',
    "d_stats": "[class*=styles_jhc__stat]",
}
AGGREGATED_RE = r"aggregated from external source"


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def parse_stipend(text: str) -> float:
    """'20,000/month' -> 20000. 'Unpaid' or unknown -> 0."""
    m = re.search(r"\d[\d,]*", text or "")
    return float(m.group(0).replace(",", "")) if m else 0.0


def parse_list_page(html: str):
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select(SEL["card"]):
        try:
            title_el = card.select_one(SEL["title"])
            role_title = _text(title_el)
            if not role_title:
                continue
            min_exp = re.match(r"\s*(\d+)", _text(card.select_one(SEL["experience"])))
            if min_exp and int(min_exp.group(1)) >= 3:
                continue  # job card that needs 3+ years
            location = _text(card.select_one(SEL["location"])) or "India"
            stipend = _text(card.select_one(SEL["stipend"]))
            stipend_numeric = parse_stipend(stipend)
            skills = [_text(li) for li in card.select(SEL["skills"])]
            job_id = card.get("data-job-id", "")
            records.append({
                "id": hashlib.md5(f"naukri-{job_id or role_title}".encode()).hexdigest(),
                "company_name": _text(card.select_one(SEL["company"])) or "Unknown",
                "role_title": role_title,
                "location": location,
                "location_type": "Remote" if re.search(r"remote|work from home|wfh", location, re.I) else "India",
                "duration": _text(card.select_one(SEL["duration"])),
                "stipend": stipend,
                "stipend_numeric": stipend_numeric,
                "stipend_currency": "INR",
                "required_skills": ", ".join(skills),
                "application_deadline": "",
                "apply_link": title_el.get("href", "") if title_el else "",
                "source_platform": "Naukri",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": "Research" if "research" in role_title.lower() else "Applied",
                "match_score": calculate_match_score(role_title, skills, "Company", stipend_numeric),
                "posted": _text(card.select_one(SEL["start"])),
                "company_rating": _text(card.select_one(SEL["rating"])),
                "description": "",
            })
        except Exception as e:
            logger.exception(f"Naukri: could not parse a card: {e}")
    return records


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "lxml").get_text(" ")).strip()


def parse_detail_page(html: str) -> dict:
    """Reads the schema.org JobPosting block and the Posted/Openings/Applicants line."""
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for script in soup.select(SEL["d_jsonld"]):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            desc = _strip_html(data.get("description"))
            out["description"] = desc[:4000]
            skills = data.get("skills") or []
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",")]
            out["detail_skills"] = [s for s in skills if s]
            out["date_posted"] = data.get("datePosted", "")
            out["application_deadline"] = data.get("validThrough", "")
            out["employment_type"] = data.get("employmentType", "")
            break
    for el in soup.select(SEL["d_stats"]):
        t = _text(el)
        m = re.match(r"(Posted|Openings|Applicants)\s*:\s*(.+)", t)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    out["aggregated"] = bool(re.search(AGGREGATED_RE, out.get("description", "") or html, re.I))
    return out


def _wanted(rec: dict) -> bool:
    skills = [s.strip() for s in rec["required_skills"].split(",") if s.strip()]
    return (internship_rejection_reason(rec["role_title"], skills, "naukri") is None
            and stipend_rejection_reason(rec["stipend"], rec["stipend_numeric"], True) is None)


def scrape_naukri():
    all_internships = []
    seen = set()

    with sync_playwright() as p:
        browser = launch_browser(p, headless=HEADLESS)
        # No fake user agent: a UA that doesn't match the real Chrome version is itself a bot signal
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        for idx, url in enumerate(URLS):
            logger.info(f"Scraping Naukri: {url}")
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(SEL["card"], timeout=12000 if all_internships else 20000)
            except Exception:
                if all_internships:   # we got in before, so this search is just empty
                    logger.info(f"Naukri: no cards for {url.split('/')[-1]}, moving on")
                    continue
                save_debug(page, "naukri_blocked")
                if HEADLESS:
                    browser.close()
                    raise RuntimeError("Naukri: no job cards (blocked). Set HEADLESS = False in sites/naukri.py")
                action_required("Naukri", f"No job cards yet. If the Chrome window shows a check, "
                                          f"solve it there within {WAIT_FOR_HUMAN_S} seconds.", "captcha")
                try:
                    page.wait_for_selector(SEL["card"], timeout=WAIT_FOR_HUMAN_S * 1000)
                    action_resolved("Naukri")
                except Exception as e:
                    if idx < len(URLS) - 1:
                        logger.warning(f"Naukri: nothing for {url.split('/')[-1]} after waiting, trying the next search")
                        continue
                    save_debug(page, "naukri_blocked")
                    browser.close()
                    raise RuntimeError(f"Naukri: still no job cards after {WAIT_FOR_HUMAN_S} s "
                                       f"(see test_output/naukri_blocked.png): {e}")

            human_delay(1.5, 2.5)
            records = parse_list_page(page.content())
            new = [r for r in records if r["id"] not in seen]
            seen.update(r["id"] for r in new)
            all_internships.extend(new)
            logger.info(f"Naukri {url.split('/')[-1]}: {len(records)} cards, {len(new)} new")

        if not all_internships:
            browser.close()
            raise RuntimeError("Naukri: no job cards in any search")

        wanted = [r for r in all_internships if _wanted(r)]
        logger.info(f"Naukri: opening {len(wanted)} detail pages for the genuineness checks")
        for i, rec in enumerate(wanted, 1):
            try:
                page.goto(rec["apply_link"], timeout=45000, wait_until="domcontentloaded")
                page.wait_for_selector(SEL["d_jsonld"], state="attached", timeout=15000)
                detail = parse_detail_page(page.content())
                if detail.get("detail_skills") and not rec["required_skills"]:
                    rec["required_skills"] = ", ".join(detail["detail_skills"])
                rec.update({k: v for k, v in detail.items() if k != "detail_skills" and v})
                rec["aggregated"] = detail.get("aggregated", False)
                rec["detail_checked"] = True
            except Exception as e:
                logger.warning(f"Naukri detail failed for {rec['apply_link']}: {e}")
            if i % 5 == 0:
                logger.info(f"  ...{i}/{len(wanted)} detail pages read")
            human_delay(1.0, 2.0)

        browser.close()

    return all_internships

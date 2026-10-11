"""
Shine internship scraper.

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The old selectors (jobCardNova_bigCard, jobCardNova_bigCardTopTitleName,
    jobCardNova_bigCardCenterListLoc) are gone; the page has 0 of them.
  - Cards are now <article class="result-card_card__p42UB" itemtype="schema.org/ListItem">.
    The class names are CSS-module hashes (the part after "__" changes on every
    Shine release), so we match on the stable prefix: [class*="result-card_role"].
  - The search page is rendered on the server (20 cards per page, page N is
    /job-search/ai-machine-learning-internship-jobs-N), and each job page carries
    a schema.org JobPosting block with the full description, skills and dates.
  - Shine's search is loose: 7,132 results for "ai machine learning internship",
    many of them full-time jobs or training programmes, so our filters matter here.
"""
import hashlib
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score, internship_rejection_reason
from scraper_utils import get_playwright_stealth_args, human_delay

BASE = "https://www.shine.com"
SEARCH = "https://www.shine.com/job-search/ai-machine-learning-internship-jobs"
PAGES = 5          # 20 cards each; results are sorted by relevance
MAX_DETAILS = 40

SEL = {
    "card": 'article[class*="result-card_card"]',
    "url": 'meta[itemprop="url"]',
    "link": 'a[class*="result-card_hit"]',
    "title": 'h3[itemprop="name"], [class*="result-card_role"]',
    "company": '[class*="result-card_company"]',
    "posted": '[class*="result-card_posted"]',
    "meta": '[class*="result-card_meta-text"]',      # experience / salary / location, in that order
    "skills": '[class*="result-card_skills-item"]',
    "d_jsonld": 'script[type="application/ld+json"]',
}


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def parse_salary(text: str) -> float:
    """'₹ 10,000 - 15,000 Per Month' or '1.2 Lakh' -> monthly number; 'Not Disclosed' -> 0."""
    t = (text or "").lower().replace(",", "")
    if not t or "not disclosed" in t:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l\b)?", t)
    if not m:
        return 0.0
    value = float(m.group(1))
    if m.group(2):                       # lakh per annum
        return round(value * 100000 / 12)
    return value


def parse_search_page(html: str):
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select(SEL["card"]):
        try:
            title = _text(card.select_one(SEL["title"]))
            if not title:
                continue
            url_el = card.select_one(SEL["url"])
            link = url_el.get("content", "") if url_el else ""
            if not link:
                a = card.select_one(SEL["link"])
                link = BASE + a.get("href", "").split("?")[0] if a else ""
            job_id = link.rstrip("/").rsplit("/", 1)[-1] if link else ""
            meta = [_text(m) for m in card.select(SEL["meta"])]
            experience = meta[0] if len(meta) > 0 else ""
            salary = meta[1] if len(meta) > 1 else ""
            location = meta[2] if len(meta) > 2 else "India"
            skills = [_text(s).lstrip("·").strip() for s in card.select(SEL["skills"])]
            min_exp = re.match(r"\s*(\d+)", experience)
            if min_exp and int(min_exp.group(1)) >= 3:
                continue  # needs 3+ years: a job, not an internship
            stipend_numeric = parse_salary(salary)
            records.append({
                "id": hashlib.md5(f"shine-{job_id or title + location}".encode()).hexdigest(),
                "company_name": _text(card.select_one(SEL["company"])) or "Unknown",
                "role_title": title,
                "location": location,
                "location_type": "Remote" if re.search(r"remote|work from home|wfh", location, re.I) else "India",
                "duration": "",
                "stipend": "" if salary.lower() == "not disclosed" else salary,
                "stipend_numeric": stipend_numeric,
                "stipend_currency": "INR",
                "required_skills": ", ".join(s for s in skills if s),
                "application_deadline": "",
                "apply_link": link,
                "source_platform": "Shine",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": "Research" if "research" in title.lower() else "Applied",
                "match_score": calculate_match_score(title, skills, "Company", stipend_numeric),
                "posted": _text(card.select_one(SEL["posted"])),
                "experience": experience,
                "description": "",
            })
        except Exception as e:
            logger.exception(f"Shine: could not parse a card: {e}")
    return records


def parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select(SEL["d_jsonld"]):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                desc = re.sub(r"\s+", " ", BeautifulSoup(obj.get("description") or "", "lxml").get_text(" ")).strip()
                return {
                    "description": desc[:4000],
                    "detail_skills": [s for s in (obj.get("skills") or []) if isinstance(s, str)],
                    "date_posted": (obj.get("datePosted") or "")[:10],
                    "application_deadline": (obj.get("validThrough") or "")[:10],
                    "employment_type": obj.get("employmentType", ""),
                    "industries": obj.get("industry", ""),
                }
    return {}


def scrape_shine():
    all_internships = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        for n in range(1, PAGES + 1):
            url = SEARCH if n == 1 else f"{SEARCH}-{n}"
            logger.info(f"Scraping Shine: {url}")
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_selector(SEL["card"], timeout=20000)
            except Exception as e:
                if n == 1:
                    browser.close()
                    raise RuntimeError(f"Shine page 1 did not load: {e}")
                logger.warning(f"Shine page {n} failed, stopping: {e}")
                break
            records = parse_search_page(page.content())
            new = [r for r in records if r["id"] not in seen]
            seen.update(r["id"] for r in new)
            all_internships.extend(new)
            logger.info(f"Shine page {n}: {len(records)} cards, {len(new)} new")
            if not new:
                break
            human_delay(1.5, 3.0)

        wanted = [r for r in all_internships
                  if internship_rejection_reason(r["role_title"], r["required_skills"].split(", "), "shine") is None]
        wanted = wanted[:MAX_DETAILS]
        logger.info(f"Shine: reading {len(wanted)} job pages for the genuineness checks")
        for rec in wanted:
            try:
                resp = context.request.get(rec["apply_link"], timeout=30000)
                if resp.ok:
                    detail = parse_detail_page(resp.text())
                    if detail.get("detail_skills") and not rec["required_skills"]:
                        rec["required_skills"] = ", ".join(detail["detail_skills"])
                    rec.update({k: v for k, v in detail.items() if k != "detail_skills" and v})
                    rec["detail_checked"] = True
            except Exception as e:
                logger.warning(f"Shine detail failed for {rec['apply_link']}: {e}")
            human_delay(0.5, 1.2)

        browser.close()
    return all_internships

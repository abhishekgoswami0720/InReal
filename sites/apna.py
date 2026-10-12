"""
Apna internship scraper.

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The old URL https://apna.co/jobs?category=internship&q=ai+ml ignores both
    parameters and lists all 81,222 jobs (first result: "Assistant General Manager").
    The search that works is /jobs?search=true&text=<words> (42 results for
    "ai ml internship"), page N with &page=N.
  - The old data-testid selectors (job-title, company-title, job-location,
    job-salary) are gone; only data-testid="job-card" is left. Title is the <h2>,
    company the <span> after it, and location / pay are the spans next to the
    LocationOnIcon / PaymentsIcon icons. Each card also carries an inline <style>
    tag, so we read the span itself, never the whole row's text.
  - Job pages are rendered on the server and carry a schema.org JobPosting block.
"""
import hashlib
import json
import re
import urllib.parse
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from filters import calculate_match_score, internship_rejection_reason
from scraper_utils import get_playwright_stealth_args, human_delay

BASE = "https://apna.co"
SEARCH = BASE + "/jobs?search=true&text={q}&page={page}"
QUERIES = ["ai ml internship", "machine learning internship", "artificial intelligence internship", "data science internship"]
PAGES_PER_QUERY = 2   # 25 cards per page
MAX_DETAILS = 60

SEL = {
    "card": 'a[data-testid="job-card"]',
    "title": "h2",
    "location_icon": 'svg[data-testid="LocationOnIcon"]',
    "pay_icon": 'svg[data-testid="PaymentsIcon"]',
    "chips": 'div[class*="overflow-x-scroll"] span',
    "d_jsonld": 'script[type="application/ld+json"]',
}


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def _next_to_icon(card, icon_sel) -> str:
    icon = card.select_one(icon_sel)
    span = icon.find_next_sibling("span") if icon else None
    return _text(span)


def parse_pay(text: str) -> float:
    """'₹15,000 - ₹25,000' -> 15000 (monthly as shown); 'Not disclosed' -> 0."""
    m = re.search(r"\d[\d,]*", text or "")
    if not m or "not disclosed" in (text or "").lower():
        return 0.0
    value = float(m.group(0).replace(",", ""))
    return round(value / 12) if value >= 200000 else value   # yearly CTC shown on some cards


def parse_search_page(html: str):
    soup = BeautifulSoup(html, "lxml")
    for style in soup.find_all("style"):
        style.decompose()
    records = []
    for card in soup.select(SEL["card"]):
        try:
            h2 = card.select_one(SEL["title"])
            title = _text(h2)
            href = card.get("href", "")
            if not title or not href:
                continue
            company_el = h2.find_next_sibling("span") if h2 else None
            location = _next_to_icon(card, SEL["location_icon"]) or "India"
            pay = _next_to_icon(card, SEL["pay_icon"])
            chips = [_text(s) for s in card.select(SEL["chips"]) if _text(s)]
            m = re.search(r"-(\d{6,})$", href)
            job_id = m.group(1) if m else href
            numeric = parse_pay(pay)
            hidden = numeric == 0
            records.append({
                "id": hashlib.md5(f"apna-{job_id}".encode()).hexdigest(),
                "company_name": _text(company_el) or "Unknown",
                "role_title": title,
                "location": location,
                "location_type": "Remote" if re.search(r"remote|work from home", " ".join([location] + chips), re.I) else "India",
                "duration": "",
                "stipend": "" if hidden else pay,
                "stipend_numeric": numeric,
                "stipend_currency": "INR",
                "stipend_hidden_by_site": hidden,     # nearly every Apna internship says "Not disclosed"
                "required_skills": "",
                "application_deadline": "",
                "apply_link": BASE + href if href.startswith("/") else href,
                "source_platform": "Apna",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": "Research" if "research" in title.lower() else "Applied",
                "match_score": calculate_match_score(title, [], "Company", numeric),
                "posted": "",
                "work_tags": ", ".join(chips),
                "description": "",
            })
        except Exception as e:
            logger.exception(f"Apna: could not parse a card: {e}")
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
                    "posted": (obj.get("datePosted") or "")[:10],
                    "application_deadline": (obj.get("validThrough") or "")[:10],
                    "industries": obj.get("industry", ""),
                }
    return {}


def scrape_apna():
    all_internships = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=get_playwright_stealth_args())
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        for q in QUERIES:
            for n in range(1, PAGES_PER_QUERY + 1):
                url = SEARCH.format(q=urllib.parse.quote(q), page=n)
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_selector(SEL["card"], timeout=15000)
                except Exception as e:
                    logger.warning(f"Apna '{q}' page {n} failed: {e}")
                    break
                records = parse_search_page(page.content())
                new = [r for r in records if r["id"] not in seen]
                seen.update(r["id"] for r in new)
                all_internships.extend(new)
                logger.info(f"Apna '{q}' page {n}: {len(records)} cards, {len(new)} new")
                human_delay(1.5, 2.5)
                if len(records) < 25:
                    break

        if not all_internships:
            browser.close()
            raise RuntimeError("Apna: no job cards on any search page")

        wanted = [r for r in all_internships if internship_rejection_reason(r["role_title"], [], "apna") is None][:MAX_DETAILS]
        logger.info(f"Apna: reading {len(wanted)} job pages for the genuineness checks")
        for rec in wanted:
            try:
                resp = context.request.get(rec["apply_link"], timeout=30000)
                if resp.ok:
                    rec.update({k: v for k, v in parse_detail_page(resp.text()).items() if v})
                    rec["detail_checked"] = True
            except Exception as e:
                logger.warning(f"Apna detail failed for {rec['apply_link']}: {e}")
            human_delay(0.5, 1.0)

        browser.close()
    return all_internships

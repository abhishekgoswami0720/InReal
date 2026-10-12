"""
Foundit (formerly Monster India) internship scraper.

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The old selectors (div "job-tuple", span "company-name", div "details") match
    nothing; the old URL https://www.foundit.in/srp/results?query=ai+ml+internship
    even shows 1 result, because the page sends the "+" signs literally
    ("ai+ml+internship") to its own search.
  - The page loads results from Foundit's JSON endpoint
        /middleware/jobsearch?sort=1&limit=60&query=<words>
    and job descriptions from /middleware/jobdetail/<id>. We call both from inside
    a real page (the site uses Akamai bot checks), for several AI/ML queries.
  - We never store the recruiter's name or phone number, which the endpoint returns.
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
from scraper_utils import human_delay, launch_browser, save_debug

BASE = "https://www.foundit.in"
SEARCH_API = BASE + "/middleware/jobsearch?sort=1&limit=60&query={q}"
DETAIL_API = BASE + "/middleware/jobdetail/{job_id}"
QUERIES = [
    "machine learning internship", "machine learning intern", "artificial intelligence internship",
    "ai internship", "ai ml intern", "data science internship", "deep learning internship",
]
MAX_DETAILS = 60
HEADLESS = False  # Akamai bot checks, like Naukri

FETCH_JS = """async (url) => {
    const r = await fetch(url, {headers: {Accept: 'application/json'}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
}"""


def _monthly(salary: dict) -> float:
    try:
        return float((salary or {}).get("absoluteMonthlyValue") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_search_json(payload: dict):
    records = []
    for x in (payload.get("jobSearchResponse") or {}).get("data") or []:
        try:
            title = (x.get("title") or "").strip()
            if not title or x.get("isJobActive") is False:
                continue
            job_id = str(x.get("jobId") or x.get("id") or "")
            lo, hi = _monthly(x.get("minimumSalary")), _monthly(x.get("maximumSalary"))
            hidden = x.get("hideSalary") or x.get("jobSalaryConfidential") or not (lo or hi)
            stipend = "" if hidden else (f"₹ {lo:,.0f} /month" if lo == hi else f"₹ {lo:,.0f} - {hi:,.0f} /month")
            location = (x.get("locations") or "India").strip()
            skills = [s.strip() for s in (x.get("skills") or "").split(",") if s.strip()]
            url = x.get("seoJdUrl") or x.get("jdUrl") or ""
            created = x.get("createdAt")
            records.append({
                "id": hashlib.md5(f"foundit-{job_id or title + location}".encode()).hexdigest(),
                "job_id": job_id,
                "company_name": (x.get("companyName") or "Unknown").strip(),
                "role_title": title,
                "location": location,
                "location_type": "Remote" if re.search(r"remote|work from home|wfh", location, re.I) else "India",
                "duration": "",
                "stipend": stipend,
                "stipend_numeric": 0.0 if hidden else (lo or hi),
                "stipend_currency": "INR",
                "stipend_hidden_by_site": bool(hidden),  # "0-0 INR" on most Foundit posts
                "required_skills": ", ".join(skills),
                "application_deadline": datetime.fromtimestamp(x["closedAt"] / 1000).strftime("%Y-%m-%d") if x.get("closedAt") else "",
                "apply_link": BASE + url if url.startswith("/") else url,
                "source_platform": "Foundit",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Company",
                "role_type": "Research" if "research" in title.lower() else "Applied",
                "match_score": calculate_match_score(title, skills, "Company", lo),
                "posted": x.get("postedBy") or (datetime.fromtimestamp(created / 1000).strftime("%Y-%m-%d") if created else ""),
                "experience": x.get("exp", ""),
                "third_party": "consultant" in " ".join(x.get("employerTypes") or []).lower(),
                "applicants": x.get("totalApplicants"),
                "description": "",
            })
        except Exception as e:
            logger.exception(f"Foundit: could not read a result: {e}")
    return records


def parse_detail_json(payload: dict) -> dict:
    d = payload.get("jobDetailResponse") or {}
    desc = re.sub(r"\s+", " ", BeautifulSoup(d.get("description") or "", "lxml").get_text(" ")).strip()
    return {"description": desc[:4000]} if desc else {}


def scrape_foundit():
    all_internships = []
    seen = set()
    with sync_playwright() as p:
        browser = launch_browser(p, headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        logger.info("Opening Foundit")
        page.goto(BASE + "/", timeout=45000, wait_until="domcontentloaded")
        human_delay(3.0, 5.0)  # let the site's own bot check finish

        for q in QUERIES:
            try:
                payload = page.evaluate(FETCH_JS, SEARCH_API.format(q=urllib.parse.quote(q)))
            except Exception as e:
                logger.warning(f"Foundit search '{q}' failed: {e}")
                if not all_internships:
                    save_debug(page, "foundit_blocked")
                continue
            records = parse_search_json(payload)
            new = [r for r in records if r["id"] not in seen]
            seen.update(r["id"] for r in new)
            all_internships.extend(new)
            logger.info(f"Foundit '{q}': {len(records)} results, {len(new)} new")
            human_delay(1.0, 2.0)

        if not all_internships:
            browser.close()
            raise RuntimeError("Foundit: no results from any search (blocked?). See test_output/foundit_blocked.png")

        wanted = [r for r in all_internships
                  if internship_rejection_reason(r["role_title"], r["required_skills"].split(", "), "foundit") is None]
        wanted = wanted[:MAX_DETAILS]
        logger.info(f"Foundit: reading {len(wanted)} job descriptions for the genuineness checks")
        for rec in wanted:
            try:
                rec.update(parse_detail_json(page.evaluate(FETCH_JS, DETAIL_API.format(job_id=rec["job_id"]))))
                rec["detail_checked"] = True
            except Exception as e:
                logger.warning(f"Foundit detail {rec['job_id']} failed: {e}")
            human_delay(0.5, 1.0)

        browser.close()
    return all_internships

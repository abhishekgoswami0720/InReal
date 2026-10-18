"""
Job aggregators for India: Talent.com, SimplyHired and Careerjet.

Rebuilt 18 Oct 2026. The old scrape_aggregators() did not read these sites at all: it returned
one made-up card per site ("Search Results: AI/ML Internships", stipend "Varies", ₹5,000) that
only linked to the search page. These read the real result pages, checked in a browser that day:

  - Talent.com: https://in.talent.com/jobs?k=<words>&l=India is server-rendered; each result is
    <article data-testid="job-card-unified"> with an <h2> title, JobCard_company / JobCard_location
    spans, a snippet and a /view?id=... link. 20 per page.
  - SimplyHired: https://www.simplyhired.co.in/search?q=<words>&l=India carries its 20 results in
    the __NEXT_DATA__ JSON (title, company, location, salaryInfo, snippet, jobKey, requirements).
  - Careerjet: https://www.careerjet.co.in/jobs?s=<words>&l=India first shows a "Verification in
    progress" page that a real browser passes on its own after a few seconds, so this one uses
    Playwright. Results are <article class="job"> with h2 a, p.company, ul.location and div.desc.

Each site is searched with the student's field words (fields.py) plus "intern".
The old scrape_niche_boards() also only returned made-up cards; its four sites are gone
(AIJobs.net now redirects to foorilla.com, which hides company names and invents salaries;
the MLOps, DeepLearning.AI and KDnuggets job pages no longer exist), so it now returns nothing.
"""
import json
import re
import urllib.parse

from bs4 import BeautifulSoup
from loguru import logger

from scraper_utils import human_delay, launch_browser
from sites._common import dedupe, get, record, search_words

TALENT = "https://in.talent.com/jobs?k={q}&l=India"
SIMPLYHIRED = "https://www.simplyhired.co.in/search?q={q}&l=India"
CAREERJET = "https://www.careerjet.co.in/jobs?s={q}&l=India"


def _queries():
    return [f"{w} intern" for w in search_words(3)]


def inr_monthly(text):
    """'₹15,000 a month' -> 15000; 'From ₹60,000 a year' -> 5000; anything else -> 0."""
    if not text or "₹" not in text:
        return 0.0
    nums = [float(n.replace(",", "")) for n in re.findall(r"₹\s*([\d,]+(?:\.\d+)?)", text)]
    if not nums:
        return 0.0
    low = min(nums)
    if re.search(r"\b(year|annum|yearly|annual)\b", text, re.I):
        return low / 12
    if re.search(r"\b(month|monthly)\b", text, re.I):
        return low
    return 0.0


# ---------- Talent.com ----------
def parse_talent(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select('article[data-testid="job-card-unified"]'):
        title = card.find("h2")
        link = card.select_one('a[href*="/view?id="]')
        if not title or not link:
            continue
        company = card.select_one('[class*="JobCard_company"]')
        location = card.select_one('[class*="JobCard_location"]')
        snippet = card.select_one('[class*="JobCard_snippet"]')
        posted = card.find("time")
        href = urllib.parse.urljoin("https://in.talent.com", link["href"])
        out.append(record("Talent.com", title.get_text(" ", strip=True),
                          company.get_text(" ", strip=True) if company else "",
                          location.get_text(" ", strip=True) if location else "India", href,
                          job_id=href.split("id=")[-1],
                          description=snippet.get_text(" ", strip=True).replace("Show more", "").strip() if snippet else "",
                          posted=(posted.get("datetime") or "")[:10] if posted else ""))
    return out


def scrape_talent():
    out = []
    for q in _queries():
        try:
            found = parse_talent(get(TALENT.format(q=urllib.parse.quote_plus(q))).text)
            logger.info(f"Talent.com '{q}': {len(found)} results")
            out += found
        except Exception as e:
            logger.warning(f"Talent.com '{q}' failed: {e}")
        human_delay(1.0, 2.0)
    return dedupe(out)


# ---------- SimplyHired ----------
def parse_simplyhired(html):
    tag = BeautifulSoup(html, "lxml").find("script", id="__NEXT_DATA__")
    if not tag:
        return []
    jobs = json.loads(tag.string).get("props", {}).get("pageProps", {}).get("jobs") or []
    out = []
    for j in jobs:
        key = j.get("jobKey")
        if not key or not j.get("title"):
            continue
        salary = j.get("salaryInfo") or ""
        monthly = inr_monthly(salary)
        out.append(record("SimplyHired", j["title"], j.get("company"), j.get("location") or "India",
                          f"https://www.simplyhired.co.in/job/{key}", job_id=key,
                          stipend=salary, stipend_numeric=monthly, currency="INR" if monthly else "",
                          skills=(j.get("requirements") or []) + (j.get("uncategorized") or [])[:8],
                          description=j.get("snippet") or ""))
    return out


def scrape_simplyhired():
    out = []
    for q in _queries():
        try:
            found = parse_simplyhired(get(SIMPLYHIRED.format(q=urllib.parse.quote_plus(q))).text)
            logger.info(f"SimplyHired '{q}': {len(found)} results")
            out += found
        except Exception as e:
            logger.warning(f"SimplyHired '{q}' failed: {e}")
        human_delay(1.0, 2.0)
    return dedupe(out)


# ---------- Careerjet ----------
def parse_careerjet(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("article.job"):
        a = card.select_one("h2 a")
        if not a:
            continue
        company = card.select_one("p.company")
        location = card.select_one("ul.location")
        desc = card.select_one("div.desc")
        badge = card.select_one("footer .badge")
        href = urllib.parse.urljoin("https://www.careerjet.co.in", a.get("href", ""))
        out.append(record("Careerjet", a.get("title") or a.get_text(" ", strip=True),
                          company.get_text(" ", strip=True) if company else "",
                          location.get_text(" ", strip=True) if location else "India", href,
                          job_id=href.rsplit("/", 1)[-1],
                          description=desc.get_text(" ", strip=True) if desc else "",
                          posted=badge.get_text(" ", strip=True) if badge else ""))
    return out


def scrape_careerjet():
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        browser = launch_browser(p, headless=True)
        page = browser.new_page()
        try:
            for q in _queries():
                try:
                    page.goto(CAREERJET.format(q=urllib.parse.quote_plus(q)), timeout=45000,
                              wait_until="domcontentloaded")
                    # the "Verification in progress" page clears itself after a few seconds
                    page.wait_for_selector("article.job, .no-results, #search-noresults", timeout=25000)
                    found = parse_careerjet(page.content())
                    logger.info(f"Careerjet '{q}': {len(found)} results")
                    out += found
                except Exception as e:
                    logger.warning(f"Careerjet '{q}' failed: {e}")
                human_delay(1.5, 3.0)
        finally:
            browser.close()
    return dedupe(out)


def scrape_aggregators():
    """All three, for old saved settings that still name 'aggregators'."""
    out = []
    for fn in (scrape_talent, scrape_simplyhired, scrape_careerjet):
        try:
            out += fn()
        except Exception as e:
            logger.warning(f"{fn.__name__} failed: {e}")
    return out


def scrape_niche_boards():
    logger.info("AI job boards: AIJobs.net, MLOps Community, DeepLearning.AI and KDnuggets no longer "
                "have readable job lists; nothing to fetch")
    return []

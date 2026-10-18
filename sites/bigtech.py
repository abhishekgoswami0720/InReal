"""
Big Tech career sites. Rebuilt 18 Oct 2026.

The old scrape_bigtech() did not read any of these sites: it returned one made-up card per
company ("AI/ML Internships (Microsoft Research)", stipend "Highly Competitive", 10,000 USD) that
only linked to a search page. Each function below reads the company's own job list, checked in a
real browser that day:

  Microsoft  GET  apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&start=N
             (JSON: positions[].name, locations, positionUrl, postedTs; "count" = total)
  Google     GET  google.com/about/careers/applications/jobs/results/?q=intern&target_level=INTERN_AND_APPRENTICE&page=N
             (server-rendered <li> cards: <h3> title, "place" icon + locations, a "Minimum
             qualifications" list; 20 per page, 85 on 18 Oct)
  Apple      GET  jobs.apple.com/en-us/search?team=internships-STDNT-INTRN&page=N
             (Apple's "Students: Internships" team; div.job-list-item rows; 108 on 18 Oct)
  Meta       metacareers.com/jobsearch/?roles[0]=Internship is drawn by JavaScript, so it opens in
             Playwright and reads the /profile/job_details/<id> links (54 on 18 Oct)
  Amazon     GET  amazon.jobs/en/search.json?base_query=intern&offset=N (JSON, 443 on 18 Oct)
  NVIDIA, Intel, Adobe, Salesforce: Workday career sites,
             POST https://<host>/wday/cxs/<tenant>/<site>/jobs {"searchText": "intern", ...}

Their searches also return non-intern jobs, so only titles that say intern / co-op / apprentice
are kept; the field filter (filters.py) then keeps the student's field.
"""
import re
import urllib.parse
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger

from sites._common import dedupe, get, html_to_text, looks_like_internship, post_json, record

MAX_PER_COMPANY = 200


# ---------- Microsoft ----------
MS_API = "https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern&location=&start={start}"


def parse_microsoft(data):
    out = []
    for p in ((data or {}).get("data") or {}).get("positions") or []:
        title = p.get("name", "")
        if not looks_like_internship(title):
            continue
        posted = datetime.fromtimestamp(p["postedTs"]).strftime("%Y-%m-%d") if p.get("postedTs") else ""
        out.append(record("Microsoft Careers", title, "Microsoft", "; ".join(p.get("locations") or []),
                          "https://apply.careers.microsoft.com" + (p.get("positionUrl") or f"/careers/job/{p.get('id')}"),
                          job_id=p.get("id", ""), skills=[p.get("department") or ""], posted=posted))
    return out


def scrape_microsoft():
    out, start, total = [], 0, None
    while start < MAX_PER_COMPANY and (total is None or start < total):
        data = get(MS_API.format(start=start)).json()
        positions = ((data.get("data") or {}).get("positions")) or []
        total = (data.get("data") or {}).get("count", 0)
        if not positions:
            break
        out += parse_microsoft(data)
        start += len(positions)
    logger.info(f"Microsoft: {total} results for 'intern', {len(out)} internships")
    return dedupe(out)


# ---------- Google ----------
GOOGLE = ("https://www.google.com/about/careers/applications/jobs/results/"
          "?q=intern&target_level=INTERN_AND_APPRENTICE&page={page}")


def parse_google(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for li in soup.find_all("li"):
        h3 = li.find("h3")
        link = li.select_one('a[href*="jobs/results/"]')
        if not h3 or not link:
            continue
        locations = []
        for icon in li.find_all("i"):
            if icon.get_text(strip=True) == "place":
                locations = [s.get_text(strip=True).lstrip("; ") for s in icon.parent.find_all("span")
                             if s.get_text(strip=True) and "more" not in s.get_text()]
                break
        quals = ""
        h4 = li.find("h4", string=re.compile("Minimum qualifications", re.I))
        if h4 and h4.find_next("ul"):
            quals = "Minimum qualifications: " + h4.find_next("ul").get_text(" ", strip=True)
        href = urllib.parse.urljoin("https://www.google.com/about/careers/applications/", link["href"].split("?")[0])
        out.append(record("Google Careers", h3.get_text(" ", strip=True), "Google",
                          "; ".join(dict.fromkeys(locations)), href, job_id=href.rsplit("/", 1)[-1].split("-")[0],
                          description=quals, labelled_internship=True))
    return out


def scrape_google():
    out = []
    for page in range(1, 11):
        found = parse_google(get(GOOGLE.format(page=page)).text)
        if not found:
            break
        out += found
    logger.info(f"Google: {len(out)} intern & apprentice posts")
    return dedupe(out)


# ---------- Apple ----------
APPLE = "https://jobs.apple.com/en-us/search?team=internships-STDNT-INTRN&page={page}"


def parse_apple(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for row in soup.select("div.job-list-item"):
        a = row.select_one("h3 a")
        if not a:
            continue
        loc = row.select_one('[id^="search-store-name-container"]')
        posted = row.select_one(".job-posted-date")
        href = urllib.parse.urljoin("https://jobs.apple.com", a.get("href", "").split("?")[0])
        out.append(record("Apple Jobs", a.get_text(" ", strip=True), "Apple",
                          loc.get_text(" ", strip=True) if loc else "", href,
                          job_id=href.split("/details/")[-1].split("/")[0],
                          posted=posted.get_text(strip=True) if posted else "", labelled_internship=True))
    return out


def _apple_pages(fetch):
    out = []
    for page in range(1, 11):
        found = parse_apple(fetch(APPLE.format(page=page)))
        if not found:
            break
        out += found
    return out


def scrape_apple():
    out = _apple_pages(lambda url: get(url).text)
    if not out:   # the list is drawn by JavaScript if the server stops sending it
        from playwright.sync_api import sync_playwright
        from scraper_utils import launch_browser
        with sync_playwright() as p:
            browser = launch_browser(p, headless=True)
            page = browser.new_page()

            def fetch(url):
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector("div.job-list-item", timeout=15000)
                except Exception:
                    pass
                return page.content()
            try:
                out = _apple_pages(fetch)
            finally:
                browser.close()
    logger.info(f"Apple: {len(out)} student internships")
    return dedupe(out)


# ---------- Meta ----------
META = "https://www.metacareers.com/jobsearch/?roles[0]=Internship"


def parse_meta(rows):
    """rows: [(href, innerText)] of the /profile/job_details/<id> links on the search page."""
    out = []
    for href, text in rows:
        m = re.search(r"/job_details/(\d+)", href or "")
        lines = [l.strip() for l in (text or "").split("\n") if l.strip() and l.strip() != "⋅"]
        if not m or not lines:
            continue
        title = lines[0]
        places = [l for l in lines[1:] if re.search(r", [A-Z]{2}\b|remote|india|singapore|london|tel aviv|"
                                                     r"dublin|paris|zurich|toronto|seattle|new york", l, re.I)]
        tags = [l for l in lines[1:] if l not in places]
        out.append(record("Meta Careers", title, "Meta", "; ".join(places),
                          f"https://www.metacareers.com/jobs/{m.group(1)}/", job_id=m.group(1),
                          skills=tags, labelled_internship=True))
    return out


def scrape_meta():
    from playwright.sync_api import sync_playwright
    from scraper_utils import launch_browser
    with sync_playwright() as p:
        browser = launch_browser(p, headless=True)
        page = browser.new_page()
        try:
            page.goto(META, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_selector('a[href*="/profile/job_details/"]', timeout=30000)
            last = -1
            for _ in range(30):          # the list grows as you scroll
                count = page.locator('a[href*="/profile/job_details/"]').count()
                if count == last:
                    break
                last = count
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(1200)
            rows = page.eval_on_selector_all('a[href*="/profile/job_details/"]',
                                             "els => els.map(a => [a.getAttribute('href'), a.innerText])")
        finally:
            browser.close()
    out = parse_meta(rows)
    logger.info(f"Meta: {len(out)} internships")
    return dedupe(out)


# ---------- Amazon ----------
AMAZON = "https://www.amazon.jobs/en/search.json?base_query=intern&result_limit=100&offset={offset}&sort=recent"


def parse_amazon(data):
    out = []
    for j in (data or {}).get("jobs") or []:
        title = j.get("title", "")
        if not looks_like_internship(title):
            continue
        desc = " ".join(filter(None, [html_to_text(j.get("description_short")),
                                      "Basic qualifications: " + html_to_text(j.get("basic_qualifications"))
                                      if j.get("basic_qualifications") else ""]))
        out.append(record("Amazon Jobs", title, j.get("company_name") or "Amazon",
                          j.get("normalized_location") or j.get("location") or "",
                          "https://www.amazon.jobs" + (j.get("job_path") or ""), job_id=j.get("id_icims") or j.get("id"),
                          skills=[j.get("job_category") or ""], description=desc, posted=j.get("posted_date") or ""))
    return out


def scrape_amazon():
    out, offset, hits = [], 0, None
    while offset < MAX_PER_COMPANY * 2 and (hits is None or offset < hits):
        data = get(AMAZON.format(offset=offset)).json()
        hits = data.get("hits", 0)
        if not data.get("jobs"):
            break
        out += parse_amazon(data)
        offset += len(data["jobs"])
    logger.info(f"Amazon: {hits} results for 'intern', {len(out)} internships")
    return dedupe(out)


# ---------- Workday sites (NVIDIA, Intel, Adobe, Salesforce) ----------
WORKDAY = {
    "nvidia": ("NVIDIA Careers", "NVIDIA", "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"),
    "intel": ("Intel Careers", "Intel", "intel.wd1.myworkdayjobs.com", "intel", "External"),
    "adobe": ("Adobe Careers", "Adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "external_experienced"),
    "salesforce": ("Salesforce Careers", "Salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce",
                   "External_Career_Site"),
}


def parse_workday(data, key):
    source, company, host, _tenant, site = WORKDAY[key]
    out = []
    for j in (data or {}).get("jobPostings") or []:
        title = j.get("title", "")
        if not looks_like_internship(title):
            continue
        path = j.get("externalPath") or ""
        out.append(record(source, title, company, j.get("locationsText") or "",
                          f"https://{host}/en-US/{site}{path}", job_id=(j.get("bulletFields") or [path])[0],
                          posted=j.get("postedOn") or ""))
    return out


def scrape_workday(key):
    source, _company, host, tenant, site = WORKDAY[key]
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out, offset, total = [], 0, None
    while offset < MAX_PER_COMPANY and (total is None or offset < total):
        data = post_json(url, {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": "intern"})
        total = data.get("total", 0) if total is None else total
        if not data.get("jobPostings"):
            break
        out += parse_workday(data, key)
        offset += 20
    logger.info(f"{source}: {total} results for 'intern', {len(out)} internships in the first {offset}")
    return dedupe(out)


def scrape_nvidia():
    return scrape_workday("nvidia")


def scrape_intel():
    return scrape_workday("intel")


def scrape_adobe():
    return scrape_workday("adobe")


def scrape_salesforce():
    return scrape_workday("salesforce")


COMPANIES = {"microsoft": scrape_microsoft, "google": scrape_google, "apple": scrape_apple, "meta": scrape_meta,
             "amazon": scrape_amazon, "nvidia": scrape_nvidia, "intel": scrape_intel, "adobe": scrape_adobe,
             "salesforce": scrape_salesforce}


def scrape_bigtech():
    """Every company, for old saved settings that still name 'bigtech'."""
    out = []
    for name, fn in COMPANIES.items():
        try:
            out += fn()
        except Exception as e:
            logger.warning(f"{name} failed: {e}")
    return out

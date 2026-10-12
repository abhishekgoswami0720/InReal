"""
Government portal scraper: AICTE National Internship Portal (Government of India,
Ministry of Education), https://internship.aicte-india.org

Checked against the live site on 12 Oct 2026. What changed since the old version:
  - The old code did not scrape internships at all. For AICTE, C-DAC and DRDO it
    checked whether the page contained a word like "machine learning" and then
    wrote ONE made-up card per portal ("AI/ML Internship Opportunities (AICTE)",
    stipend "Govt Norms" = 5000). That is not a real listing.
  - The AICTE portal now loads its listings from a public JSON endpoint:
        /api/v1/catalogue/internships?q=<words>&page=N&pageSize=60
    and every item says who posted it ("category": MSME, Corporate, NGO,
    Government, Army, TULIP), whether the portal verified the employer, the
    stipend, deadline, openings and description. We read real listings from it.
  - On 12 Oct the portal had 1,236 live internships: 785 MSME, 390 Corporate,
    34 Army, 18 NGO, 6 TULIP (urban missions) and 3 "Government". Its AI/ML
    listings are mostly small firms, many selling training, so the genuine
    checks matter here too.
  - C-DAC's dashboard on the portal only shows statistics (no listings), and
    DRDO's page describes a scheme run lab by lab, so neither gives listings to scrape.
"""
import hashlib
import re
import urllib.parse
from datetime import datetime

import requests
from loguru import logger

from filters import calculate_match_score
from scraper_utils import human_delay

BASE = "https://internship.aicte-india.org"
API = BASE + "/api/v1/catalogue/internships?{query}&sort=best&page={page}&pageSize=60"
SEARCHES = [
    "q=machine%20learning", "q=artificial%20intelligence", "q=data%20science", "q=deep%20learning",
    "q=computer%20vision", "q=generative%20ai", "q=nlp",
    # every listing from government bodies, whatever the topic (the AI/ML filter runs later)
    "category=Government", "category=Army", "category=TULIP",
]
GOVERNMENT_CATEGORIES = {"government", "army", "tulip"}
MAX_PAGES = 10


# Plain headers on purpose. get_random_headers() offers "br" (Brotli) compression,
# and without the brotli package requests cannot unpack it: the laptop run on
# 12 Oct 06:21 got compressed bytes and "Expecting value: line 1 column 1".
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Referer": BASE + "/internships",
}


def _get_json(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except requests.exceptions.SSLError:
        # Government sites sometimes serve an incomplete certificate chain
        logger.warning("AICTE: certificate problem, retrying without verification for this public listing")
        r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f"not JSON (HTTP {r.status_code}, {r.headers.get('content-type')}): {r.text[:150]!r}")


def parse_items(payload: dict):
    records = []
    for x in payload.get("items") or []:
        try:
            title = (x.get("title") or "").strip()
            if not title or x.get("isOpen") is False:
                continue
            category = (x.get("category") or "").strip()
            stipend_num = float(x.get("stipend") or 0)
            display = (x.get("stipendDisplay") or "").strip()
            skills = [s for s in (x.get("skills") or []) if isinstance(s, str)]
            desc_parts = [x.get("description") or ""] + [r for r in (x.get("responsibilities") or []) if isinstance(r, str)]
            location = (x.get("location") or "India").strip()
            mode = (x.get("mode") or "").strip()
            records.append({
                "id": hashlib.md5(f"aicte-{x.get('id') or title + location}".encode()).hexdigest(),
                "company_name": (x.get("organization") or "Unknown").strip(),
                "role_title": title,
                "location": location,
                "location_type": "Remote" if re.search(r"remote|work from home", mode + " " + location, re.I) else "India",
                "duration": (x.get("duration") or "").strip(),
                "stipend": display,
                "stipend_numeric": stipend_num,
                "stipend_currency": "INR",
                "required_skills": ", ".join(skills),
                "application_deadline": (x.get("deadline") or "")[:10],
                "apply_link": f"{BASE}/internships/{x.get('id')}" if x.get("id") else BASE + "/internships",
                "source_platform": "AICTE Internship Portal (Govt of India)",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                "org_type": "Government" if category.lower() in GOVERNMENT_CATEGORIES else "Company",
                "role_type": "Research" if "research" in title.lower() else "Applied",
                "match_score": calculate_match_score(title, skills, "Government" if category.lower() in GOVERNMENT_CATEGORIES else "Company", stipend_num),
                "posted": (x.get("postedDate") or "")[:10],
                "poster_category": category,              # MSME / Corporate / NGO / Government / Army / TULIP
                "portal_verified": x.get("verified"),
                "openings": x.get("openings"),
                "description": re.sub(r"\s+", " ", " ".join(desc_parts)).strip()[:4000],
            })
        except Exception as e:
            logger.exception(f"AICTE: could not read an item: {e}")
    return records


def scrape_government():
    all_internships = []
    seen = set()
    for query in SEARCHES:
        for page in range(1, MAX_PAGES + 1):
            url = API.format(query=query, page=page)
            try:
                payload = _get_json(url)
            except Exception as e:
                logger.warning(f"AICTE '{urllib.parse.unquote(query)}' page {page} failed: {e}")
                break
            records = parse_items(payload)
            new = [r for r in records if r["id"] not in seen]
            seen.update(r["id"] for r in new)
            all_internships.extend(new)
            total_pages = payload.get("totalPages") or 1
            logger.info(f"AICTE '{urllib.parse.unquote(query)}' page {page}/{total_pages}: {len(records)} listings, {len(new)} new")
            human_delay(0.8, 1.6)
            if page >= total_pages:
                break
    if not all_internships:
        raise RuntimeError("AICTE portal returned no listings")
    return all_internships

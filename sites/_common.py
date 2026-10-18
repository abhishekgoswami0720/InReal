"""
Small helpers shared by the scrapers rebuilt on 18 Oct 2026 (Cutshort, the job aggregators,
Remotive, We Work Remotely, Foorilla and the Big Tech career sites).

Every record these scrapers return is a real post read from the site. Nothing is invented:
no placeholder cards, no made-up stipends. A field the site does not give stays empty.
"""
import hashlib
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from filters import calculate_match_score

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-IN,en;q=0.9",
}
TIMEOUT = 25

INDIA_RE = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|delhi|new delhi|noida|gurugram|gurgaon|hyderabad|pune|chennai|"
    r"kolkata|ahmedabad|jaipur|lucknow|chandigarh|indore|kochi|coimbatore|thiruvananthapuram|bhubaneswar|"
    r"nagpur|surat|vadodara|mohali|ghaziabad|faridabad|mysore|mysuru|visakhapatnam)\b", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)


def get(url, **kw):
    """GET with browser-like headers; raises on HTTP errors."""
    headers = dict(HEADERS, **kw.pop("headers", {}))
    r = requests.get(url, headers=headers, timeout=kw.pop("timeout", TIMEOUT), **kw)
    r.raise_for_status()
    return r


def post_json(url, payload, **kw):
    headers = dict(HEADERS, **{"Content-Type": "application/json", "Accept": "application/json"},
                   **kw.pop("headers", {}))
    r = requests.post(url, json=payload, headers=headers, timeout=kw.pop("timeout", TIMEOUT), **kw)
    r.raise_for_status()
    return r.json()


def html_to_text(html, limit=4000):
    if not html:
        return ""
    return re.sub(r"\s+", " ", BeautifulSoup(html, "lxml").get_text(" ")).strip()[:limit]


def location_type(location):
    loc = location or ""
    if REMOTE_RE.search(loc):
        return "Remote"
    if INDIA_RE.search(loc):
        return "India"
    return "International"


def search_words(limit=3):
    """The chosen field's search phrases (fields.py), at most `limit`."""
    import fields
    return fields.search_terms()[:limit]


def record(source, title, company, location, link, *, job_id="", stipend="", stipend_numeric=0.0,
           currency="", skills=None, description="", posted="", org_type="Company", duration="",
           labelled_internship=False):
    """One listing in the shape scraper.py expects. Empty stays empty: nothing is guessed."""
    title = re.sub(r"\s+", " ", title or "").strip()
    company = re.sub(r"\s+", " ", company or "").strip() or "Unknown"
    location = re.sub(r"\s+", " ", location or "").strip()
    skills = [s for s in (skills or []) if s]
    numeric = float(stipend_numeric or 0)
    key = job_id or f"{title}|{company}|{link}"
    rec = {
        "id": hashlib.md5(f"{source.lower()}-{key}".encode()).hexdigest(),
        "job_id": str(job_id or ""),
        "company_name": company,
        "role_title": title,
        "location": location,
        "location_type": location_type(location),
        "duration": duration,
        "stipend": stipend,
        "stipend_numeric": numeric,
        "stipend_currency": currency,
        "required_skills": ", ".join(skills),
        "application_deadline": "",
        "apply_link": link,
        "source_platform": source,
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
        "org_type": org_type,
        "role_type": "Research" if "research" in title.lower() else "Applied",
        "match_score": calculate_match_score(title, skills, org_type, numeric),
        "posted": posted,
        "description": description,
    }
    if labelled_internship:
        rec["labelled_internship"] = True
    return rec


def dedupe(records):
    seen, out = set(), []
    for r in records:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


INTERN_RE = re.compile(r"\b(intern|interns|internship|internships|co-?op|trainee|apprentice\w*)\b", re.I)


def looks_like_internship(*texts):
    return any(INTERN_RE.search(t or "") for t in texts)

"""
Remote job boards: Remotive (public JSON API) and We Work Remotely (RSS feed).

Checked in a real browser on 18 Oct 2026:
  - Remotive: https://remotive.com/api/remote-jobs returns every live job as JSON
    (title, company_name, job_type, candidate_required_location, salary, tags, description, url).
    Its terms: link back to the Remotive URL, name Remotive as the source, and call the API at
    most about 4 times a day. So we cache the answer for 6 hours and keep the Remotive link.
    The free API only returns the latest 12 jobs (any search, category or limit: 12; the full
    list is their paid API), and none of the 12 was an internship on 18 Oct. So this mostly
    finds nothing; it is kept because it is honest and cheap.
  - We Work Remotely: https://weworkremotely.com/remote-jobs.rss lists about 90 current jobs
    ("Company: Role" titles, region, type, description). On 18 Oct it had 1 internship.
The old versions only looked at AI/ML feeds; the field filter (filters.py) now decides.
"""
import json
import time
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from sites._common import dedupe, get, html_to_text, looks_like_internship, record

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
REMOTIVE_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "remotive.json"
REMOTIVE_MAX_AGE = 6 * 3600
WWR_FEED = "https://weworkremotely.com/remote-jobs.rss"


def _remotive_jobs():
    try:
        if REMOTIVE_CACHE.exists() and time.time() - REMOTIVE_CACHE.stat().st_mtime < REMOTIVE_MAX_AGE:
            return json.loads(REMOTIVE_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    jobs = get(REMOTIVE_API).json().get("jobs", [])
    try:
        REMOTIVE_CACHE.parent.mkdir(exist_ok=True)
        REMOTIVE_CACHE.write_text(json.dumps(jobs), encoding="utf-8")
    except OSError:
        pass
    return jobs


def parse_remotive(jobs):
    out = []
    for j in jobs:
        title, jtype = j.get("title", ""), j.get("job_type", "")
        if not looks_like_internship(title, jtype):
            continue
        out.append(record(
            "Remotive", title, j.get("company_name"),
            f"Remote ({j.get('candidate_required_location') or 'Worldwide'})",
            j.get("url", ""), job_id=j.get("id", ""),
            stipend=j.get("salary") or "", skills=j.get("tags") or [],
            description=html_to_text(j.get("description")), posted=(j.get("publication_date") or "")[:10],
            labelled_internship="intern" in jtype.lower()))
    return dedupe(out)


def scrape_remotive():
    jobs = _remotive_jobs()
    out = parse_remotive(jobs)
    logger.info(f"Remotive: {len(jobs)} live jobs, {len(out)} internships")
    return out


def parse_wwr(xml_text):
    soup = BeautifulSoup(xml_text, "xml")
    out = []
    for item in soup.find_all("item"):
        raw = (item.find("title").text if item.find("title") else "").strip()
        jtype = item.find("type").text if item.find("type") else ""
        desc = html_to_text(item.find("description").text if item.find("description") else "")
        if not looks_like_internship(raw, jtype):
            continue
        company, _, title = raw.partition(": ")
        if not title:
            company, title = "", raw
        region = item.find("region").text if item.find("region") else ""
        link = item.find("link").text.strip() if item.find("link") else ""
        skills = [s.strip() for s in (item.find("skills").text if item.find("skills") else "").split(",")]
        out.append(record("We Work Remotely", title, company, f"Remote ({region or 'Anywhere'})", link,
                          job_id=link, skills=skills, description=desc,
                          posted=(item.find("pubDate").text if item.find("pubDate") else "")[:16]))
    return dedupe(out)


def scrape_weworkremotely():
    out = parse_wwr(get(WWR_FEED).text)
    logger.info(f"We Work Remotely: {len(out)} internships in the feed")
    return out


# Old names, kept so nothing that imports them breaks
scrape_linkedin = scrape_remotive
scrape_indeed = scrape_weworkremotely

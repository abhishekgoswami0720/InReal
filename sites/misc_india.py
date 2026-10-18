"""
Cutshort internships.

Checked in a real browser on 18 Oct 2026. The old scraper opened
https://cutshort.io/jobs/ai-ml?type=internship and looked for div.job-card, which no longer
exists, so it always returned nothing. The page https://cutshort.io/jobs/internship-jobs is
server-rendered (Next.js) and carries every listed internship in its __NEXT_DATA__ JSON
(23 on 18 Oct): headline, company, locations, salaryRange (INR per month), allSkills, the
description (sanitizedComment) and publicUrl. We read that JSON; the field filter keeps the
student's field.
"""
import json

from bs4 import BeautifulSoup
from loguru import logger

from sites._common import dedupe, get, html_to_text, record

CUTSHORT_URL = "https://cutshort.io/jobs/internship-jobs"


def _stipend(rng):
    if not rng or rng.get("currency") != "INR":
        return "", 0.0
    lo, hi = rng.get("min") or 0, rng.get("max") or 0
    per = {"MONTH": "/month", "YEAR": "/year"}.get(rng.get("duration"), "")
    if per == "/year":            # turn yearly figures into monthly so the ₹5,000/month check works
        lo, hi, per = lo / 12, hi / 12, "/month"
    if not (lo or hi):
        return "", 0.0
    text = f"₹ {lo:,.0f}{per}" if not hi or lo == hi else f"₹ {lo:,.0f} - {hi:,.0f}{per}"
    return text, float(lo or hi)


def parse_cutshort(html):
    tag = BeautifulSoup(html, "lxml").find("script", id="__NEXT_DATA__")
    if not tag:
        return []
    queries = json.loads(tag.string)["props"]["pageProps"]["dehydratedState"]["queries"]
    jobs = []
    for q in queries:
        data = ((q.get("state") or {}).get("data") or {}).get("data") or {}
        jobs = (data.get("pageData") or {}).get("jobs") or jobs
    out = []
    for j in jobs:
        stipend, numeric = _stipend(j.get("salaryRange"))
        out.append(record(
            "Cutshort", j.get("headline", ""), (j.get("companyDetails") or {}).get("name"),
            ", ".join(j.get("locations") or []) or "India", j.get("publicUrl", ""),
            job_id=j.get("_id", ""), stipend=stipend, stipend_numeric=numeric,
            currency="INR" if stipend else "", skills=j.get("allSkills") or [],
            description=html_to_text(j.get("sanitizedComment")),
            # the page also lists a few non-internships ("process executive - voice process");
            # trust Cutshort's own "Internship" skill tag, else the title must say intern
            labelled_internship=any(s.lower() == "internship" for s in j.get("allSkills") or [])))
    return dedupe(out)


def scrape_cutshort():
    out = parse_cutshort(get(CUTSHORT_URL).text)
    logger.info(f"Cutshort: {len(out)} internships on {CUTSHORT_URL}")
    return out

"""
Opens a listing's apply link the way a candidate would and reports what happened:
the redirect chain, where it ended up, the HTTP status, and whether the page says
the internship is closed.

The page text itself is NOT used for the scam check. Portal pages carry their own
boilerplate (Internshala advertises its paid trainings on every page, for example),
which would look like a "course sold as an internship". The scam check reads the
listing text each scraper already cut out of the page.
"""
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}
MAX_BYTES = 1_500_000
# Naukri/Foundit (Akamai) and LinkedIn answer scripts with these: the page exists, we just can't see it
BLOCKED_CODES = {401, 403, 429, 503, 999}
CLOSED_RE = re.compile(
    r"no longer accepting applications|this (internship|job|opportunity) (has )?(expired|closed)"
    r"|applications? (are |is )?(now )?closed|job is no longer (available|active)"
    r"|this job has expired|position has been filled|registrations? (are |is )?closed",
    re.I,
)


def domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def resolve(url: str, timeout: float = 12.0) -> dict:
    out = {"url": url, "final_url": url, "final_domain": domain(url), "chain": [],
           "http_status": None, "link_state": "unreachable", "closed_phrase": ""}
    if not url or not url.lower().startswith(("http://", "https://")):
        out["link_state"] = "invalid"
        return out
    try:
        with requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True) as r:
            out["chain"] = [h.url for h in r.history] + [r.url]
            out["final_url"] = r.url
            out["final_domain"] = domain(r.url)
            out["http_status"] = r.status_code
            body = b""
            if r.status_code == 200 and "html" in r.headers.get("content-type", "html"):
                for part in r.iter_content(65536):
                    body += part
                    if len(body) >= MAX_BYTES:
                        break
    except requests.exceptions.SSLError:
        out["link_state"] = "bad_certificate"
        return out
    except requests.exceptions.RequestException as e:
        out["error"] = type(e).__name__
        return out

    status = out["http_status"]
    if status in (404, 410):
        out["link_state"] = "dead"
    elif status in BLOCKED_CODES:
        out["link_state"] = "portal_blocks_bots"
    elif status and status >= 400:
        out["link_state"] = "error"
    else:
        out["link_state"] = "ok"
        if body:
            soup = BeautifulSoup(body, "lxml")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            m = CLOSED_RE.search(" ".join(soup.get_text(" ").split()))
            if m:
                out["link_state"] = "closed"
                out["closed_phrase"] = m.group(0)
    return out

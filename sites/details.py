"""
Full post text for the sites whose search page shows only a short snippet (about 150-200
characters): Talent.com, SimplyHired and Careerjet. With so little text the scam check cannot
judge a post, so every one of them went to Review (18 Oct 2026: 20 of 20 Talent.com posts).

Checked in a real browser on 19 Oct 2026, each post's own page has the whole text:
  - Talent.com /view?id=...  : a JobPosting in <script type="application/ld+json"> (about 2,600
    characters), or on some posts only the text under the "Job description" heading. Plain requests work, so this runs at "Load 5 more" time, only for the 5 posts
    being checked (fill_details below), not for every post found.
  - SimplyHired /job/<key>   : pageProps.jobDescriptionHtml in __NEXT_DATA__ (about 3,300).
  - Careerjet /jobad/<id>    : a JobPosting in ld+json (about 4,200).
SimplyHired and Careerjet refuse scripts, so their pages are read inside the visible Chrome
window that already opened for the search (fetch_in_page), right after each results page.
"""
import json

from loguru import logger

from sites._common import get, html_to_text

DETAIL_TEXT_LIMIT = 4000


def _postings(data):
    """Every JSON-LD object, flattening @graph lists."""
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict):
            if isinstance(item.get("@graph"), list):
                yield from _postings(item["@graph"])
            else:
                yield item


def jobposting_text(scripts):
    """Text of the JobPosting description in the given ld+json script bodies ('' if none)."""
    best = ""
    for body in scripts or []:
        try:
            data = json.loads(body)
        except (TypeError, ValueError):
            continue
        for item in _postings(data):
            kind = item.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if item.get("description") and ("JobPosting" in kinds or "employmentType" in item or "title" in item):
                text = html_to_text(item["description"], DETAIL_TEXT_LIMIT)
                if len(text) > len(best):
                    best = text
    return best


def ld_json_scripts(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "lxml")
    return [s.string or s.get_text() for s in soup.find_all("script", type="application/ld+json")]


def text_under_heading(html, heading="Job description"):
    """The text of the block right after a heading such as "Job description" (for pages without
    a JobPosting; their class names are generated, so the visible heading is what we can rely on)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup.find_all(True):
        if tag.find(True) is None and tag.get_text(strip=True).lower() == heading.lower():
            block = tag.find_next_sibling()
            if block is not None:
                return html_to_text(str(block), DETAIL_TEXT_LIMIT)
    return ""


# ---------- at "Load 5 more" time, with plain requests ----------
def _talent(link):
    """About 7 in 10 Talent.com posts carry a JobPosting; the rest only show the text under a
    "Job description" heading (6 of 20 on 19 Oct 2026), so both are tried."""
    html = get(link).text
    return jobposting_text(ld_json_scripts(html)) or text_under_heading(html)


FETCHERS = {"Talent.com": _talent}


def fill_details(rows, min_chars):
    """For rows from a site in FETCHERS whose text is shorter than min_chars, read the post's own
    page and put its full text in row['description']. Returns how many got longer text.
    A failed page is skipped: the row keeps its snippet (and the short-text rule sends it to Review)."""
    filled = missed = 0
    for row in rows:
        fetch = FETCHERS.get(row.get("source_platform", ""))
        desc = str(row.get("description") or "").strip()
        if not fetch or len(desc) >= min_chars or not row.get("apply_link"):
            continue
        try:
            text = fetch(row["apply_link"])
        except Exception as e:
            logger.warning(f"{row['source_platform']} details for {row['apply_link']} failed: {e}")
            continue
        if len(text) > len(desc):
            row["description"] = text
            filled += 1
        else:
            missed += 1
            logger.warning(f"{row['source_platform']}: no full text found on {row['apply_link']}")
    if filled or missed:
        logger.info(f"Read the full post for {filled} listing(s) before the scam check"
                    + (f"; {missed} kept only the short snippet" if missed else ""))
    return filled


# ---------- during the search, inside the visible Chrome window ----------
# Runs in the site's own page, so its cookies and the passed verification apply; 5 at a time.
_FETCH_JS = """async ([urls, mode]) => {
  const out = {};
  for (let i = 0; i < urls.length; i += 5) {
    await Promise.all(urls.slice(i, i + 5).map(async (u) => {
      try {
        const r = await fetch(u);
        if (!r.ok) return;
        const d = new DOMParser().parseFromString(await r.text(), 'text/html');
        if (mode === 'next') {
          const nd = d.getElementById('__NEXT_DATA__');
          out[u] = nd ? (JSON.parse(nd.textContent).props.pageProps.jobDescriptionHtml || '') : '';
        } else {
          out[u] = [...d.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent);
        }
      } catch (e) {}
    }));
  }
  return out;
}"""


def fetch_in_page(page, records, mode):
    """mode 'next' (SimplyHired: __NEXT_DATA__) or 'ldjson' (Careerjet). Replaces each record's
    snippet with the full text when the post's page gives a longer one."""
    urls = [r["apply_link"] for r in records if r.get("apply_link")]
    if not urls:
        return 0
    try:
        got = page.evaluate(_FETCH_JS, [urls, mode]) or {}
    except Exception as e:
        logger.warning(f"Reading full posts in the browser failed: {e}")
        return 0
    filled = 0
    for r in records:
        value = got.get(r.get("apply_link"))
        text = html_to_text(value, DETAIL_TEXT_LIMIT) if mode == "next" else jobposting_text(value)
        if len(text) > len(r.get("description") or ""):
            r["description"] = text
            filled += 1
    return filled

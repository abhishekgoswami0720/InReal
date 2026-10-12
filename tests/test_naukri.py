"""Offline tests for Naukri: trimmed copies of the live search and detail pages (no network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genuine import check_listing  # noqa: E402
from scraper import evaluate  # noqa: E402
from sites.naukri import URLS, parse_detail_page, parse_list_page  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_one_search_per_paid_range():
    assert [u.split("qcstipend=")[1] for u in URLS] == ["0To10", "10To20", "20To30", "30To40", "40To50"]


def test_list_selectors():
    records = parse_list_page(load("naukri_list.html"))
    assert [r["company_name"] for r in records] == ["Varroc", "Arcitech", "Tower Research Capital"]
    varroc, arcitech, tower = records
    assert varroc["role_title"] == "Intern - AI/ML"
    assert varroc["stipend"] == "20,000/month" and varroc["stipend_numeric"] == 20000  # old code: always ""
    assert varroc["duration"] == "No fixed duration" and varroc["location"] == "Pune"
    assert varroc["posted"] == "Starts within 1 month" and varroc["company_rating"] == "3.7"
    assert arcitech["apply_link"].endswith("-290926502549")
    assert tower["stipend"] == "Unpaid" and tower["stipend_numeric"] == 0


def test_detail_jsonld():
    d = parse_detail_page(load("naukri_detail.html"))
    assert d["aggregated"] is True
    assert d["date_posted"] == "2026-09-29" and d["application_deadline"] == "2026-12-28"
    assert "Python" in d["detail_skills"]
    assert d["openings"] == "1" and d["applicants"] == "100+" and d["posted"] == "1 week ago"
    assert "Conversion: Performance" in d["description"] and "<p>" not in d["description"]


def test_end_to_end_with_aggregated_flag():
    records = parse_list_page(load("naukri_list.html"))
    records[1].update(parse_detail_page(load("naukri_detail.html")))
    out = {(i["company_name"]): (kept, reason, i.get("trust_flags", "")) for i, kept, reason in evaluate("naukri", records)}
    assert out["Varroc"][:2] == (True, "")
    assert out["Arcitech"][0] is True and "Copied by the portal" in out["Arcitech"][2]
    assert out["Tower Research Capital"][:2] == (False, "Unpaid")


def test_aggregated_is_only_a_flag():
    reason, flags = check_listing({"role_title": "AI Intern", "stipend": "15,000/month",
                                   "stipend_numeric": 15000, "aggregated": True})
    assert reason is None and any("Copied by the portal" in f for f in flags)

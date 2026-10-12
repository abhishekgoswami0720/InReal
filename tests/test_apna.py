"""Offline tests for Apna: trimmed copies of the live search and job pages (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper import evaluate  # noqa: E402
from sites.apna import SEARCH, parse_detail_page, parse_pay, parse_search_page  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_search_url_is_the_one_that_filters():
    assert SEARCH.startswith("https://apna.co/jobs?search=true&text=")


def test_card_selectors_ignore_inline_style():
    iqvia, sprinklr = parse_search_page(load("apna_search.html"))
    assert iqvia["role_title"] == "AI/ML Research and Development Intern" and iqvia["company_name"] == "IQVIA"
    assert iqvia["location"] == "Kochi"                     # not ".css-q7mezt{...}Kochi"
    assert iqvia["stipend"] == "" and iqvia["stipend_hidden_by_site"] is True
    assert iqvia["work_tags"] == "Work from Office, Full Time, Freshers only"
    assert iqvia["apply_link"] == "https://apna.co/job/kochi/intern-1573157134"
    assert sprinklr["stipend"] == "₹15,000 - ₹25,000" and sprinklr["stipend_numeric"] == 15000


def test_detail_jsonld():
    d = parse_detail_page(load("apna_detail.html"))
    assert d["posted"] == "2026-10-09" and d["application_deadline"] == "2026-11-08"
    assert "Generative AI" in d["description"] and d["industries"] == "Research & Development"


def test_pay_and_end_to_end():
    assert parse_pay("Not disclosed") == 0 and parse_pay("₹3,00,000 - ₹4,00,000") == 25000
    out = {i["company_name"]: (k, r, i.get("trust_flags", "")) for i, k, r in evaluate("apna", parse_search_page(load("apna_search.html")))}
    assert out["IQVIA"] == (True, "", "") and out["Sprinklr India Private Limited"] == (True, "", "")

"""Offline tests for Foundit: trimmed copies of the live JSON responses (no network)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import evaluate  # noqa: E402
from sites.foundit import parse_detail_json, parse_search_json  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_search_fields():
    sparks, simple, maxgen = parse_search_json(load("foundit_search.json"))
    assert sparks["role_title"] == "Free AI/ML Internship" and sparks["company_name"] == "Sparks to Ideas"
    assert sparks["stipend"] == "₹ 4,167 - 8,333 /month" and sparks["stipend_numeric"] == 4167
    assert sparks["third_party"] is True and sparks["application_deadline"]
    assert sparks["apply_link"] == "https://www.foundit.in/job/free-ai-ml-internship-sparks-to-ideas-ahmedabad-rajkot-gandhinagar-69386620"
    assert "recruiter" not in json.dumps(sparks).lower()  # never store the recruiter's name or phone
    assert simple["stipend"] == "" and simple["stipend_hidden_by_site"] is True
    assert maxgen["stipend_numeric"] == 20833


def test_detail_description():
    d = parse_detail_json(load("foundit_detail.json"))
    assert d["description"].startswith("Description We are seeking a motivated Free AI/ML Intern")


def test_end_to_end():
    recs = parse_search_json(load("foundit_search.json"))
    out = {i["company_name"]: (kept, reason, i.get("trust_flags", "")) for i, kept, reason in evaluate("foundit", recs)}
    assert out["Sparks to Ideas"][:2] == (False, "Stipend below ₹5,000/month (₹ 4,167 - 8,333 /month)")
    assert out["Simple Energy"] == (True, "", "")
    assert out["Maxgen Technologies Private Limited"][0] is True


def test_consultant_flag():
    from genuine import check_listing
    reason, flags = check_listing({"role_title": "ML Intern", "stipend": "₹ 10,000 /month", "stipend_numeric": 10000,
                                   "third_party": True})
    assert reason is None and "Posted by a recruiter or consultant, not the company itself" in flags

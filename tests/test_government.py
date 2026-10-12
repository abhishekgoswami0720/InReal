"""Offline tests for the AICTE National Internship Portal (Govt of India) scraper (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper import evaluate  # noqa: E402
from sites.government import parse_items  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def items():
    return parse_items(json.loads((FIX / "aicte_search.json").read_text(encoding="utf-8")))


def test_fields():
    pixel, webneural, edurank, tulip = items()
    assert pixel["company_name"] == "pixelwind technologies" and pixel["poster_category"] == "Corporate"
    assert pixel["stipend"] == "₹10,000 / month" and pixel["stipend_numeric"] == 10000
    assert pixel["apply_link"] == "https://internship.aicte-india.org/internships/1-INTERNSHIP_17917149596acb668f32cb1"
    assert pixel["application_deadline"] == "2026-10-31" and pixel["openings"] == 70
    assert tulip["org_type"] == "Government" and pixel["org_type"] == "Company"
    assert webneural["location_type"] == "Remote"


def test_genuine_checks_on_portal_listings():
    out = {i["company_name"]: (k, r, i.get("trust_flags", "")) for i, k, r in evaluate("government", items())}
    assert out["pixelwind technologies"][1] == "Not an AI/ML role"
    kept, _, flags = out["Web Neural Infotech"]
    assert kept and "Advertises another website in the title" in flags
    assert "Sounds like a training programme sold as an internship" in flags   # "Guaranteed Certification"
    assert out["EduRankAI"][1] == "Unpaid"
    assert out["State Mission Management Unit, AMRUT Kerala"][1] == "Not an AI/ML role"


def test_mass_openings_flag():
    from genuine import check_listing
    _, flags = check_listing({"role_title": "ML Intern", "stipend": "₹10,000 / month", "stipend_numeric": 10000, "openings": 70})
    assert "70 openings for one internship" in flags


def test_portal_titles_need_not_say_intern_and_course_titles_are_flagged():
    base = items()[1]
    posts = [{**base, "id": "a", "role_title": "incorporation of Artificial intelligence and Machine learning in Defence",
              "company_name": "HQ Southern Comd", "poster_category": "Army", "description": "", "stipend": "Up to ₹75,000", "stipend_numeric": 75000},
             {**base, "id": "b", "role_title": "Machine Learning with Python", "company_name": "KITECH VISTA PRIVATE LIMITED",
              "description": "", "stipend": "₹5,000 / month", "stipend_numeric": 5000}]
    out = {i["company_name"]: (k, r, i.get("trust_flags", "")) for i, k, r in evaluate("government", posts)}
    assert out["HQ Southern Comd"][:2] == (True, "")
    assert out["KITECH VISTA PRIVATE LIMITED"][0] and "training programme" in out["KITECH VISTA PRIVATE LIMITED"][2]

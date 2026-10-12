"""Offline tests for Shine: trimmed copies of the live search and job pages (no network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import evaluate  # noqa: E402
from sites.shine import parse_detail_page, parse_salary, parse_search_page  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_search_selectors():
    recs = parse_search_page(load("shine_search.html"))
    # the "3 to 8 Yrs" job card is skipped
    assert [r["role_title"] for r in recs] == ["MACHINE LEARNING AI INTERNSHIP AT AHMEDABAD", "Generative Ai Internship in Pune"]
    m = recs[0]
    assert m["company_name"] == "Maxgen Technologies Private Limited"
    assert m["location"] == "Ahmedabad" and m["experience"] == "0 to 4 Yrs" and m["posted"] == "2 weeks ago"
    assert m["stipend"] == "" and m["stipend_numeric"] == 0
    assert m["required_skills"] == "Data Science, Machine Learning, AI"
    assert m["apply_link"] == "https://www.shine.com/jobs/machine-learning-ai-internship-at-ahmedabad/maxgen-technologies-private-limited/19593657"


def test_detail_jsonld():
    d = parse_detail_page(load("shine_detail.html"))
    assert d["date_posted"] == "2026-09-26" and d["application_deadline"] == "2026-11-25"
    assert "job placement" in d["description"] and d["industries"] == "IT Services & Consulting"


def test_salary():
    assert parse_salary("Not Disclosed") == 0
    assert parse_salary("₹ 12 Lakh/Yr") == 100000
    assert parse_salary("₹ 10,000 - 15,000 Per Month") == 10000


def test_training_programme_and_many_towns_are_flagged():
    recs = parse_search_page(load("shine_search.html"))
    recs[0].update(parse_detail_page(load("shine_detail.html")))
    out = {i["role_title"]: (kept, i.get("trust_flags", "")) for i, kept, _ in evaluate("shine", recs)}
    kept, flags = out["MACHINE LEARNING AI INTERNSHIP AT AHMEDABAD"]
    assert kept and "Sounds like a training programme sold as an internship" in flags
    kept, flags = out["Generative Ai Internship in Pune"]
    assert kept and "One post listed for 8 towns" in flags


def test_fixes_from_the_first_laptop_run():
    # 12 Oct 02:28: "1.0 - 2.0 Lakh/Yr" was read as Rs 1/month and dropped
    assert parse_salary("1.0 - 2.0 Lakh/Yr") == 8333
    recs = parse_search_page(load("shine_search.html"))
    base = recs[0]
    posts = [
        {**base, "id": "u1", "role_title": "Audio AI Intern Speech Data Labelling (Unpaid Internship)"},
        {**base, "id": "u2", "role_title": "AI Intern(Non Paid) (Hyderabad)"},
        {**base, "id": "t1", "role_title": "Data Science & Generative AI Training & Internship", "location": "Delhi"},
        {**base, "id": "ok", "role_title": "Machine Learning Intern", "location": "Pune",
         "description": "This is not an unpaid role: Rs 15,000 a month."},
    ]
    out = {i["id"]: (kept, reason, i.get("trust_flags", "")) for i, kept, reason in evaluate("shine", posts)}
    assert out["u1"][0] is False and out["u1"][1].startswith("Unpaid (the post says")
    assert out["u2"][0] is False
    assert out["t1"][0] is True and "training programme" in out["t1"][2]
    assert out["ok"][0] is True
    # "Not Disclosed" on Shine is not flagged on every card
    assert "Stipend amount not stated" not in out["ok"][2]

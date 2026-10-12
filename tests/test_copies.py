"""Mass re-posting (Foundit laptop run, 12 Oct 2026) is shown once, with the warnings of every copy."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper import evaluate  # noqa: E402


def post(i, title, company, location, description=""):
    return {"id": str(i), "role_title": title, "company_name": company, "location": location,
            "location_type": "India", "stipend": "₹ 20,833 - 41,667 /month", "stipend_numeric": 20833,
            "stipend_currency": "INR", "required_skills": "Data Science, Machine Learning", "description": description}


def test_maxgen_flood_collapses_to_one_with_all_warnings():
    titles = ["DATA SCIENCE INTERNSHIP AT PUNE", "DATA SCIENCE INTERNSHIP AN AHMEDABAD", "DATA SCIENCE -ML INTERNSHIP AT PUNE",
              "Data Science Ml Internship Ahmedabad", "DATA SCIENCE INTERNSHIP AT AHMEDBAAD", "DATA SCIENCE INTERNSHIP PUNE",
              "DATA SCIENCE INTERNSHIP AT PUNE"]
    posts = [post(i, t, "Maxgen Technologies Private Limited", "Pune, Satara, Sangli") for i, t in enumerate(titles)]
    posts[3]["description"] = "machine learning program with job placement"   # only one copy's page was read
    posts.append(post(99, "MACHINE LEARNING INTERNSHIP AT PUNE", "Maxgen Technologies Private Limited", "Pune"))
    res = evaluate("foundit", posts)
    kept = [i for i, k, _ in res if k]
    assert [i["role_title"] for i in kept] == ["DATA SCIENCE INTERNSHIP AT PUNE", "MACHINE LEARNING INTERNSHIP AT PUNE"]
    flags = kept[0]["trust_flags"]
    assert "Sounds like a training programme sold as an internship" in flags
    assert "Same company posted 7 copies of this internship" in flags
    assert sum(1 for _, k, r in res if r.startswith("Copy of another post")) == 6


def test_hidden_company_name_is_flagged():
    res = evaluate("foundit", [post(1, "DATA SCIENCE INTERNSHIP AT AHMEDABAD", "**********", "Ahmedabad")])
    assert res[0][1] is True and "Company name hidden" in res[0][0]["trust_flags"]


def test_different_roles_from_one_company_stay():
    roles = ["AI/ML", "Data Science", "Business Analytics", "Artificial Intelligence (AI)", "Data Analytics"]
    res = evaluate("internshala", [post(i, r, "Codeatrix", "Work from home") for i, r in enumerate(roles)])
    assert sum(1 for _, k, _ in res if k) == 5   # different roles, so nothing is collapsed

"""Offline tests for LinkedIn: trimmed copies of the live guest API responses (no network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import evaluate  # noqa: E402
from sites.linkedin import SEARCH_CONFIGS, parse_detail_html, parse_search_html, query_wanted  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_search_card_selectors():
    recs = parse_search_html(load("linkedin_search.html"), "India · ML")
    assert [r["company_name"] for r in recs] == ["ERIC Robotics", "Sparks To Ideas", "Sparks To Ideas", "Meril"]
    eric = recs[0]
    assert eric["role_title"] == "Machine Learning Intern" and eric["job_id"] == "4459699809"
    assert eric["location"] == "Pune Division, Maharashtra, India" and eric["location_type"] == "India"
    assert eric["apply_link"] == "https://in.linkedin.com/jobs/view/machine-learning-intern-at-eric-robotics-4459699809"
    assert eric["posted"] == "2026-08-02"
    assert eric["stipend"] == "" and eric["stipend_numeric"] == 0 and eric["stipend_hidden_by_site"] is True


def test_detail_selectors():
    d = parse_detail_html(load("linkedin_detail.html"))
    assert d["employment_type"] == "Full-time" and d["industries"] == "Staffing and Recruiting"
    assert d["applicants"] == "Be among the first 25 applicants"
    assert d["aggregated"] is True and d["provided_by"] == "Shine.com"
    assert "IT training and development company" in d["description"]


def test_end_to_end():
    recs = parse_search_html(load("linkedin_search.html"), "India · ML")
    recs[1].update(parse_detail_html(load("linkedin_detail.html")))
    # a third Sparks To Ideas copy in another town (the live search had several)
    recs.append({**recs[2], "id": "x", "job_id": "1", "location": "Rajkot, Gujarat, India"})
    out = {(i["company_name"], i["location"]): (kept, reason, i.get("trust_flags", "")) for i, kept, reason in evaluate("linkedin", recs)}
    assert out[("ERIC Robotics", "Pune Division, Maharashtra, India")] == (True, "", "")  # no fake "stipend not stated" flag
    assert out[("Meril", "Bengaluru, Karnataka, India")][:2] == (False, "Not labelled as an internship")
    sparks = out[("Sparks To Ideas", "Amreli, Gujarat, India")]
    assert sparks[0] is True
    assert "Same post repeated in 3 towns of Gujarat" in sparks[2] and "Copied by the portal" in sparks[2]


def test_big_company_in_many_cities_is_not_flagged():
    # Live result 12 Oct: DoorDash posted one ML intern role in 4 US cities; that is normal
    base = parse_search_html(load("linkedin_search.html"), "USA · ML")[0]
    recs = [{**base, "id": str(n), "company_name": "DoorDash", "role_title": "Machine Learning Intern (Masters) - Summer 2027",
             "location": loc} for n, loc in enumerate(["San Francisco, CA", "Sunnyvale, CA", "New York, NY", "Seattle, WA"])]
    assert all(kept and flags == "" for (_, kept, _), flags in
               ((r, r[0].get("trust_flags", "")) for r in evaluate("linkedin", recs)))


def test_dashboard_checkboxes_still_choose_searches():
    all_regions = ["india", "worldwide", "usa", "europe", "remote"]
    india_only = [s for s in SEARCH_CONFIGS if query_wanted(s[0], s[1], ["india"], ["ml", "ai"])]
    assert india_only and all("india" in loc.lower() for _, loc, _ in india_only)
    assert len([s for s in SEARCH_CONFIGS if query_wanted(s[0], s[1], all_regions, [])]) == len(SEARCH_CONFIGS)

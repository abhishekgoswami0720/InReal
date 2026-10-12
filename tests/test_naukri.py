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


def test_first_pages_of_narrow_searches_only():
    assert len(URLS) == 20 and all("qcstipend=" in u for u in URLS)
    assert URLS[0] == "https://www.naukri.com/ai-ml-internship-jobs-in-india?qcstipend=0To10"
    assert "https://www.naukri.com/machine-learning-internship-jobs?qcstipend=10To20" in URLS


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
    # experience comes from the link on internship cards; only a fixed duration counts as Naukri's internship label
    assert [r["min_experience"] for r in records] == [0, 0, 0]
    assert [r["labelled_internship"] for r in records] == [False, True, False]


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


def _card(title, duration="3 months duration", exp=0):
    return {"role_title": title, "company_name": "Acme", "stipend": "15,000/month", "stipend_numeric": 15000,
            "stipend_currency": "INR", "duration": duration, "required_skills": "", "location": "Pune",
            "labelled_internship": duration[0].isdigit(), "min_experience": exp}


def test_titles_missed_on_12_oct_laptop_run():
    """Real Naukri posts the old rules dropped (laptop run, 12 Oct 07:04)."""
    out = {i["role_title"]: (kept, reason) for i, kept, reason in evaluate("naukri", [
        _card("AIML Intern"), _card("AI-Intern"),
        _card("AI / Generative AI Engineer", "6 months duration"),   # Naukri files it as an internship
        _card("Web Developer Fresher", "No fixed duration", 5),
        _card("Data Annotation Engineer", "6 months duration"),
        _card("AI Filmmaking Trainee", "6 months duration"),
        _card("Placement Coordinator", "No fixed duration", 1),
    ])}
    assert out["AIML Intern"] == (True, "") and out["AI-Intern"] == (True, "")
    assert out["AI / Generative AI Engineer"] == (True, "")
    assert out["Web Developer Fresher"] == (False, "Not labelled as an internship")
    assert out["Data Annotation Engineer"] == (False, "Not an AI/ML role")
    assert out["AI Filmmaking Trainee"] == (False, "Not an AI/ML role")
    assert out["Placement Coordinator"] == (False, "Not labelled as an internship")


def test_experience_rules():
    res = {i["min_experience"]: (kept, reason, i.get("trust_flags", "")) for i, kept, reason in evaluate("naukri", [
        _card("AI Intern", exp=0), _card("ML Intern", exp=2), _card("AI Engineer Intern", exp=4)])}
    assert res[0] == (True, "", "")
    assert res[2][0] is True and "Asks for 2+ years of experience" in res[2][2]
    assert res[4] == (False, "Asks for 4+ years of experience", "")


def test_training_institute_name_is_a_flag():
    reason, flags = check_listing({"role_title": "AI Intern", "company_name": "Fireblaze Ai School",
                                   "stipend": "5,000/month", "stipend_numeric": 5000})
    assert reason is None and any("training institute" in f for f in flags)
    assert all(";" not in f for f in flags)   # ";" separates flags in the CSV (07:42 dashboard counted this one as 2)
    _, gov = check_listing({"role_title": "AI Intern", "company_name": "School of Planning", "org_type": "Government",
                            "stipend": "5,000/month", "stipend_numeric": 5000})
    assert not any("training institute" in f for f in gov)


def test_internship_that_converts_to_full_time_is_kept():
    from filters import internship_rejection_reason
    assert internship_rejection_reason("AI/ML Engineering Intern Internship to Full-Time", [], "shine") is None
    assert internship_rejection_reason("【Class of 2028／Full-Time】Applied Scientists", [], "linkedin") is not None
    assert internship_rejection_reason("Full Time ML Engineer Intern", [], "linkedin") == "Title has 'full time'"


def test_general_ai_word_is_not_enough_for_non_ml_work():
    from filters import internship_rejection_reason as r
    for t in ["Creative design & AI intern", "Artificial Intelligence Sales Intern",
              "AI INTERNSHIP FILM & CREATIVE INDUSTRY", "AI Intern Global Communications & Marketing"]:
        assert r(t, [], "naukri") == "Not an AI/ML role", t
    for t in ["AI Intern", "AI-Intern", "Data & AI Intern (Brazil)", "Research and AI Intern",
              "Internship in Agentic AI and human-centered design", "AI Engineer Intern - Marketing Tech"]:
        assert r(t, [], "naukri") is None, t


def test_training_seller_flag_spreads_to_its_other_posts():
    def gov(title, company):
        return {"role_title": title, "company_name": company, "stipend": "₹5,000 / month", "stipend_numeric": 5000,
                "stipend_currency": "INR", "required_skills": "", "location": "Remote", "duration": "3 Months"}
    out = {i["role_title"]: i.get("trust_flags", "") for i, kept, _ in evaluate("government", [
        gov("Ai & Machine Learning Engineer Intern", "METATAARAKA™ AI INNOVATIONS PRIVATE LIMITED"),
        gov("Ai & Machine Learning Engineer Intern – 1 Year Fully Online Remote Internship with Employment "
            "Opportunity (Based on Successful Completion)", "METATAARAKA™ AI INNOVATIONS PRIVATE LIMITED"),
        gov("Machine Learning Intern", "TECHGRATION TECHNOLOGIES PRIVATE LIMITED"),
    ])}
    assert out["Ai & Machine Learning Engineer Intern"] == "Another post by this employer sounds like a training programme"
    assert out["Machine Learning Intern"] == ""


def test_coop_counts_and_french_german_posts_say_why():
    from filters import internship_rejection_reason as r
    assert r("Machine Learning Applied Scientist (Co-op)", [], "linkedin") is None
    assert r("2027 Spring Co-op Machine Learning AI, Cambridge", [], "linkedin") is None
    assert r("Stage - Applied Research in GenAI / NLP F/M", [], "linkedin") == "Posted in French/German ('stage')"
    assert r("Praktikum als Applied AI Engineer (m/w/d)", [], "linkedin").startswith("Posted in French/German")
    assert r("Backstage AI Engineer Intern", [], "linkedin") is None

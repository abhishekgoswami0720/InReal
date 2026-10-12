"""Fields of study: searches and the title check follow the field chosen for the run."""
import fields
from filters import internship_rejection_reason
from output_handler import sync_listings, _read_rows
import output_handler as oh


def teardown_function():
    fields.set_current("ai_ml")


def test_default_is_ai_ml_and_unknown_falls_back():
    fields.set_current(None)
    assert fields.current() == "ai_ml"
    fields.set_current("astrology")
    assert fields.current() == "ai_ml"


def test_medical_titles():
    fields.set_current("medical")
    assert internship_rejection_reason("Clinical Research Intern", [], "linkedin") is None
    assert internship_rejection_reason("Hospital Administration Internship", [], "shine") is None
    assert internship_rejection_reason("Machine Learning Intern", [], "linkedin") == "Not a Medicine & Healthcare role"
    # the shared rules still apply
    assert internship_rejection_reason("Senior Nurse Intern", [], "linkedin").startswith("Title has")


def test_ai_ml_unchanged():
    fields.set_current("ai_ml")
    assert internship_rejection_reason("Machine Learning Intern", [], "linkedin") is None
    assert internship_rejection_reason("Clinical Research Intern", [], "linkedin") == "Not an AI/ML role"


def test_word_boundaries():
    fields.set_current("hr_ops")
    assert not fields.matches("three month chrome extension internship")   # 'hr' inside other words
    assert fields.matches("hr intern")


def test_site_searches_follow_the_field():
    from sites import internshala, naukri, shine
    fields.set_current("medical")
    urls, pages = internshala.urls_for_field()
    assert urls[0].endswith("/internships/keywords-medical/") and pages == 5
    assert naukri.urls_for_field()[0].startswith("https://www.naukri.com/medical-internship-jobs")
    assert shine.search_for_field().endswith("/job-search/medical-internship-jobs")
    fields.set_current("ai_ml")
    assert naukri.urls_for_field() == naukri.URLS and shine.search_for_field() == shine.SEARCH


def test_a_post_in_two_fields_keeps_both(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "i.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "l.json")
    row = {"id": "x", "company_name": "A", "role_title": "Data Analyst Intern", "date_scraped": "2026-10-13"}
    sync_listings([{**row, "field": "ai_ml"}], [])
    sync_listings([{**row, "field": "data"}], [])
    assert _read_rows()[0]["field"] == "ai_ml;data"

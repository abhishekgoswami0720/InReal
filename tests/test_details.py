"""Full post text for the snippet-only sites (sites/details.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sites import details  # noqa: E402

FULL = "<p>Stipend: 10,000/month</p><p>Duration: 6 Months</p><p>" + "Real work on Angular and .NET. " * 20 + "</p>"


def test_jobposting_inside_a_graph_like_talent():
    page = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": []},
        {"@type": "JobPosting", "title": "SDE Intern", "description": FULL}]})
    text = details.jobposting_text([page])
    assert text.startswith("Stipend: 10,000/month") and len(text) > 500 and "<p>" not in text


def test_jobposting_without_type_like_careerjet():
    page = json.dumps({"validThrough": "2026-12-19", "employmentType": ["FULL_TIME", "INTERN"], "description": FULL})
    assert "Angular" in details.jobposting_text([page])
    assert details.jobposting_text(["not json", json.dumps({"@type": "Organization", "name": "x"})]) == ""


def test_ld_json_scripts_from_html():
    html = f'<html><head><script type="application/ld+json">{json.dumps({"@type": "JobPosting", "description": FULL})}</script></head></html>'
    assert "Angular" in details.jobposting_text(details.ld_json_scripts(html))


class FakePage:
    def __init__(self, answer):
        self.answer, self.args = answer, None

    def evaluate(self, js, args):
        self.args = args
        return self.answer


def test_fetch_in_page_simplyhired_and_careerjet():
    recs = [{"apply_link": "https://www.simplyhired.co.in/job/k1", "description": "short"},
            {"apply_link": "https://www.simplyhired.co.in/job/k2", "description": "short"}]
    page = FakePage({"https://www.simplyhired.co.in/job/k1": FULL})          # k2 failed in the page
    assert details.fetch_in_page(page, recs, "next") == 1
    assert page.args[1] == "next" and len(page.args[0]) == 2
    assert recs[0]["description"].startswith("Stipend") and recs[1]["description"] == "short"

    cj = [{"apply_link": "https://www.careerjet.co.in/jobad/x", "description": "short"}]
    page = FakePage({"https://www.careerjet.co.in/jobad/x": [json.dumps({"employmentType": "INTERN", "description": FULL})]})
    assert details.fetch_in_page(page, cj, "ldjson") == 1 and "Angular" in cj[0]["description"]


def test_fetch_in_page_survives_a_browser_error():
    class Broken:
        def evaluate(self, *a):
            raise RuntimeError("page closed")
    recs = [{"apply_link": "https://x/1", "description": "short"}]
    assert details.fetch_in_page(Broken(), recs, "next") == 0 and recs[0]["description"] == "short"


TALENT_NO_LD = """<html><body><div class="a1"><h1>SDET Intern</h1></div>
<div class="sc-9"><span class="sc-15">Job description</span>
<div class="sc-10"><p>Job Title: SDET Intern</p><p>Stipend: 6,000 - 10,000 per month</p><p>""" + "Testing web apps with Selenium. " * 20 + """</p></div></div>
<div data-testid="ListRelatedJobs">Other jobs</div></body></html>"""


def test_talent_page_without_jobposting_uses_the_job_description_block(monkeypatch):
    class R:
        text = TALENT_NO_LD
    monkeypatch.setattr(details, "get", lambda url: R)
    text = details._talent("https://in.talent.com/view?id=1")
    assert text.startswith("Job Title: SDET Intern") and "Stipend: 6,000" in text and "Other jobs" not in text


def test_fill_details_reports_misses(monkeypatch):
    monkeypatch.setitem(details.FETCHERS, "Talent.com", lambda link: "")
    rows = [{"source_platform": "Talent.com", "description": "short", "apply_link": "https://x/1"}]
    assert details.fill_details(rows, 300) == 0 and rows[0]["description"] == "short"


def test_stipend_from_text():
    f = details.stipend_from_text
    assert f("Location: Bangalore Stipend: 10,000/month Duration: 6 Months") == ("₹10,000 a month", 10000)
    assert f("Fresher Stipend: 6,000 – 10,000 per month About") == ("₹6,000 – ₹10,000 a month", 6000)
    assert f("stipend of INR 20k per month") == ("₹20,000 a month", 20000)
    assert f("Stipend: Up to 25,000/month") == ("Up to ₹25,000 a month", 25000)
    assert f("Stipend: 2.4 LPA")[1] == 20000
    assert f("Stipend: Unpaid") == ("Unpaid", 0.0)
    # no amount after the word "stipend": nothing is guessed
    assert f("Stipend: Performance-based. CTC after internship 6 LPA") == ("", 0.0)
    assert f("Stipend for 3 months will be given") == ("", 0.0)
    assert f("We pay a good salary of 30,000") == ("", 0.0)


def test_add_stipend_only_fills_an_empty_stipend_and_drops_the_flag():
    row = {"stipend": "", "stipend_numeric": 0, "description": "Stipend: 10,000/month",
           "trust_flags": "Stipend amount not stated; One post listed for 6 towns"}
    assert details.add_stipend(row) is True
    assert row["stipend"] == "₹10,000 a month" and row["stipend_numeric"] == 10000 and row["stipend_currency"] == "INR"
    assert row["trust_flags"] == "One post listed for 6 towns"
    kept = {"stipend": "₹20,000 a month", "stipend_numeric": 20000, "description": "Stipend: 5,000/month"}
    assert details.add_stipend(kept) is False and kept["stipend"] == "₹20,000 a month"


def test_performance_based_stipends_say_so():
    f = details.stipend_from_text
    assert f("Stipend: Performance-Based, up to 7,500/- FOR COLLEGE STUDENTS") == ("Up to ₹7,500 a month (performance-based)", 7500)
    assert f("Stipend: 7,500 – 15,000 (performance-based). Equal") == ("₹7,500 – ₹15,000 a month (performance-based)", 7500)

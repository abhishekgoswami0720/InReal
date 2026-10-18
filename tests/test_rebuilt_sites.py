"""Parsers of the scrapers rebuilt on 18 Oct 2026, run on small copies of what each site sent that day."""
import json

import fields
from sites import bigtech, misc_india, niche, rss_feeds


def setup_function(_):
    fields.set_current("software")


def teardown_function(_):
    fields.set_current(fields.DEFAULT)


def test_remotive_keeps_only_internships_and_links_back():
    jobs = [
        {"id": 1, "title": "Senior React Developer", "job_type": "full_time", "company_name": "A", "url": "u1"},
        {"id": 2, "title": "Software Engineering Intern", "job_type": "internship", "company_name": "B",
         "candidate_required_location": "India", "url": "https://remotive.com/remote-jobs/x-2",
         "salary": "", "tags": ["python"], "description": "<p>Build things</p>", "publication_date": "2026-10-14T20:33:44"},
    ]
    out = rss_feeds.parse_remotive(jobs)
    assert [r["role_title"] for r in out] == ["Software Engineering Intern"]
    r = out[0]
    assert r["apply_link"].startswith("https://remotive.com/") and r["source_platform"] == "Remotive"
    assert r["stipend"] == "" and r["stipend_numeric"] == 0      # nothing invented
    assert r["description"] == "Build things" and r["posted"] == "2026-10-14"


def test_wwr_splits_company_and_title():
    xml = """<rss><channel>
      <item><title>Lithic: Senior Software Engineer</title><type>Full-Time</type><link>https://weworkremotely.com/a</link></item>
      <item><title>Sezzle: Chargeback Operations Intern (Colombia)</title><region>Anywhere in the World</region>
            <type>Internship</type><link>https://weworkremotely.com/b</link><description>&lt;p&gt;Hi&lt;/p&gt;</description></item>
    </channel></rss>"""
    out = rss_feeds.parse_wwr(xml)
    assert len(out) == 1
    assert out[0]["company_name"] == "Sezzle" and out[0]["role_title"] == "Chargeback Operations Intern (Colombia)"
    assert out[0]["location_type"] == "Remote"


def test_cutshort_reads_next_data():
    data = {"props": {"pageProps": {"dehydratedState": {"queries": [{"state": {"data": {"data": {"pageData": {"jobs": [
        {"_id": "x1", "publicUrl": "https://cutshort.io/job/Sales-Intern-x1", "headline": "Sales Intern",
         "allSkills": ["Sales", "Internship"], "locations": ["Ahmedabad"], "companyDetails": {"name": "Unada Labs"},
         "salaryRange": {"duration": "MONTH", "currency": "INR", "min": 12000, "max": 20000},
         "sanitizedComment": "<p>Call clients</p>"},
        {"_id": "x2", "publicUrl": "https://cutshort.io/job/x2", "headline": "Process executive",
         "allSkills": ["Voice"], "locations": ["Hyderabad"], "companyDetails": {"name": "Vy"},
         "salaryRange": {"duration": "YEAR", "currency": "INR", "min": 240000, "max": 300000}},
    ]}}}}}]}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    out = misc_india.parse_cutshort(html)
    assert out[0]["company_name"] == "Unada Labs" and out[0]["stipend_numeric"] == 12000
    assert out[0]["location_type"] == "India" and out[0].get("labelled_internship")
    assert out[1]["stipend_numeric"] == 20000 and not out[1].get("labelled_internship")   # yearly -> monthly


def test_talent_cards():
    html = """<article data-testid="job-card-unified"><header><h2 class="JobCard_title__X">Software Developer Intern</h2>
      <address><span class="JobCard_company__N">Kompass India</span><span class="JobCard_location__n">Mumbai, India</span></address></header>
      <p class="JobCard_snippet__r">APIs and databases ... <a href="/view?id=6395">Show more</a></p>
      <time datetime="2026-09-30T10:56:36Z">18 days ago</time></article>"""
    out = niche.parse_talent(html)
    assert out[0]["role_title"] == "Software Developer Intern" and out[0]["company_name"] == "Kompass India"
    assert out[0]["apply_link"] == "https://in.talent.com/view?id=6395" and out[0]["posted"] == "2026-09-30"


def test_simplyhired_next_data_and_salary():
    data = {"props": {"pageProps": {"jobs": [{"jobKey": "K1", "title": "internship for laravel developer",
             "company": "DSV Info", "location": "Lucknow, Uttar Pradesh", "salaryInfo": "From ₹60,000 a year",
             "snippet": "Learn", "requirements": ["PHP"], "uncategorized": ["Laravel"]}]}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    out = niche.parse_simplyhired(html)
    assert out[0]["apply_link"] == "https://www.simplyhired.co.in/job/K1"
    assert out[0]["stipend_numeric"] == 5000 and out[0]["stipend_currency"] == "INR"
    assert niche.inr_monthly("₹15,000 a month") == 15000 and niche.inr_monthly("Competitive") == 0


def test_careerjet_cards():
    html = """<article class="job clicky"><header><h2><a href="/jobad/in53dc" title="Intern - Turbine Software">Intern - Turbine Software</a></h2></header>
      <p class="company"><a href="/company/Siemens">Siemens Energy</a></p><ul class="location"><li>India</li></ul>
      <div class="desc">About the role</div><footer><ul><li><span class="badge">28 days ago</span></li></ul></footer></article>"""
    out = niche.parse_careerjet(html)
    assert out[0]["company_name"] == "Siemens Energy" and out[0]["apply_link"] == "https://www.careerjet.co.in/jobad/in53dc"


def test_niche_boards_return_nothing_instead_of_fake_cards():
    assert niche.scrape_niche_boards() == []


def test_microsoft_keeps_interns():
    data = {"data": {"count": 2, "positions": [
        {"id": 1970, "name": "Data Science INTERN", "locations": ["India, Multiple Locations"], "postedTs": 1791442234,
         "department": "Data Science", "positionUrl": "/careers/job/1970"},
        {"id": 1971, "name": "Post Doc Researcher", "locations": ["India, Karnataka, Bangalore"]}]}}
    out = bigtech.parse_microsoft(data)
    assert len(out) == 1 and out[0]["apply_link"] == "https://apply.careers.microsoft.com/careers/job/1970"
    assert out[0]["company_name"] == "Microsoft" and out[0]["stipend"] == ""


def test_google_cards():
    html = """<ul><li class="lLd3Je"><div><h3 class="QJPWVe">Software Engineering Intern, PhD, Summer 2027</h3>
      <span class="pwO9Dc"><i>place</i><span class="r0wTof">Mountain View, CA, USA</span><span class="r0wTof">; Atlanta, GA, USA</span><span>; +29 more</span></span>
      <h4>Minimum qualifications</h4><ul><li>Pursuing a PhD</li></ul>
      <a href="jobs/results/91436104816698054-software-engineering-intern?q=intern">Learn more</a></div></li></ul>"""
    out = bigtech.parse_google(html)
    assert out[0]["location"] == "Mountain View, CA, USA; Atlanta, GA, USA"
    assert out[0]["apply_link"].endswith("/jobs/results/91436104816698054-software-engineering-intern")
    assert out[0]["description"].startswith("Minimum qualifications: Pursuing a PhD")


def test_apple_rows():
    html = """<div class="job-list-item"><h3><a href="/en-us/details/200688946-3715/software-engineering-intern?team=STDNT">Software Engineering Intern</a></h3>
      <span class="job-posted-date">Oct 16, 2026</span><span id="search-store-name-container-2">Shanghai</span></div>"""
    out = bigtech.parse_apple(html)
    assert out[0]["location"] == "Shanghai" and out[0]["job_id"] == "200688946-3715"


def test_meta_links():
    rows = [("/profile/job_details/1950497786328676",
             "Signal Integrity Intern\nMenlo Park, CA\nInternship - Engineering, Tech & Design\nHardware")]
    out = bigtech.parse_meta(rows)
    assert out[0]["location"] == "Menlo Park, CA"
    assert out[0]["apply_link"] == "https://www.metacareers.com/jobs/1950497786328676/"


def test_amazon_and_workday():
    a = bigtech.parse_amazon({"jobs": [
        {"title": "2027 Software Dev Engineer Intern - United Kingdom", "company_name": "Amazon UK Services Ltd.",
         "normalized_location": "London, England, GBR", "job_path": "/en/jobs/10581332/x", "id_icims": "10581332",
         "description_short": "Solve problems", "basic_qualifications": "- CS degree", "job_category": "Software Development"},
        {"title": "Software Development Engineer II", "job_path": "/en/jobs/1/y"}]})
    assert len(a) == 1 and a[0]["apply_link"] == "https://www.amazon.jobs/en/jobs/10581332/x"
    w = bigtech.parse_workday({"jobPostings": [
        {"title": "DFT Intern - 2027", "externalPath": "/job/China-Shanghai/DFT-Intern_JR2027176",
         "locationsText": "China, Shanghai", "postedOn": "Posted 5 Days Ago", "bulletFields": ["JR2027176"]},
        {"title": "Director, International Tax Planning", "externalPath": "/job/x"}]}, "nvidia")
    assert len(w) == 1
    assert w[0]["apply_link"] == "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/China-Shanghai/DFT-Intern_JR2027176"


def test_registry_points_at_new_scrapers():
    from scraper import ALL_SCRAPERS
    from sites import registry
    assert registry.scrapers_for(["google", "careerjet_in", "amazon"])[0] == ["google", "careerjet", "amazon"]
    for key in ["talent", "simplyhired", "careerjet", "microsoft", "google", "apple", "meta", "amazon",
                "nvidia", "intel", "adobe", "salesforce"]:
        assert key in ALL_SCRAPERS

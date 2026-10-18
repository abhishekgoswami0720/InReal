"""
Every site InReal lists, in one place. The dashboard draws its site checkboxes from this list
(GET /api/sites), and scraper.py uses it to turn the ticked sites into the scrapers to run.

    key     : what the dashboard sends (one per site)
    name    : shown to the student
    region  : india | usa | europe | remote | worldwide (matches the region checkboxes)
    how     : how the data is fetched -- api (a public JSON/data endpoint), rss (a feed),
              page (the HTML page), browser (a real Chrome window), search (a web search)
    status  : tested  -- scraper rebuilt and checked against the live site
              basic   -- an older scraper that runs but was not rebuilt yet
              planned -- listed, no scraper yet (the checkbox is disabled)
    runs    : the scraper in scraper.ALL_SCRAPERS that fetches it (None while planned).
              Several sites can share one scraper (e.g. the four AI job boards).
"""

REGIONS = [
    {"key": "india", "label": "India"},
    {"key": "usa", "label": "USA"},
    {"key": "europe", "label": "Europe"},
    {"key": "remote", "label": "Remote"},
    {"key": "worldwide", "label": "Global"},
]


def _s(key, name, region, how, status, runs=None):
    return {"key": key, "name": name, "region": region, "how": how, "status": status, "runs": runs}


SITES = [
    # India
    _s("internshala", "Internshala", "india", "page", "tested", "internshala"),
    _s("unstop", "Unstop", "india", "api", "tested", "unstop"),
    _s("naukri", "Naukri", "india", "browser", "tested", "naukri"),
    _s("shine", "Shine", "india", "page", "tested", "shine"),
    _s("foundit", "Foundit", "india", "browser", "tested", "foundit"),
    _s("apna", "Apna", "india", "page", "tested", "apna"),
    _s("government", "AICTE Internship Portal (Govt)", "india", "api", "tested", "government"),
    _s("cutshort", "Cutshort", "india", "page", "basic", "cutshort"),
    _s("talent_in", "Talent.com India", "india", "page", "basic", "aggregators"),
    _s("careerjet_in", "Careerjet India", "india", "page", "basic", "aggregators"),
    _s("simplyhired_in", "SimplyHired India", "india", "page", "basic", "aggregators"),
    _s("hirist", "Hirist", "india", "page", "planned"),
    _s("iimjobs", "iimjobs", "india", "page", "planned"),
    _s("freshersworld", "Freshersworld", "india", "page", "planned"),
    _s("timesjobs", "TimesJobs", "india", "page", "planned"),
    _s("ncs", "National Career Service (Govt)", "india", "page", "planned"),
    _s("indeed_in", "Indeed India", "india", "browser", "planned"),

    # USA
    _s("usajobs", "USAJOBS (US Govt)", "usa", "api", "planned"),
    _s("simplify", "Simplify internship list (GitHub)", "usa", "api", "planned"),
    _s("greenhouse", "Greenhouse company boards", "usa", "api", "planned"),
    _s("lever", "Lever company boards", "usa", "api", "planned"),
    _s("ashby", "Ashby company boards", "usa", "api", "planned"),
    _s("themuse", "The Muse", "usa", "api", "planned"),
    _s("adzuna_us", "Adzuna USA", "usa", "api", "planned"),
    _s("builtin", "Built In", "usa", "page", "planned"),
    _s("dice", "Dice", "usa", "page", "planned"),
    _s("wellfound", "Wellfound (AngelList)", "usa", "browser", "planned"),

    # Europe
    _s("euraxess", "EURAXESS (EU research)", "europe", "page", "planned"),
    _s("arbeitnow", "Arbeitnow", "europe", "api", "planned"),
    _s("adzuna_eu", "Adzuna UK & Europe", "europe", "api", "planned"),
    _s("reed", "Reed (UK)", "europe", "api", "planned"),
    _s("eu_traineeships", "EU Institutions traineeships", "europe", "page", "planned"),
    _s("cern", "CERN student programmes", "europe", "page", "planned"),
    _s("wttj", "Welcome to the Jungle", "europe", "page", "planned"),
    _s("graduateland", "Graduateland", "europe", "page", "planned"),

    # Remote
    _s("remotive", "Remotive", "remote", "rss", "basic", "remotive"),
    _s("weworkremotely", "We Work Remotely", "remote", "rss", "basic", "weworkremotely"),
    _s("remoteok", "Remote OK", "remote", "api", "planned"),
    _s("himalayas", "Himalayas", "remote", "api", "planned"),
    _s("workingnomads", "Working Nomads", "remote", "api", "planned"),
    _s("jobspresso", "Jobspresso", "remote", "page", "planned"),
    _s("remoteco", "Remote.co", "remote", "page", "planned"),

    # Global
    _s("linkedin", "LinkedIn", "worldwide", "page", "tested", "linkedin"),
    _s("microsoft", "Microsoft Careers", "worldwide", "page", "basic", "bigtech"),
    _s("google", "Google Careers", "worldwide", "page", "basic", "bigtech"),
    _s("meta", "Meta Careers", "worldwide", "page", "basic", "bigtech"),
    _s("apple", "Apple Jobs", "worldwide", "page", "basic", "bigtech"),
    _s("nvidia", "NVIDIA Careers", "worldwide", "page", "basic", "bigtech"),
    _s("aijobs", "AIJobs.net", "worldwide", "page", "basic", "niche"),
    _s("mlops", "MLOps Community jobs", "worldwide", "page", "basic", "niche"),
    _s("deeplearningai", "DeepLearning.AI jobs", "worldwide", "page", "basic", "niche"),
    _s("kdnuggets", "KDnuggets jobs", "worldwide", "page", "basic", "niche"),
    _s("universities", "University & research lab pages", "worldwide", "search", "basic", "universities"),
    _s("websearch", "Web search (DuckDuckGo)", "worldwide", "search", "basic", "search"),
    _s("gsoc", "Google Summer of Code", "worldwide", "api", "planned"),
    _s("outreachy", "Outreachy", "worldwide", "page", "planned"),
    _s("mlh", "MLH Fellowship", "worldwide", "page", "planned"),
    _s("mitacs", "Mitacs Globalink", "worldwide", "page", "planned"),
    _s("un_careers", "UN Careers internships", "worldwide", "page", "planned"),
    _s("maxplanck", "Max Planck institutes", "worldwide", "page", "planned"),
]

BY_KEY = {s["key"]: s for s in SITES}

# What the live scan popup calls each scraper (one scraper can cover several sites)
SCRAPER_LABELS = {
    "internshala": "Internshala", "unstop": "Unstop", "naukri": "Naukri", "shine": "Shine",
    "foundit": "Foundit", "apna": "Apna", "government": "AICTE (Govt)", "cutshort": "Cutshort",
    "aggregators": "Talent.com, Careerjet, SimplyHired", "remotive": "Remotive",
    "weworkremotely": "We Work Remotely", "international": "We Work Remotely (browser)",
    "linkedin": "LinkedIn", "bigtech": "Big Tech careers", "niche": "AI job boards",
    "universities": "University pages", "search": "Web search",
}

TESTED = [s["key"] for s in SITES if s["status"] == "tested"]


def public_list():
    """For the dashboard: regions, sites (without the internal 'runs') and scraper labels."""
    return {
        "regions": REGIONS,
        "sites": [{k: v for k, v in s.items() if k != "runs"} for s in SITES],
        "scraper_labels": SCRAPER_LABELS,
    }


def scrapers_for(keys):
    """Ticked site keys -> scraper names to run, in order, each once. Planned or unknown keys are
    returned separately so the caller can log them. A scraper name itself (old saved settings,
    e.g. 'niche') is passed through."""
    run, skipped = [], []
    for key in keys:
        site = BY_KEY.get(key)
        name = site["runs"] if site else (key if key in SCRAPER_LABELS else None)
        if not name:
            skipped.append(key)
        elif name not in run:
            run.append(name)
    return run, skipped

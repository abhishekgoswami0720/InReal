"""Sites are scraped only when someone asks, and only the sites they picked (19 Oct 2026)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_mod  # noqa: E402


def test_a_search_without_sites_is_refused(monkeypatch):
    ran = []
    monkeypatch.setattr(app_mod, "run_scrapers", lambda **kw: ran.append(kw))
    app_mod.scraper_t = None
    c = app_mod.app.test_client()
    for body in (None, {}, {"sources": []}, {"sources": ["", " "]}, {"field": "software"}):
        r = c.post("/api/scrape", json=body) if body is not None else c.post("/api/scrape")
        assert r.status_code == 400, body
    assert ran == [] and app_mod.scraper_t is None       # nothing started, least of all "every site"


def test_a_search_runs_only_the_picked_sites(monkeypatch):
    ran = []
    monkeypatch.setattr(app_mod, "run_scrapers", lambda **kw: ran.append(kw["config"]["sources"]))
    app_mod.scraper_t = None
    r = app_mod.app.test_client().post("/api/scrape", json={"sources": ["talent_in"], "field": "software"})
    assert r.get_json()["status"] == "started"
    app_mod.scraper_t.join(2)
    assert ran == [["talent_in"]]


def test_the_app_never_starts_the_automatic_update():
    main = (Path(app_mod.__file__).read_text(encoding="utf-8").split('if __name__ == "__main__":', 1)[1])
    assert "autopilot.start(" not in main



def test_only_a_new_search_asks_for_its_first_10(monkeypatch):
    """25 Oct: the list stayed empty behind a button after a search. A new search now sends its
    first 10 to the scam check by itself; "Search more" (which carries the search's tag) doesn't."""
    seen = []
    monkeypatch.setattr(app_mod, "run_scrapers", lambda **kw: seen.append(dict(kw["config"])))
    c = app_mod.app.test_client()
    app_mod.scraper_t = None
    tag = c.post("/api/scrape", json={"sources": ["unstop"], "field": "software"}).get_json()["run_tag"]
    app_mod.scraper_t.join(2)
    app_mod.scraper_t = None
    c.post("/api/scrape", json={"sources": ["unstop"], "field": "software", "run_tag": tag})
    app_mod.scraper_t.join(2)
    assert seen[0].get("first_show") == 10 and not seen[1].get("first_show")


def test_first_10_go_out_as_sites_finish_and_only_from_this_search(tmp_path, monkeypatch):
    import output_handler as oh
    import scraper
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "internships_log.json")
    monkeypatch.setattr("sites.details.fill_details", lambda rows, n: None)
    monkeypatch.setattr("moderation.notify.notify_n8n", lambda source="": None)
    monkeypatch.setattr(scraper, "evaluate", lambda src, raw: [(dict(r), True, "") for r in raw])
    row = lambda i, site: {"id": f"{site}{i}", "company_name": "Acme", "role_title": "Software Intern",
                           "apply_link": f"https://example.com/{site}/{i}", "source_platform": site, "description": "x" * 400}
    oh.sync_listings([row(i, "Old") for i in range(5)], [], hold=True, run_tag="earlier")   # another search's posts
    scraper.RUN_TAG["value"] = "now"
    scraper._release["left"] = 10
    try:
        scraper.process_and_save("cutshort", [row(i, "Cutshort") for i in range(4)])     # fast site: all 4 go now
        sent = [r for r in oh.read_all_rows() if r["moderation_status"] != "held"]
        assert len(sent) == 4 and {r["source_platform"] for r in sent} == {"Cutshort"}
        scraper.process_and_save("unstop", [row(i, "Unstop") for i in range(9)])          # tops the batch up to 10
        sent = [r for r in oh.read_all_rows() if r["moderation_status"] != "held"]
        assert len(sent) == 10 and all(r["last_run"] == "now" for r in sent)
        scraper.process_and_save("shine", [row(i, "Shine") for i in range(5)])            # nothing more by itself
        assert sum(r["moderation_status"] != "held" for r in oh.read_all_rows()) == 10
    finally:
        scraper._release["left"] = 0
        scraper.RUN_TAG["value"] = ""


def test_a_site_stops_reading_once_it_has_enough():
    from sites import budget
    recs = [{"id": f"r{i}"} for i in range(30)]
    budget.start(10, seen_ids=["r0", "r1"])
    try:
        assert budget.take(recs)[0]["id"] == "r2" and len(budget.take(recs)) == 10   # saved ones skipped
        assert budget.enough(recs[:12]) and not budget.enough(recs[:11])
    finally:
        budget.stop()
    assert budget.take(recs) == recs and not budget.enough(recs)                      # no target: no limit


def test_sites_run_a_few_at_a_time_fast_ones_first_and_retry_a_dropped_connection(monkeypatch):
    """26 Oct: all 25 sites at once made the laptop's connections drop and 9 sites failed."""
    import threading
    import time
    import requests
    import scraper
    monkeypatch.setattr(scraper, "process_and_save", lambda name, listings, per_site=None: len(listings))
    monkeypatch.setattr(scraper, "update_run_history", lambda *a: None)
    live, peak, started, tries = [0], [0], [], {}
    lock = threading.Lock()

    def site(name, flaky=False):
        def run(**kw):
            with lock:
                started.append(name)
                live[0] += 1
                peak[0] = max(peak[0], live[0])
                tries[name] = tries.get(name, 0) + 1
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            if flaky and tries[name] == 1:
                raise requests.exceptions.SSLError("EOF occurred in violation of protocol")
            return [{"id": name}]
        return run

    names = ["internshala", "shine", "apna", "naukri", "government", "cutshort", "unstop", "nvidia", "intel",
             "adobe", "salesforce", "amazon", "remotive"]
    fake = {n: site(n, flaky=(n == "nvidia")) for n in names}
    monkeypatch.setattr(scraper, "ALL_SCRAPERS", fake)
    monkeypatch.setattr("sites.registry.scrapers_for", lambda keys: (list(keys), []))
    scraper.run_scrapers(dry_run=False, config={"sources": names, "field": "software", "limit": 0, "run_tag": "t"})
    assert peak[0] <= scraper.MAX_PARALLEL
    assert started[0] == "government" and started.index("naukri") > started.index("internshala")   # Chrome last
    assert tries["nvidia"] == 2 and not scraper.RUN_PROGRESS["failed"]                              # retried, saved

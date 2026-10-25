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


def _fake_search(n_per_site):
    """A stand-in for the scrapers: saves held posts from two sites under the search's tag."""
    import output_handler as oh

    def run(dry_run=False, config=None, **kw):
        rows = [{"id": f"{site}-{config['run_tag']}-{i}", "company_name": "Acme", "role_title": "Software Intern",
                 "apply_link": f"https://example.com/{site}/{i}", "source_platform": site, "description": "x" * 400}
                for site in ("Unstop", "Shine") for i in range(n_per_site)]
        oh.sync_listings(rows, [], hold=True, run_tag=config["run_tag"])
    return run


def test_a_new_search_shows_its_first_10_without_a_click(tmp_path, monkeypatch):
    """25 Oct: the list stayed empty behind a button after a search; now the first 10 go to the
    scam check when the search ends. "Search more" still waits for "Load 5 more"."""
    import output_handler as oh
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "internships_log.json")
    monkeypatch.setattr("sites.details.fill_details", lambda rows, n: None)
    sent = []
    monkeypatch.setattr("moderation.notify.notify_n8n", lambda source="": sent.append(source))
    monkeypatch.setattr(app_mod, "run_scrapers", _fake_search(8))
    c = app_mod.app.test_client()

    app_mod.scraper_t = None
    tag = c.post("/api/scrape", json={"sources": ["unstop", "shine"], "field": "software"}).get_json()["run_tag"]
    app_mod.scraper_t.join(5)
    rows = [r for r in oh.read_all_rows() if r.get("last_run") == tag]
    checking = [r for r in rows if r["moderation_status"] != "held"]   # released: waiting for n8n
    assert len(rows) == 16 and len(checking) == 10
    assert {r["source_platform"] for r in checking} == {"Unstop", "Shine"}   # mixed, not one site's ten
    assert sent == ["first results"]

    # "Search more" adds to the same search and sends nothing by itself
    app_mod.scraper_t = None
    monkeypatch.setattr(app_mod, "run_scrapers", _fake_search(12))
    c.post("/api/scrape", json={"sources": ["unstop", "shine"], "field": "software", "run_tag": tag})
    app_mod.scraper_t.join(5)
    rows = [r for r in oh.read_all_rows() if r.get("last_run") == tag]
    assert sum(r["moderation_status"] != "held" for r in rows) == 10 and sent == ["first results"]
    assert len(rows) == 24   # 8 more per site; the first 16 were found again, not added twice

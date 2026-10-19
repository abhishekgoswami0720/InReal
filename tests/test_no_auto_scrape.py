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

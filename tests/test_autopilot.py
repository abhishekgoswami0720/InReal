"""Automatic update (autopilot.py): one round with fake scrapers, Supabase and n8n."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import autopilot  # noqa: E402
import output_handler as oh  # noqa: E402

LONG = "Build web apps with our team, weekly reviews, stipend paid monthly. " * 6


def test_a_round_checks_only_new_posts_and_waits_for_verdicts(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "log.json")
    monkeypatch.setattr(autopilot, "settings", lambda: {"on": True, "every_h": 6, "fields": ["software"], "limit": 50})
    seen_configs = []

    def fake_scrape(dry_run, config):
        seen_configs.append(config)
        rows = [{"id": i, "role_title": "SDE Intern", "company_name": "Acme", "apply_link": f"https://x/{i}",
                 "source_platform": "Unstop", "description": LONG, "field": "software"} for i in ("old1", "new1", "new2")]
        oh.sync_listings(rows, [], hold=True, run_tag=config["run_tag"])

    import scraper
    monkeypatch.setattr(scraper, "run_scrapers", fake_scrape)
    import supabase_sync
    monkeypatch.setattr(supabase_sync, "known_verdicts", lambda ids: {"old1": "approved"} if "old1" in ids else {})
    published = []
    monkeypatch.setattr(supabase_sync, "publish_later", lambda rows: published.extend(r["id"] for r in rows))

    def fake_n8n(source=""):        # n8n: judge everything pending
        for p in oh.pending_moderation(limit=50, claim=True):
            oh.save_verdict(p["id"], "approved", 0.05, ["LLM: genuine"])
    import moderation.notify
    monkeypatch.setattr(moderation.notify, "notify_n8n", fake_n8n)

    result = autopilot.run_round(lambda: False)
    assert result == {"software": {"to_check": 2, "known": 1}}
    cfg = seen_configs[0]
    assert cfg["field"] == "software" and cfg["run_tag"].startswith("auto-") and "talent_in" in cfg["sources"]
    assert "hirist" not in cfg["sources"]                    # planned sites are not searched
    statuses = {r["id"]: r["moderation_status"] for r in oh.read_all_rows()}
    assert statuses == {"old1": "approved", "new1": "approved", "new2": "approved"}
    assert sorted(published) == ["new1", "new2"]              # old1 was not checked (or paid for) again
    assert autopilot.STATE["busy"] is False and autopilot.STATE["last_round"]


def test_no_round_while_a_manual_search_runs(monkeypatch):
    monkeypatch.setattr(autopilot, "settings", lambda: {"on": True, "every_h": 6, "fields": ["software"], "limit": 50})
    assert autopilot.run_round(lambda: True) == {}


def test_a_search_during_a_round_is_queued_and_the_round_yields(tmp_path, monkeypatch):
    import time
    import app as app_mod
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "log.json")
    ran = []
    monkeypatch.setattr(app_mod, "run_scrapers", lambda **kw: ran.append(kw["config"]["field"]))
    monkeypatch.setitem(autopilot.STATE, "busy", True)
    monkeypatch.setitem(autopilot.STATE, "yield", False)
    app_mod.scraper_t = None
    c = app_mod.app.test_client()
    d = c.post("/api/scrape", json={"field": "software", "sources": ["unstop"]}).get_json()
    assert d["status"] == "queued" and d["run_tag"]
    assert autopilot.STATE["yield"] is True                         # the round is asked to stop
    time.sleep(0.3)
    assert c.get("/api/scrape/status").get_json()["status"] == "queued" and ran == []
    assert c.post("/api/scrape", json={"field": "data", "sources": ["unstop"]}).get_json()["status"] == "running"
    autopilot.STATE["busy"] = False                                 # the round ends
    app_mod.scraper_t.join(5)
    assert ran == ["software"]
    assert c.post("/api/session/new").get_json()["status"] == "kept"   # a reload never wipes anything


def test_a_round_stops_before_the_next_field_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "log.json")
    monkeypatch.setattr(autopilot, "settings", lambda: {"on": True, "every_h": 6, "fields": ["software", "data"], "limit": 50})
    searched = []

    def fake_scrape(dry_run, config):
        searched.append(config["field"])
        autopilot.STATE["yield"] = True                             # someone pressed Search meanwhile
    monkeypatch.setattr("scraper.run_scrapers", fake_scrape)
    monkeypatch.setattr("supabase_sync.known_verdicts", lambda ids: {})
    autopilot.STATE["yield"] = False
    autopilot.run_round(lambda: False)
    assert searched == ["software"]
    assert autopilot.STATE["yield"] is False and autopilot.STATE["busy"] is False



def test_a_restart_does_not_start_a_new_round(tmp_path, monkeypatch):
    monkeypatch.setattr(autopilot, "LAST_ROUND_FILE", tmp_path / "last.txt")
    now = 1_000_000.0
    assert autopilot.first_delay(6, now) == 120                     # never ran: 2 minutes after start
    (tmp_path / "last.txt").write_text(str(now - 3600))             # last round an hour ago
    assert autopilot.first_delay(6, now) == 5 * 3600                # next one when it is due
    (tmp_path / "last.txt").write_text(str(now - 7 * 3600))
    assert autopilot.first_delay(6, now) == 120


def test_load_more_posts_go_before_the_automatic_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "log.json")
    row = lambda i, tag: {"id": f"{tag}{i}", "role_title": "Intern", "source_platform": "Unstop", "description": LONG}
    oh.sync_listings([row(i, "a") for i in range(8)], [], run_tag="auto-20261019-1724-software")
    oh.sync_listings([row(i, "m") for i in range(2)], [], run_tag="20261019-172342")
    first = [p["id"] for p in oh.pending_moderation(limit=5)]
    assert first[:2] == ["m0", "m1"] or set(first[:2]) == {"m0", "m1"}
    assert len(first) == 5                                          # the rest of the batch: automatic ones

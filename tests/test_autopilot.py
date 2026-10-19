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


def test_manual_search_and_page_reload_wait_for_a_round(monkeypatch):
    import app as app_mod
    monkeypatch.setitem(autopilot.STATE, "busy", True)
    c = app_mod.app.test_client()
    assert c.post("/api/scrape", json={"field": "software", "sources": ["unstop"]}).get_json()["status"] == "running"
    assert c.post("/api/session/new").get_json()["status"] == "busy"

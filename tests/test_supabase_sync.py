"""Laptop -> Supabase publishing (supabase_sync.py), against a fake Supabase REST endpoint."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import supabase_sync as ss  # noqa: E402


@pytest.fixture
def fake_supabase(monkeypatch):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append({"path": self.path, "apikey": self.headers.get("apikey"),
                        "auth": self.headers.get("Authorization"), "prefer": self.headers.get("Prefer"), "body": body})
            self.send_response(201)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(ss, "settings", lambda: (f"http://127.0.0.1:{srv.server_address[1]}", "sb_secret_test"))
    yield got
    srv.shutdown()


def row(id_, status, **kw):
    return {"id": id_, "role_title": "SDE Intern", "company_name": "Acme", "source_platform": "Talent.com",
            "moderation_status": status, "stipend_numeric": "10000.0", "scam_risk": "0.08",
            "field": "software;ai_ml", "description": "Line one\nLine two", **kw}


def test_only_judged_rows_are_published_with_the_secret_key_header(fake_supabase):
    rows = [row("a", "approved"), row("b", "review"), row("c", "blocked"), row("d", "held"), row("e", "checking"), row("f", "")]
    assert ss.publish(rows) == 3
    call = fake_supabase[0]
    assert call["path"] == "/rest/v1/listings?on_conflict=id"
    assert call["apikey"] == "sb_secret_test" and call["auth"] is None          # never on Authorization
    assert "resolution=merge-duplicates" in call["prefer"]
    a = call["body"][0]
    assert a["status"] == "approved" and a["fields"] == ["software", "ai_ml"]
    assert a["stipend_numeric"] == 10000.0 and a["scam_risk"] == 0.08
    assert a["description"] == "Line one\nLine two"
    assert "verified_at" not in a and "first_seen_at" not in a                  # the database sets those


def test_off_or_unreachable_never_raises(monkeypatch):
    monkeypatch.setattr(ss, "settings", lambda: ("", ""))
    assert ss.publish([row("a", "approved")]) == 0
    monkeypatch.setattr(ss, "settings", lambda: ("http://127.0.0.1:9", "k"))      # nothing listens there
    assert ss.publish([row("a", "approved")]) == 0


def test_a_verdict_is_shared(monkeypatch, tmp_path):
    import output_handler as oh
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "log.json")
    shared = []
    monkeypatch.setattr(ss, "publish_later", lambda rows: shared.extend(rows))
    long_desc = "Build web apps with our team. " * 15
    oh.sync_listings([{"id": "v1", "role_title": "SDE Intern", "company_name": "Acme", "apply_link": "https://x/1",
                       "source_platform": "Unstop", "description": long_desc}], [])
    oh.save_verdict("v1", "approved", 0.05, ["LLM: genuine"])
    assert [(r["id"], r["moderation_status"]) for r in shared] == [("v1", "approved")]
    oh.save_verdict("v1", "blocked", 0.9, ["fee"])
    assert oh.unblock("v1") is True
    assert [r["moderation_status"] for r in shared] == ["approved", "blocked", "review"]


def test_the_backfill_loop_resends_judged_posts(monkeypatch):
    import app as app_mod
    import supabase_sync
    sent = []
    monkeypatch.setattr(supabase_sync, "enabled", lambda: True)
    monkeypatch.setattr(supabase_sync, "publish", lambda rows: sent.append(len(rows)) or len(rows))
    monkeypatch.setattr("output_handler.read_all_rows", lambda: [{"id": "a"}, {"id": "b"}])
    monkeypatch.setattr(app_mod, "PUBLISH_EVERY_S", 3600)
    t = app_mod.start_publish_loop()
    t.join(0.5)
    assert sent == [2]


def test_pages_move_from_127_0_0_1_to_localhost():
    import app as app_mod
    c = app_mod.app.test_client()
    r = c.get("/app", base_url="http://127.0.0.1:5000")
    assert r.status_code == 302 and r.headers["Location"] == "http://localhost:5000/app"
    assert c.get("/api/fields", base_url="http://127.0.0.1:5000").status_code == 200   # the API is not moved

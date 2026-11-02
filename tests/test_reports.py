"""'Report this post': 2+ different users move a VERIFIED post to "needs a look"; reports never block."""
import csv

import output_handler as oh
import supabase_sync


def _setup(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "internships_log.json")
    oh._write_rows(rows)


def _rows(tmp_path):
    with open(tmp_path / "internships.csv", newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def test_two_reporters_send_a_verified_post_to_review(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [
        {"id": "a", "role_title": "Intern", "moderation_status": "approved", "moderation_reasons": "LLM: genuine"},
        {"id": "b", "role_title": "Intern", "moderation_status": "approved"},
        {"id": "c", "role_title": "Intern", "moderation_status": "blocked"},
        {"id": "d", "role_title": "Intern", "moderation_status": "review"},
    ])
    counts = {"a": {"users": 2, "reasons": {"asks_money": 2}},
              "b": {"users": 1, "reasons": {"fake_company": 1}},           # one person is not enough
              "c": {"users": 5, "reasons": {"other": 5}},                  # already hidden: untouched
              "d": {"users": 3, "reasons": {"task_scam": 3}}}              # already needs a look
    assert oh.apply_reports(counts) == ["a"]
    rows = _rows(tmp_path)
    assert rows["a"]["moderation_status"] == "review"
    assert rows["a"]["moderation_reasons"].startswith("Reported by 2 users (asks for money ×2)")
    assert "LLM: genuine" in rows["a"]["moderation_reasons"]
    assert rows["b"]["moderation_status"] == "approved" and rows["c"]["moderation_status"] == "blocked"
    assert oh.apply_reports(counts) == []                               # nothing twice


def test_report_counts_counts_each_user_once(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self):
            return [{"listing_id": "a", "user_id": "u1", "reason": "asks_money"},
                    {"listing_id": "a", "user_id": "u2", "reason": "fake_company"},
                    {"listing_id": "b", "user_id": "u1", "reason": "other"}]
    monkeypatch.setattr(supabase_sync, "settings", lambda: ("https://x.supabase.co", "secret"))
    monkeypatch.setattr(supabase_sync.requests, "get", lambda *a, **k: R())
    got = supabase_sync.report_counts()
    assert got["a"] == {"users": 2, "reasons": {"asks_money": 1, "fake_company": 1}}
    assert got["b"]["users"] == 1


def test_report_counts_is_empty_without_supabase():
    assert supabase_sync.report_counts() == {}      # conftest turns Supabase off

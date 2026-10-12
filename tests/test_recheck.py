import output_handler as oh
from moderation import recheck


def _rows(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "i.csv")
    rows = [
        {"id": "a", "source_platform": "Unstop", "moderation_status": "approved", "scam_risk": "0.1",
         "moderation_reasons": "Embedding failed (403) | ok", "moderated_at": "x", "date_scraped": "1"},
        {"id": "b", "source_platform": "Unstop", "moderation_status": "approved", "scam_risk": "0.1",
         "moderation_reasons": "fine", "moderated_at": "x", "date_scraped": "2"},
        {"id": "c", "source_platform": "Internshala", "moderation_status": "blocked", "scam_risk": "0.9",
         "moderation_reasons": "fee", "moderated_at": "x", "date_scraped": "3"},
        {"id": "d", "source_platform": "Unstop", "moderation_status": "", "date_scraped": "4"},
    ]
    oh._write_rows(rows)


def status():
    return {r["id"]: r["moderation_status"] for r in oh._read_rows()}


def test_default_only_failed(tmp_path, monkeypatch):
    _rows(tmp_path, monkeypatch)
    assert recheck.requeue() == 1
    assert status() == {"a": "", "b": "approved", "c": "blocked", "d": ""}


def test_by_source_and_all(tmp_path, monkeypatch):
    _rows(tmp_path, monkeypatch)
    assert recheck.requeue(source="unstop") == 2
    assert status()["c"] == "blocked"
    assert recheck.requeue(all_rows=True) == 1
    assert all(v == "" for v in status().values())

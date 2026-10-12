"""sync_listings: saved rows are refreshed when the rules change, not frozen at their first save."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import output_handler as oh  # noqa: E402


def _row(id_, title, flags="", day="2026-10-12"):
    return {"id": id_, "company_name": "Acme", "role_title": title, "stipend": "5,000/month",
            "stipend_numeric": 5000, "source_platform": "Naukri", "date_scraped": day, "trust_flags": flags}


def _rows():
    return {r["id"]: r for r in oh._read_rows()}


def test_refresh_add_and_remove(tmp_path, monkeypatch):

    # 06:52 run: saved with the rules of that time
    r = oh.sync_listings([_row("a", "AI Intern"), _row("b", "Creative design & AI intern"), _row("c", "ML Intern")], [])
    assert r == {"added": 3, "updated": 0, "removed": 0}

    # 07:24 run: "a" now has a warning, "b" fails the new title rule, "c" was not in this run's results
    r = oh.sync_listings([_row("a", "AI Intern", "Employer's name sounds like a training institute"),
                          _row("d", "AI Engineer Intern")], ["b"])
    assert r == {"added": 1, "updated": 1, "removed": 1}
    rows = _rows()
    assert set(rows) == {"a", "c", "d"}                      # "c" untouched: not seen is not the same as dropped
    assert "training institute" in rows["a"]["trust_flags"]  # refreshed, not frozen
    assert rows["a"]["is_new"] == "True"                     # first-seen marker kept

    # same run again: nothing new, nothing changed
    r = oh.sync_listings([_row("a", "AI Intern", "Employer's name sounds like a training institute"),
                          _row("d", "AI Engineer Intern")], ["b"])
    assert r == {"added": 0, "updated": 0, "removed": 0}


def test_nothing_is_written_to_disk(tmp_path, monkeypatch):
    """No internships.csv / internships_log.json may ever be created again."""
    monkeypatch.chdir(tmp_path)
    before = set(ROOT.iterdir())
    oh.sync_listings([_row("z", "AI Intern")], [])
    oh.save_verdict("z", "approved", 0.1, ["ok"])
    oh.update_run_history(1, [])
    assert set(ROOT.iterdir()) == before and not list(tmp_path.iterdir())
    assert not (ROOT / "internships.csv").exists() and not (ROOT / "internships_log.json").exists()


def test_app_removes_leftover_store_files(tmp_path):
    import app
    for name in ["internships.csv", "internships_log.json", "keep.txt"]:
        (tmp_path / name).write_text("x")
    assert sorted(app.remove_old_store_files(tmp_path)) == ["internships.csv", "internships_log.json"]
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]


def test_clear_forgets_seen_ids():
    oh.sync_listings([_row("y", "AI Intern")], [])
    oh.clear_all()
    assert oh._read_rows() == []
    assert oh.sync_listings([_row("y", "AI Intern")], [])["added"] == 1   # comes back after a clear

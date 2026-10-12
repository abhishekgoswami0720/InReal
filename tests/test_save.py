"""sync_listings: saved rows are refreshed when the rules change, not frozen at their first save."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import output_handler as oh  # noqa: E402


def _row(id_, title, flags="", day="2026-10-12"):
    return {"id": id_, "company_name": "Acme", "role_title": title, "stipend": "5,000/month",
            "stipend_numeric": 5000, "source_platform": "Naukri", "date_scraped": day, "trust_flags": flags}


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def test_refresh_add_and_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(oh, "CSV_FILE", tmp_path / "internships.csv")
    monkeypatch.setattr(oh, "LOG_FILE", tmp_path / "internships_log.json")

    # 06:52 run: saved with the rules of that time
    r = oh.sync_listings([_row("a", "AI Intern"), _row("b", "Creative design & AI intern"), _row("c", "ML Intern")], [])
    assert r == {"added": 3, "updated": 0, "removed": 0}

    # 07:24 run: "a" now has a warning, "b" fails the new title rule, "c" was not in this run's results
    r = oh.sync_listings([_row("a", "AI Intern", "Employer's name sounds like a training institute"),
                          _row("d", "AI Engineer Intern")], ["b"])
    assert r == {"added": 1, "updated": 1, "removed": 1}
    rows = _rows(oh.CSV_FILE)
    assert set(rows) == {"a", "c", "d"}                      # "c" untouched: not seen is not the same as dropped
    assert "training institute" in rows["a"]["trust_flags"]  # refreshed, not frozen
    assert rows["a"]["is_new"] == "True"                     # first-seen marker kept

    # same run again: nothing new, nothing changed
    r = oh.sync_listings([_row("a", "AI Intern", "Employer's name sounds like a training institute"),
                          _row("d", "AI Engineer Intern")], ["b"])
    assert r == {"added": 0, "updated": 0, "removed": 0}

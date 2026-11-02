"""Hand labels and the accuracy report (moderation/label.py, moderation/accuracy.py)."""
from moderation import accuracy, label


def _row(i, status, src="Internshala"):
    return {"id": i, "role_title": f"Intern {i}", "company_name": "Acme", "source_platform": src,
            "moderation_status": status, "scam_risk": "0.10", "moderation_reasons": "why", "description": "text"}


def test_labels_are_saved_with_a_copy_of_the_post_and_the_latest_answer_wins(tmp_path):
    path = tmp_path / "labels.jsonl"
    label.save_label(_row("a", "approved"), "genuine", path)
    label.save_label(_row("a", "approved"), "scam", path)
    got = label.load_labels(path)
    assert got["a"]["label"] == "scam"
    assert got["a"]["post"]["role_title"] == "Intern a" and got["a"]["verdict"]["status"] == "approved"


def test_posts_to_label_alternate_between_verdicts_and_skip_labelled_ones():
    rows = [_row("v1", "approved"), _row("v2", "approved"), _row("v3", "approved"),
            _row("b1", "blocked"), _row("r1", "review"), _row("x", ""), _row("h", "held"), _row("e", "expired")]
    order = [r["id"] for r in label.to_label(rows, {"v2": {}})]
    assert order == ["v1", "r1", "b1", "v3"]                     # by turns; unjudged and closed posts left out
    assert [r["id"] for r in label.to_label(rows, {}, source="naukri")] == []
    assert len(label.to_label(rows, {}, limit=2)) == 2


def test_wilson_range_is_honest_about_small_samples():
    lo, hi = accuracy.wilson(9, 10)
    assert 0.55 < lo < 0.6 and 0.98 < hi <= 1.0
    assert accuracy.wilson(0, 0) == (0.0, 0.0)


def test_score_counts_the_two_worst_mistakes():
    pairs = [("scam", "blocked"), ("scam", "review"), ("scam", "approved"),
             ("genuine", "approved"), ("genuine", "approved"), ("genuine", "blocked"),
             ("unsure", "approved"), ("scam", "expired")]
    s = accuracy.score(pairs)
    assert s["scams"] == 3 and s["genuine"] == 3 and s["left_out"] == 2
    assert s["scams_caught"]["k"] == 1 and s["scams_flagged"]["k"] == 2 and s["scams_missed"]["k"] == 1
    assert s["genuine_blocked"]["k"] == 1 and s["genuine_verified"]["k"] == 2
    text = accuracy.report(s, [], "as saved")
    assert "Scams shown as Verified" in text and "Fewer than 100" in text


def test_collect_uses_the_saved_verdict_and_lists_mistakes(tmp_path):
    path = tmp_path / "labels.jsonl"
    label.save_label(_row("s1", "approved"), "scam", path)
    label.save_label(_row("g1", "blocked"), "genuine", path)
    label.save_label(_row("g2", "approved"), "genuine", path)
    pairs, mistakes = accuracy.collect(label.load_labels(path))
    assert sorted(pairs) == [("genuine", "approved"), ("genuine", "blocked"), ("scam", "approved")]
    assert {m["kind"] for m in mistakes} == {"Scam shown as Verified", "Genuine post hidden"}

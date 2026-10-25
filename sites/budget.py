"""How many NEW posts each site needs to find in one search (25 Oct 2026: under 15 s for the first results).

A search keeps only ~15 new posts per site (the rest used to wait for "Search more"), yet the
slow sites read everything first: Internshala opened 225 job pages to keep 11, which took 7 min.
scraper.run_scrapers sets a target here before the sites start; a site then stops paging and
stops opening job pages once it has that many posts it hasn't saved before. The ones it skipped
are still unseen, so "Search more" (which skips saved posts) reaches them next time.

No target (command line, tests) = no limit, the old behaviour.
"""
import threading

_lock = threading.Lock()
_state = {"target": None, "seen": frozenset()}


def start(target, seen_ids=()):
    with _lock:
        _state["target"] = int(target) if target else None
        _state["seen"] = frozenset(seen_ids or ())


def stop():
    start(None)


def target():
    return _state["target"]


def unseen(records):
    seen = _state["seen"]
    return [r for r in records if r.get("id") not in seen]


def enough(records, factor=1.0):
    """True once a site has collected enough new posts to stop reading more list pages."""
    t = _state["target"]
    return t is not None and len(unseen(records)) >= t * factor


def take(records):
    """The posts worth opening the job page for: new ones first, at most the target."""
    t = _state["target"]
    if t is None:
        return records
    return unseen(records)[:t]

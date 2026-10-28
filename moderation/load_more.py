"""'Load 5 more' = 5 more internships ON SCREEN, not 5 sent to the scam check (28 Oct 2026).

About half the posts sent to the check don't end up in the list (blocked, needs a look, closed), so
5 sent used to give 2 or 3 on screen, sometimes none. Now one click sends 5, waits for the verdicts,
and sends more for the ones that didn't pass, until 5 passed, nothing is left, or MAX_CHECKED posts
were checked (so one click can never spend more than that on Azure).

The dashboard reads the progress from /api/moderation/status ("load_more").
"""
import threading
import time

from loguru import logger

MAX_CHECKED = 15          # posts one click may send to the scam check at most
ROUND_TIMEOUT_S = 150     # a round whose verdicts haven't all come back by then is given up
WAITING = ("", "checking")

# which verdicts count as "on screen" for each scam-check filter of the dashboard
SHOWN = {
    "verified": {"approved"},
    "verified_review": {"approved", "review"},
    "hide_blocked": {"approved", "review", "expired", "retry"},
    "blocked": {"blocked"},
}

_lock = threading.Lock()
JOB = {"running": False, "run_tag": "", "want": 0, "shown": 0, "checked": 0, "done_reason": ""}


def status() -> dict:
    return dict(JOB)


def busy() -> bool:
    return JOB["running"]


def _statuses(ids) -> dict:
    from output_handler import read_all_rows
    wanted = set(ids)
    return {r["id"]: (r.get("moderation_status") or "") for r in read_all_rows() if r.get("id") in wanted}


def _wait_for(ids, sleep=time.sleep, clock=time.time) -> dict:
    """Until every id has a verdict (or the round times out). Returns id -> status."""
    start = clock()
    while True:
        st = _statuses(ids)
        if all(st.get(i, "") not in WAITING for i in ids) or clock() - start > ROUND_TIMEOUT_S:
            return st
        sleep(1)


def fill(first_ids: list, run_tag: str, want: int = 5, show: str = "verified", wake=None, sleep=time.sleep) -> dict:
    """Follows the first batch and tops it up until `want` of them are on screen. Runs in a thread."""
    from output_handler import release_held_ids
    if wake is None:
        from moderation.notify import start_scam_check as wake
    shown_as = SHOWN.get(show, SHOWN["verified"])
    ids, shown = list(first_ids), 0
    JOB.update(shown=0, checked=len(ids), done_reason="")
    try:
        batch = list(first_ids)
        while batch:
            st = _wait_for(batch, sleep=sleep)
            shown += sum(1 for i in batch if st.get(i) in shown_as)
            JOB.update(shown=shown)
            short = want - shown
            if short <= 0:
                JOB["done_reason"] = "enough"
                break
            room = MAX_CHECKED - len(ids)
            if room <= 0:
                JOB["done_reason"] = "limit"
                break
            # about half pass, so ask for twice the shortfall (never past the limit)
            batch = release_held_ids(min(room, short * 2), run_tag)
            if not batch:
                JOB["done_reason"] = "none_left"
                break
            ids += batch
            JOB.update(checked=len(ids))
            wake("load more (top-up)")
        logger.info(f"Load 5 more: {shown} on screen from {len(ids)} checked ({JOB['done_reason']})")
    except Exception as e:  # noqa: BLE001 - the button must never stay stuck on "Checking"
        logger.exception(f"Load 5 more stopped: {e}")
        JOB["done_reason"] = "error"
    finally:
        JOB["running"] = False
    return status()


def start(first_ids: list, run_tag: str, want: int = 5, show: str = "verified") -> bool:
    """Starts following a click in the background. False when one is already running."""
    with _lock:
        if JOB["running"]:
            return False
        JOB.update(running=True, run_tag=run_tag, want=want, shown=0, checked=len(first_ids), done_reason="")
    threading.Thread(target=fill, args=(first_ids, run_tag, want, show), daemon=True, name="load-more").start()
    return True

"""Runs the scam check on posts waiting in the list (the job the n8n workflow used to do).

One round: take up to 10 waiting posts (claimed, so two rounds never take the same ones), open
their apply links (all at once), rules, one embedding call, gate, AI judge (5 posts per call,
2 calls at once), fuse, save each verdict (which also publishes it to Supabase). Then the next
round, until nothing waits. "Needs a look" verdicts get a second look from the agent (agent.py)
in the background, so they never slow the first results down.

The worker is a thread inside the app, started by app.py; wake() is called after each site is
saved and on "Load 5 more" (moderation/notify.py). Without wake() it still looks every 30 min.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from moderation.pipeline import judge, vectors
from moderation.pipeline.config import settings
from moderation.pipeline.fuse import expired_verdict, fuse_batches, stage1_verdict
from moderation.pipeline.rules import analyse

ROUND_EVERY_S = 30 * 60
_round_lock = threading.Lock()
_wake = threading.Event()
_worker = {"thread": None}


def _resolve(url):
    from moderation.link_check import resolve
    try:
        return resolve(url)
    except Exception as e:  # noqa: BLE001 - a link we can't open is a signal, not a crash
        return {"link_state": "unreachable", "error": type(e).__name__}


def judge_posts(rows: list, cfg: dict | None = None, bank: dict | None = None, resolve=_resolve,
                embed=None, call=None) -> list:
    """The three stages on these posts; returns one verdict per post (nothing is saved here).
    embed/call/resolve can be swapped in tests."""
    cfg = cfg or settings()
    bank = bank or vectors.load_bank()
    embed = embed or (lambda texts: vectors.embed_call(texts, bank))
    call = call or judge.call
    with ThreadPoolExecutor(max_workers=min(10, len(rows)) or 1) as ex:
        links = list(ex.map(lambda r: resolve(r.get("apply_link", "")), rows))

    verdicts, posts = [], []
    for row, link in zip(rows, links):
        if link.get("link_state") in ("dead", "closed"):
            verdicts.append(expired_verdict(row, link))       # not a scam judgement: the post is gone
        else:
            posts.append(analyse(row, link))
    if not posts:
        return verdicts

    batches = vectors.pack(posts, bank)
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as ex:
        answers = list(ex.map(lambda b: embed(b["chunks"]), batches))
    items = vectors.unpack(posts, batches, answers, bank, cfg)

    verdicts += [stage1_verdict(i, cfg) for i in items if i["gate"]["decision"] == "block"]
    to_judge = [i for i in items if i["gate"]["decision"] != "block"]
    if to_judge:
        jb = judge.pack(to_judge, judge.provider(), cfg["judgeBatch"])
        with ThreadPoolExecutor(max_workers=max(1, min(cfg["judgeParallel"], len(jb)))) as ex:
            janswers = list(ex.map(lambda b: call(b["judgeRequest"]), jb))
        verdicts += [x["verdict"] for x in fuse_batches(jb, janswers, cfg)]
    return verdicts


def check_waiting(limit: int | None = None) -> dict:
    """One round on the waiting posts. Returns counts; saves every verdict."""
    from output_handler import pending_moderation, save_verdict
    cfg = settings()
    bank = vectors.load_bank()
    if bank is None:
        logger.warning("Scam check can't run: moderation/pattern_index.json is missing. "
                       "Run: python -m moderation.build_index")
        return {"checked": 0, "error": "no pattern index"}
    with _round_lock:
        rows = pending_moderation(limit or cfg["batchLimit"], claim=True)
        if not rows:
            return {"checked": 0}
        t0 = time.time()
        try:
            verdicts = judge_posts(rows, cfg, bank)
        except Exception as e:  # noqa: BLE001 - put the claimed posts back, never leave them "checking"
            logger.exception(f"Scam check round failed: {e}")
            for r in rows:
                save_verdict(r["id"], "retry", 0, [])
            return {"checked": 0, "error": str(e)}
        counts = {}
        for v in verdicts:
            try:
                save_verdict(v["id"], v["status"], v["scam_risk"], v["reasons"])
            except (TypeError, ValueError) as e:
                logger.warning(f"Verdict for {v['id']} not saved: {e}")
                continue
            counts[v["status"]] = counts.get(v["status"], 0) + 1
        took = time.time() - t0
    names = {"approved": "verified", "review": "need a look", "blocked": "likely scam", "expired": "closed", "retry": "to retry"}
    logger.info(f"Scam check: {len(verdicts)} checked in {took:.1f}s ("
                + ", ".join(f"{n} {names.get(k, k)}" for k, n in counts.items()) + ")")
    if cfg["agent"]:
        review = [v["id"] for v in verdicts if v["status"] == "review"]
        if review:
            try:
                import langgraph  # noqa: F401
            except ImportError:
                logger.warning("Second look skipped: run  pip install -r requirements.txt  (needs langgraph)")
            else:
                from moderation.pipeline import agent
                agent.look_later(review)
    return {"checked": len(verdicts), **counts, "seconds": round(took, 1)}


def _loop():
    while True:
        _wake.wait(timeout=ROUND_EVERY_S)
        _wake.clear()
        try:
            while check_waiting().get("checked"):
                pass
        except Exception as e:  # noqa: BLE001 - the worker must never die
            logger.exception(f"Scam check worker: {e}")
            time.sleep(5)


def start_worker():
    """Started once by app.py. Tests and command-line tools don't start it."""
    t = _worker["thread"]
    if t and t.is_alive():
        return t
    t = threading.Thread(target=_loop, daemon=True, name="scam-check")
    t.start()
    _worker["thread"] = t
    return t


def running() -> bool:
    t = _worker["thread"]
    return bool(t and t.is_alive())


def wake(source: str = "") -> bool:
    """Something new is waiting: start a round now. False when the worker isn't running."""
    if not running():
        return False
    _wake.set()
    return True

"""Starts the scam check when posts are waiting. Called after EACH site is saved and on
"Load 5 more", so site 1 is checked while site 2 is still being searched.

SCAM_CHECK=python (default, 26 Oct 2026): the check runs inside the app (moderation/pipeline).
SCAM_CHECK=n8n: the old way, a POST to INREAL_N8N_WEBHOOK (n8n/inreal_moderation.json).
The name notify_n8n stays so every caller keeps working.
"""
import os

from loguru import logger

from moderation.env import load_env


def mode() -> str:
    load_env()
    return "n8n" if os.environ.get("SCAM_CHECK", "python").strip().lower() == "n8n" else "python"


def notify_n8n(source: str = "") -> None:
    from output_handler import moderation_counts
    pending = moderation_counts()["pending"]
    if not pending:
        return
    if mode() == "python":
        from moderation.pipeline import wake
        if wake(source):
            logger.info(f"Scam check started{f' for {source}' if source else ''} ({pending} listings waiting)")
        return
    _post_to_n8n(source, pending)


def _post_to_n8n(source: str, pending: int) -> None:
    url = os.environ.get("INREAL_N8N_WEBHOOK", "").strip()
    if not url:
        return
    try:
        import requests
        r = requests.post(url, json={"event": "site_saved", "source": source, "pending": pending}, timeout=5)
        if r.status_code == 404:
            # n8n only registers /webhook/... while the workflow is published (active)
            logger.warning(f"n8n answered 404 for {url}: publish the 'InReal – scam moderation' workflow "
                           f"in n8n, or run it with 'Execute workflow'. {pending} listings are waiting.")
        elif r.status_code >= 400:
            logger.warning(f"n8n webhook returned HTTP {r.status_code}: {r.text[:200]}")
        else:
            logger.info(f"Scam check started in n8n{f' for {source}' if source else ''} ({pending} listings waiting)")
    except Exception as e:
        logger.warning(f"Could not reach n8n at {url} ({type(e).__name__}). Is n8n running? "
                       f"The workflow's 30-minute schedule will pick the listings up once it is.")

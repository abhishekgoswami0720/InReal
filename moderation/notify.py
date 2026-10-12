"""Tells n8n there are listings to check. Called by the scraper after EACH site is saved,
so n8n checks site 1 while site 2 is still being scraped (instead of waiting for the whole run)."""
import os

from loguru import logger

from moderation.env import load_env


def notify_n8n(source: str = "") -> None:
    load_env()
    url = os.environ.get("INREAL_N8N_WEBHOOK", "").strip()
    if not url:
        return
    from output_handler import moderation_counts
    try:
        import requests
        pending = moderation_counts()["pending"]
        if not pending:
            return
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

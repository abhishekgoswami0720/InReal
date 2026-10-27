"""Starts the scam check when posts are waiting. Called after EACH site is saved and on
"Load 5 more", so site 1 is checked while site 2 is still being searched.

The check runs inside the app (moderation/pipeline). Until 27 Oct 2026 it could also run in an
n8n workflow; that was removed (the old code is in the git history).
"""
from loguru import logger


def start_scam_check(source: str = "") -> None:
    from output_handler import moderation_counts
    pending = moderation_counts()["pending"]
    if not pending:
        return
    from moderation.pipeline import wake
    if wake(source):
        logger.info(f"Scam check started{f' for {source}' if source else ''} ({pending} listings waiting)")

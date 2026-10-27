"""Knobs of the scam check. Override any of them in .env."""
import os

from moderation.env import load_env


def settings() -> dict:
    load_env()
    env = os.environ.get

    def num(name, default):
        try:
            return float(env(name, "") or default)
        except ValueError:
            return float(default)

    return {
        "blockAt": num("MOD_BLOCK_AT", 0.7),          # risk for "likely scam"
        "reviewAt": num("MOD_REVIEW_AT", 0.4),        # risk for "needs a look"
        "hitFloor": env("MOD_HIT_FLOOR", ""),         # empty = the thresholds build_index measured
        "strongFloor": env("MOD_STRONG_FLOOR", ""),
        "margin": env("MOD_MARGIN", ""),
        "batchLimit": int(num("MOD_BATCH_LIMIT", 10)),   # posts taken per round
        "judgeBatch": int(num("MOD_JUDGE_BATCH", 5)),    # posts per AI call
        "judgeParallel": int(num("MOD_JUDGE_PARALLEL", 2)),  # AI calls at once (Azure: 50k tokens/min)
        "agent": env("MOD_AGENT", "on").strip().lower() not in ("off", "0", "false", "no"),
    }

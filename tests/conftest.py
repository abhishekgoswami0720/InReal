"""Shared test setup."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def no_real_supabase(monkeypatch):
    """Tests save fake verdicts; with the laptop's .env they would otherwise be published to the
    real shared list. Every test talks to a fake (or nothing) instead."""
    import supabase_sync
    monkeypatch.setattr(supabase_sync, "settings", lambda: ("", ""))

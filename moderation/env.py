"""Reads KEY=value lines from the project's .env file (never committed) into os.environ."""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


LOADED_FROM_FILE = set()


def load_env(path: Path = ENV_FILE):
    """
    Values in .env WIN over variables already set in Windows / the terminal. (12 Oct: a system-wide
    AZURE_OPENAI_* left over from another project silently replaced the .env values -> 401.)
    AZURE_OPENAI_API_KEY (the name LangChain projects use) is accepted for AZURE_OPENAI_KEY.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
        LOADED_FROM_FILE.add(key.strip())
    if not os.environ.get("AZURE_OPENAI_KEY") and os.environ.get("AZURE_OPENAI_API_KEY"):
        os.environ["AZURE_OPENAI_KEY"] = os.environ["AZURE_OPENAI_API_KEY"]

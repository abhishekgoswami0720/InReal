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
    apply_aliases()


# The names used in test.py / the Azure quickstart -> the names this project reads
ALIASES = {
    "AZURE_OPENAI_EMBEDDING_ENDPOINT": "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_EMBEDDING_KEY": "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_API_KEY": "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_GPT4O_KEY": "AZURE_OPENAI_JUDGE_KEY",
}


def apply_aliases():
    env = os.environ
    for src, dst in ALIASES.items():
        if env.get(src, "").strip() and not env.get(dst, "").strip():
            env[dst] = env[src].strip()
    # An embedding endpoint in .env means "embed on Azure", unless EMBED_PROVIDER says otherwise
    if env.get("AZURE_OPENAI_EMBEDDING_ENDPOINT", "").strip() and not env.get("EMBED_PROVIDER", "").strip():
        env["EMBED_PROVIDER"] = "azure"
    if env.get("AZURE_OPENAI_ENDPOINT", "").strip() and not env.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "").strip():
        env["AZURE_OPENAI_EMBED_DEPLOYMENT"] = "text-embedding-3-small"
    # gpt-4o endpoint (resource URL only) -> full chat-completions URL of the gpt-4o deployment
    base = env.get("AZURE_OPENAI_GPT4O_ENDPOINT", "").strip().rstrip("/")
    if base and not env.get("AZURE_OPENAI_JUDGE_URL", "").strip():
        if "/chat/completions" not in base:
            deployment = env.get("AZURE_OPENAI_GPT4O_DEPLOYMENT", "gpt-4o").strip()
            base = f"{base.split('/openai/')[0]}/openai/deployments/{deployment}/chat/completions?api-version=2025-01-01-preview"
        env["AZURE_OPENAI_JUDGE_URL"] = base

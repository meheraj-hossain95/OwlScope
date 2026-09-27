import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    """Read env var; fall back to default if missing OR empty string."""
    val = os.getenv(key, "").strip()
    return val if val else default


# Strip trailing slash so URL construction never produces double-slashes
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen2.5-coder:7b")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()  # empty string is valid

FLASK_SECRET_KEY = _env("FLASK_SECRET_KEY", "owlscope-dev-secret-change-me")

CACHE_DIR = _env("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))

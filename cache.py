"""File-based report cache for OwlScope.

Reports are stored as JSON files in CACHE_DIR, keyed by a SHA256 hash of
the normalised issue URL.  No database required.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from config import CACHE_DIR


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def url_to_cache_key(url: str) -> str:
    """Return a stable SHA256 hex digest for the given URL.

    The URL is normalised (stripped, lowercased, trailing slash removed)
    before hashing so equivalent URLs map to the same key.
    """
    normalised = url.strip().lower().rstrip("/")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def get_cached_report(url: str) -> dict | None:
    """Return the cached report dict for *url*, or None on a cache miss."""
    key = url_to_cache_key(url)
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def save_report(url: str, report_dict: dict) -> str:
    """Persist *report_dict* to disk and return the cache key.

    Adds a ``cached_at`` ISO-8601 timestamp if not already present.
    """
    _ensure_cache_dir()
    key = url_to_cache_key(url)
    if "cached_at" not in report_dict:
        report_dict["cached_at"] = datetime.now(timezone.utc).isoformat()
    with open(_cache_path(key), "w", encoding="utf-8") as fh:
        json.dump(report_dict, fh, ensure_ascii=False, indent=2)
    return key


def get_report_by_key(key: str) -> dict | None:
    """Load a cached report directly by its cache key (SHA256 hex string)."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def list_cached_reports() -> list[dict]:
    """Return metadata for all cached reports, sorted newest-first.

    Each entry contains ``key``, ``cached_at``, ``url``, and ``title``
    (if available in the stored report).
    """
    _ensure_cache_dir()
    results = []
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        key = fname[:-5]
        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            results.append({
                "key": key,
                "cached_at": data.get("cached_at", ""),
                "url": data.get("url", ""),
                "title": data.get("issue", {}).get("title", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue
    results.sort(key=lambda x: x["cached_at"], reverse=True)
    return results

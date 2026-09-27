"""Tests for cache.py — read, write, key derivation."""

import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch CACHE_DIR before importing cache so it uses a temp directory
import config


@pytest.fixture(autouse=True)
def temp_cache_dir(tmp_path, monkeypatch):
    """Redirect all cache I/O to a temporary directory for each test."""
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    # Re-patch the module-level CACHE_DIR in cache.py
    import cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))
    return tmp_path


import cache as cache_mod
from cache import url_to_cache_key, get_cached_report, save_report, get_report_by_key, list_cached_reports


# ---------------------------------------------------------------------------
# url_to_cache_key
# ---------------------------------------------------------------------------

class TestUrlToCacheKey:
    def test_same_url_same_key(self):
        assert url_to_cache_key("https://github.com/a/b/issues/1") == \
               url_to_cache_key("https://github.com/a/b/issues/1")

    def test_trailing_slash_normalised(self):
        a = url_to_cache_key("https://github.com/a/b/issues/1")
        b = url_to_cache_key("https://github.com/a/b/issues/1/")
        assert a == b

    def test_case_normalised(self):
        a = url_to_cache_key("https://github.com/Owner/Repo/issues/1")
        b = url_to_cache_key("https://github.com/owner/repo/issues/1")
        assert a == b

    def test_different_urls_different_keys(self):
        assert url_to_cache_key("https://github.com/a/b/issues/1") != \
               url_to_cache_key("https://github.com/a/b/issues/2")

    def test_returns_hex_string(self):
        key = url_to_cache_key("https://github.com/a/b/issues/1")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# get_cached_report / save_report
# ---------------------------------------------------------------------------

class TestCacheRoundTrip:
    URL = "https://github.com/owner/repo/issues/42"

    def test_cache_miss_returns_none(self):
        assert get_cached_report(self.URL) is None

    def test_save_and_retrieve(self):
        report = {"sections": {"issue_summary": "test"}, "url": self.URL}
        save_report(self.URL, report)
        loaded = get_cached_report(self.URL)
        assert loaded is not None
        assert loaded["sections"]["issue_summary"] == "test"

    def test_save_adds_cached_at(self):
        report = {"url": self.URL}
        save_report(self.URL, report)
        loaded = get_cached_report(self.URL)
        assert "cached_at" in loaded

    def test_save_preserves_existing_cached_at(self):
        report = {"url": self.URL, "cached_at": "2024-01-01T00:00:00+00:00"}
        save_report(self.URL, report)
        loaded = get_cached_report(self.URL)
        assert loaded["cached_at"] == "2024-01-01T00:00:00+00:00"

    def test_save_returns_key(self):
        key = save_report(self.URL, {"url": self.URL})
        assert key == url_to_cache_key(self.URL)

    def test_overwrite(self):
        save_report(self.URL, {"url": self.URL, "v": 1})
        save_report(self.URL, {"url": self.URL, "v": 2})
        loaded = get_cached_report(self.URL)
        assert loaded["v"] == 2


# ---------------------------------------------------------------------------
# get_report_by_key
# ---------------------------------------------------------------------------

class TestGetReportByKey:
    URL = "https://github.com/owner/repo/issues/99"

    def test_not_found_returns_none(self):
        assert get_report_by_key("nonexistentkey") is None

    def test_retrieves_by_key(self):
        report = {"url": self.URL, "data": "hello"}
        key = save_report(self.URL, report)
        loaded = get_report_by_key(key)
        assert loaded["data"] == "hello"


# ---------------------------------------------------------------------------
# list_cached_reports
# ---------------------------------------------------------------------------

class TestListCachedReports:
    def test_empty_dir_returns_empty_list(self):
        assert list_cached_reports() == []

    def test_lists_saved_reports(self):
        save_report("https://github.com/a/b/issues/1", {"url": "u1", "issue": {"title": "T1"}})
        save_report("https://github.com/a/b/issues/2", {"url": "u2", "issue": {"title": "T2"}})
        reports = list_cached_reports()
        assert len(reports) == 2

    def test_sorted_newest_first(self):
        save_report("https://github.com/a/b/issues/1", {
            "url": "u1", "cached_at": "2024-01-01T00:00:00+00:00"
        })
        save_report("https://github.com/a/b/issues/2", {
            "url": "u2", "cached_at": "2024-06-01T00:00:00+00:00"
        })
        reports = list_cached_reports()
        assert reports[0]["cached_at"] > reports[1]["cached_at"]

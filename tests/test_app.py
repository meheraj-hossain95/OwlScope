"""Tests for Flask app routes."""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a Flask test client with cache redirected to a temp dir."""
    import config
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))

    import cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))

    import app as app_mod
    app_mod.app.config["TESTING"] = True
    app_mod.app.config["WTF_CSRF_ENABLED"] = False

    with app_mod.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestIndexRoute:
    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    @patch("app.cache.list_cached_reports", return_value=[])
    def test_index_returns_200(self, mock_list, mock_conn, client):
        resp = client.get("/")
        assert resp.status_code == 200

    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    @patch("app.cache.list_cached_reports", return_value=[])
    def test_index_contains_form(self, mock_list, mock_conn, client):
        resp = client.get("/")
        assert b"analyze" in resp.data.lower()

    @patch("app.llm_client.check_connection", return_value=(False, "Connection refused"))
    @patch("app.cache.list_cached_reports", return_value=[])
    def test_index_shows_ollama_warning_when_unreachable(self, mock_list, mock_conn, client):
        resp = client.get("/")
        assert b"Ollama" in resp.data or b"unreachable" in resp.data.lower()


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------

class TestAnalyzeRoute:
    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    @patch("app.cache.list_cached_reports", return_value=[])
    def test_empty_url_redirects_with_flash(self, mock_list, mock_conn, client):
        resp = client.post("/analyze", data={"url": ""}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"paste" in resp.data.lower() or b"url" in resp.data.lower()

    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    @patch("app.cache.list_cached_reports", return_value=[])
    def test_invalid_url_redirects_with_flash(self, mock_list, mock_conn, client):
        resp = client.post(
            "/analyze", data={"url": "https://example.com/not-github"},
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"Invalid" in resp.data or b"invalid" in resp.data.lower()

    @patch("app.cache.get_cached_report")
    @patch("app.cache.url_to_cache_key", return_value="abc123")
    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    def test_cache_hit_redirects_to_report(self, mock_conn, mock_key, mock_cache, client):
        mock_cache.return_value = {"sections": {}, "url": "u", "issue": {}, "repo": {}, "is_pr": False}
        resp = client.post(
            "/analyze",
            data={"url": "https://github.com/owner/repo/issues/42"},
        )
        assert resp.status_code == 302
        assert b"abc123" in resp.headers["Location"].encode()

    @patch("app.report_generator.generate_report")
    @patch("app.github_fetcher.fetch_issue_context")
    @patch("app.cache.get_cached_report", return_value=None)
    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    def test_full_flow_generates_and_redirects(
        self, mock_conn, mock_no_cache, mock_fetch, mock_gen, client, tmp_path, monkeypatch
    ):
        import cache as cache_mod
        monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))

        mock_fetch.return_value = {
            "repo": {"full_name": "owner/repo", "description": "", "language": "Python",
                     "default_branch": "main", "topics": []},
            "issue": {"number": 42, "title": "Test", "body": "", "state": "open",
                      "labels": [], "author": "x", "created_at": ""},
            "comments": [], "is_pr": False, "pr_details": None,
            "changed_files": [], "file_tree": [], "relevant_files": {},
        }
        mock_gen.return_value = {
            "url": "https://github.com/owner/repo/issues/42",
            "issue": {"number": 42, "title": "Test"},
            "repo": {"full_name": "owner/repo"},
            "is_pr": False,
            "sections": {k: "content" for k in [
                "issue_summary","feature_impact","code_impact","visualization",
                "root_cause","fix_suggestions","test_generation","security_impact"
            ]},
            "generated_at": "2024-01-01T00:00:00+00:00",
        }

        resp = client.post(
            "/analyze",
            data={"url": "https://github.com/owner/repo/issues/42"},
        )
        assert resp.status_code == 302
        assert "/report/" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# GET /report/<key>
# ---------------------------------------------------------------------------

class TestViewReportRoute:
    def _seed_report(self, tmp_path):
        import cache as cache_mod
        report = {
            "url": "https://github.com/owner/repo/issues/42",
            "issue": {"number": 42, "title": "A bug"},
            "repo": {"full_name": "owner/repo"},
            "is_pr": False,
            "sections": {k: "# Section\ncontent" for k in [
                "issue_summary","feature_impact","code_impact","visualization",
                "root_cause","fix_suggestions","test_generation","security_impact"
            ]},
            "generated_at": "2024-01-01T00:00:00+00:00",
            "cached_at": "2024-01-01T00:00:00+00:00",
        }
        key = cache_mod.save_report(report["url"], report)
        return key, report

    def test_returns_200_for_valid_key(self, client, tmp_path, monkeypatch):
        import cache as cache_mod
        monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))
        import app as app_mod
        monkeypatch.setattr(app_mod.cache, "CACHE_DIR", str(tmp_path))

        key, _ = self._seed_report(tmp_path)
        resp = client.get(f"/report/{key}")
        assert resp.status_code == 200

    def test_shows_issue_title(self, client, tmp_path, monkeypatch):
        import cache as cache_mod
        monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))
        import app as app_mod
        monkeypatch.setattr(app_mod.cache, "CACHE_DIR", str(tmp_path))

        key, _ = self._seed_report(tmp_path)
        resp = client.get(f"/report/{key}")
        assert b"A bug" in resp.data

    def test_unknown_key_redirects(self, client):
        resp = client.get("/report/nonexistentkey123", follow_redirects=True)
        assert resp.status_code == 200
        assert b"not found" in resp.data.lower()


# ---------------------------------------------------------------------------
# GET /report/<key>/download
# ---------------------------------------------------------------------------

class TestDownloadRoute:
    def test_download_returns_markdown(self, client, tmp_path, monkeypatch):
        import cache as cache_mod
        monkeypatch.setattr(cache_mod, "CACHE_DIR", str(tmp_path))
        import app as app_mod
        monkeypatch.setattr(app_mod.cache, "CACHE_DIR", str(tmp_path))

        report = {
            "url": "https://github.com/owner/repo/issues/42",
            "issue": {"number": 42, "title": "A bug"},
            "repo": {"full_name": "owner/repo"},
            "is_pr": False,
            "sections": {"issue_summary": "summary text"},
            "generated_at": "2024-01-01T00:00:00+00:00",
        }
        key = cache_mod.save_report(report["url"], report)

        resp = client.get(f"/report/{key}/download")
        assert resp.status_code == 200
        assert b"OwlScope" in resp.data
        assert b"A bug" in resp.data
        assert b"attachment" in resp.headers["Content-Disposition"].encode()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthRoute:
    @patch("app.llm_client.check_connection", return_value=(True, "ok"))
    def test_health_connected(self, mock_conn, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ollama"] == "connected"

    @patch("app.llm_client.check_connection", return_value=(False, "Connection refused"))
    def test_health_unreachable(self, mock_conn, client):
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["ollama"] == "unreachable"

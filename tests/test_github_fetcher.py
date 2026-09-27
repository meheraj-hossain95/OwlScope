"""Tests for github_fetcher.py — URL parsing and fetch orchestration."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Make the OwlScope package importable from the tests/ sub-directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from github_fetcher import (
    parse_github_url,
    GitHubFetchError,
    select_relevant_files,
    fetch_issue_context,
)


# ---------------------------------------------------------------------------
# parse_github_url
# ---------------------------------------------------------------------------

class TestParseGitHubUrl:
    def test_issue_url(self):
        result = parse_github_url("https://github.com/owner/repo/issues/42")
        assert result == {"owner": "owner", "repo": "repo", "number": 42, "type": "issue"}

    def test_pr_url(self):
        result = parse_github_url("https://github.com/owner/repo/pull/7")
        assert result == {"owner": "owner", "repo": "repo", "number": 7, "type": "pr"}

    def test_url_with_fragment(self):
        result = parse_github_url(
            "https://github.com/owner/repo/issues/42#issuecomment-123456"
        )
        assert result["number"] == 42
        assert result["type"] == "issue"

    def test_url_with_trailing_slash(self):
        result = parse_github_url("https://github.com/owner/repo/issues/42/")
        assert result["number"] == 42

    def test_url_with_whitespace(self):
        result = parse_github_url("  https://github.com/owner/repo/issues/5  ")
        assert result["number"] == 5

    def test_invalid_url_raises(self):
        with pytest.raises(GitHubFetchError, match="Invalid GitHub URL"):
            parse_github_url("https://example.com/not-github")

    def test_empty_string_raises(self):
        with pytest.raises(GitHubFetchError):
            parse_github_url("")

    def test_github_non_issue_url_raises(self):
        with pytest.raises(GitHubFetchError):
            parse_github_url("https://github.com/owner/repo")

    def test_http_url_accepted(self):
        result = parse_github_url("http://github.com/owner/repo/issues/1")
        assert result["number"] == 1

    def test_org_with_hyphens(self):
        result = parse_github_url("https://github.com/my-org/my-repo/pull/100")
        assert result["owner"] == "my-org"
        assert result["repo"] == "my-repo"
        assert result["type"] == "pr"


# ---------------------------------------------------------------------------
# select_relevant_files
# ---------------------------------------------------------------------------

class TestSelectRelevantFiles:
    def _tree_entry(self, path):
        return {"type": "blob", "path": path}

    def test_prefers_changed_files(self):
        tree = [
            self._tree_entry("src/main.py"),
            self._tree_entry("src/utils.py"),
            self._tree_entry("README.md"),
        ]
        changed = [{"filename": "src/main.py"}]
        result = select_relevant_files(tree, "", changed, max_files=3)
        assert result[0] == "src/main.py"

    def test_prefers_mentioned_files(self):
        tree = [
            self._tree_entry("src/auth.py"),
            self._tree_entry("src/helpers.py"),
        ]
        result = select_relevant_files(tree, "Bug in auth.py module", [], max_files=2)
        assert "src/auth.py" in result

    def test_max_files_respected(self):
        tree = [self._tree_entry(f"file{i}.py") for i in range(20)]
        result = select_relevant_files(tree, "", [], max_files=5)
        assert len(result) <= 5

    def test_skips_non_source_files(self):
        tree = [
            self._tree_entry("data.csv"),
            self._tree_entry("image.png"),
            self._tree_entry("app.py"),
        ]
        result = select_relevant_files(tree, "", [], max_files=10)
        assert "data.csv" not in result
        assert "image.png" not in result
        assert "app.py" in result

    def test_empty_tree(self):
        result = select_relevant_files([], "some issue body", [], max_files=5)
        assert result == []

    def test_skips_directory_entries(self):
        tree = [
            {"type": "tree", "path": "src"},
            {"type": "blob", "path": "src/app.py"},
        ]
        result = select_relevant_files(tree, "", [], max_files=5)
        assert "src" not in result
        assert "src/app.py" in result


# ---------------------------------------------------------------------------
# fetch_issue_context — integration-level with mocked HTTP
# ---------------------------------------------------------------------------

def _mock_response(data, status=200):
    m = MagicMock()
    m.ok = status < 400
    m.status_code = status
    m.json.return_value = data
    return m


class TestFetchIssueContext:
    @patch("github_fetcher.requests.get")
    def test_fetches_issue_context(self, mock_get):
        """Happy path: issue URL returns assembled context dict."""
        responses = [
            # get_repo_info
            _mock_response({
                "full_name": "owner/repo", "description": "test repo",
                "language": "Python", "default_branch": "main", "topics": []
            }),
            # get_issue
            _mock_response({
                "number": 42, "title": "Test issue", "body": "Something broke",
                "state": "open", "labels": [], "user": {"login": "alice"}, "created_at": "2024-01-01"
            }),
            # get_issue_comments
            _mock_response([]),
            # get_repo_tree
            _mock_response({"tree": [{"type": "blob", "path": "app.py"}]}),
            # get_file_content for app.py
            _mock_response({
                "encoding": "base64",
                "content": __import__("base64").b64encode(b"print('hello')").decode() + "\n",
                "size": 14,
            }),
        ]
        mock_get.side_effect = responses

        ctx = fetch_issue_context("https://github.com/owner/repo/issues/42")

        assert ctx["issue"]["title"] == "Test issue"
        assert ctx["repo"]["full_name"] == "owner/repo"
        assert ctx["is_pr"] is False
        assert ctx["comments"] == []

    @patch("github_fetcher.requests.get")
    def test_404_raises_github_fetch_error(self, mock_get):
        mock_get.return_value = _mock_response({}, status=404)
        with pytest.raises(GitHubFetchError, match="404"):
            fetch_issue_context("https://github.com/owner/repo/issues/1")

    @patch("github_fetcher.requests.get")
    def test_403_raises_github_fetch_error(self, mock_get):
        mock_get.return_value = _mock_response({}, status=403)
        with pytest.raises(GitHubFetchError, match="rate limit"):
            fetch_issue_context("https://github.com/owner/repo/issues/1")

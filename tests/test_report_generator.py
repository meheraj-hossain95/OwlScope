"""Tests for report_generator.py — context building and section generation."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from report_generator import (
    build_context_string,
    generate_section,
    generate_report,
    SECTION_ORDER,
    SECTION_LABELS,
    _CONTEXT_CHAR_LIMIT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_context(
    title="Auth bug",
    body="Login fails with 500",
    language="Python",
    is_pr=False,
    comments=None,
    changed_files=None,
    file_tree=None,
    relevant_files=None,
):
    return {
        "repo": {
            "full_name": "owner/repo",
            "description": "Test repo",
            "language": language,
            "default_branch": "main",
            "topics": [],
        },
        "issue": {
            "number": 42,
            "title": title,
            "body": body,
            "state": "open",
            "labels": ["bug"],
            "author": "alice",
            "created_at": "2024-01-01",
        },
        "comments": comments or [],
        "is_pr": is_pr,
        "pr_details": None,
        "changed_files": changed_files or [],
        "file_tree": file_tree or ["app.py", "utils.py"],
        "relevant_files": relevant_files or {},
    }


# ---------------------------------------------------------------------------
# build_context_string
# ---------------------------------------------------------------------------

class TestBuildContextString:
    def test_contains_repo_name(self):
        ctx = _make_context()
        result = build_context_string(ctx)
        assert "owner/repo" in result

    def test_contains_issue_title(self):
        ctx = _make_context(title="Crash on startup")
        result = build_context_string(ctx)
        assert "Crash on startup" in result

    def test_contains_issue_body(self):
        ctx = _make_context(body="Error in production")
        result = build_context_string(ctx)
        assert "Error in production" in result

    def test_pr_label_shown(self):
        ctx = _make_context(is_pr=True)
        result = build_context_string(ctx)
        assert "PULL REQUEST" in result

    def test_issue_label_shown(self):
        ctx = _make_context(is_pr=False)
        result = build_context_string(ctx)
        assert "ISSUE" in result

    def test_comments_included(self):
        ctx = _make_context(comments=[{"author": "bob", "body": "Can confirm", "created_at": ""}])
        result = build_context_string(ctx)
        assert "bob" in result
        assert "Can confirm" in result

    def test_changed_files_included(self):
        ctx = _make_context(
            is_pr=True,
            changed_files=[{
                "filename": "auth/login.py",
                "status": "modified",
                "additions": 5,
                "deletions": 2,
                "patch": "- old\n+ new",
            }],
        )
        result = build_context_string(ctx)
        assert "auth/login.py" in result

    def test_relevant_files_included(self):
        ctx = _make_context(relevant_files={"app.py": "def main(): pass"})
        result = build_context_string(ctx)
        assert "def main(): pass" in result

    def test_context_truncated_at_limit(self):
        long_body = "x" * (_CONTEXT_CHAR_LIMIT + 5000)
        ctx = _make_context(body=long_body)
        result = build_context_string(ctx)
        assert len(result) <= _CONTEXT_CHAR_LIMIT + 50  # small allowance for truncation message
        assert "truncated" in result.lower()


# ---------------------------------------------------------------------------
# generate_section
# ---------------------------------------------------------------------------

class TestGenerateSection:
    @patch("report_generator.llm_client.generate")
    def test_calls_llm_and_returns_text(self, mock_gen):
        mock_gen.return_value = "## Issue Summary\n\nAuth fails."
        ctx = _make_context()
        result = generate_section("issue_summary", build_context_string(ctx))
        assert "Auth fails" in result
        mock_gen.assert_called_once()

    @patch("report_generator.llm_client.generate")
    def test_llm_error_returns_error_message(self, mock_gen):
        from llm_client import LLMError
        mock_gen.side_effect = LLMError("Connection refused")
        ctx = _make_context()
        result = generate_section("issue_summary", build_context_string(ctx))
        assert "Generation failed" in result
        assert "Connection refused" in result


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    @patch("report_generator.llm_client.generate")
    def test_all_sections_present(self, mock_gen):
        mock_gen.return_value = "Generated content."
        ctx = _make_context()
        report = generate_report(ctx, url="https://github.com/owner/repo/issues/42")

        assert "sections" in report
        for key in SECTION_ORDER:
            assert key in report["sections"], f"Missing section: {key}"

    @patch("report_generator.llm_client.generate")
    def test_report_contains_metadata(self, mock_gen):
        mock_gen.return_value = "Content."
        ctx = _make_context()
        report = generate_report(ctx, url="https://github.com/owner/repo/issues/42")

        assert report["url"] == "https://github.com/owner/repo/issues/42"
        assert report["repo"]["full_name"] == "owner/repo"
        assert report["issue"]["title"] == "Auth bug"
        assert "generated_at" in report

    @patch("report_generator.llm_client.generate")
    def test_llm_called_once_per_section(self, mock_gen):
        mock_gen.return_value = "Content."
        ctx = _make_context()
        generate_report(ctx)
        assert mock_gen.call_count == len(SECTION_ORDER)

    @patch("report_generator.llm_client.generate")
    def test_partial_llm_failure_still_returns_all_sections(self, mock_gen):
        """If LLM fails for one section, the others still generate."""
        from llm_client import LLMError
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 3:
                raise LLMError("Oops")
            return "Content."

        mock_gen.side_effect = side_effect
        ctx = _make_context()
        report = generate_report(ctx)
        assert len(report["sections"]) == len(SECTION_ORDER)
        # The failed section should contain an error message
        failed_key = SECTION_ORDER[2]
        assert "Generation failed" in report["sections"][failed_key]


# ---------------------------------------------------------------------------
# SECTION_LABELS completeness
# ---------------------------------------------------------------------------

def test_all_sections_have_labels():
    for key in SECTION_ORDER:
        assert key in SECTION_LABELS, f"SECTION_LABELS missing key: {key}"

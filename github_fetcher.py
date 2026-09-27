"""GitHub REST API fetcher for OwlScope.

Fetches all context needed to investigate a GitHub issue or PR:
  - Issue metadata, body, labels, assignees
  - All comments
  - PR diff and changed files (if a pull request)
  - Repo top-level file tree
  - Content of up to 5 most relevant source files
"""

import re
import base64
import requests

from config import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"

# Heuristic: only fetch content for these source file extensions
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".cpp", ".c", ".h", ".php", ".rs", ".swift", ".kt",
    ".vue", ".svelte", ".html", ".css", ".scss",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    """Build request headers. Adds Authorization only when token is set."""
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _get(url: str, params: dict = None) -> dict | list | None:
    """GET a GitHub API endpoint. Returns parsed JSON or raises on error."""
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
    except requests.exceptions.RequestException as exc:
        raise GitHubFetchError(f"Network error calling GitHub API: {exc}") from exc

    if resp.status_code == 404:
        raise GitHubFetchError(f"GitHub returned 404 — resource not found: {url}")
    if resp.status_code == 403:
        raise GitHubFetchError(
            "GitHub API rate limit hit or access denied (403). "
            "Set GITHUB_TOKEN in .env to increase rate limits."
        )
    if resp.status_code == 401:
        raise GitHubFetchError("GitHub API returned 401 — invalid token.")
    if not resp.ok:
        raise GitHubFetchError(
            f"GitHub API error {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class GitHubFetchError(Exception):
    """Raised when the GitHub API call fails for any reason."""


# ---------------------------------------------------------------------------
# URL parser
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> dict:
    """Parse a GitHub issue or PR URL into its components.

    Supports:
      https://github.com/owner/repo/issues/123
      https://github.com/owner/repo/pull/123
      https://github.com/owner/repo/issues/123#issuecomment-...

    Returns:
        {"owner": str, "repo": str, "number": int, "type": "issue"|"pr"}

    Raises:
        GitHubFetchError: if the URL is not a recognised GitHub issue/PR URL.
    """
    url = url.strip().split("#")[0].rstrip("/")
    pattern = r"https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)"
    match = re.match(pattern, url)
    if not match:
        raise GitHubFetchError(
            "Invalid GitHub URL. Expected format: "
            "https://github.com/owner/repo/issues/123  or  .../pull/123"
        )
    owner, repo, kind, number = match.groups()
    return {
        "owner": owner,
        "repo": repo,
        "number": int(number),
        "type": "pr" if kind == "pull" else "issue",
    }


# ---------------------------------------------------------------------------
# Individual fetchers
# ---------------------------------------------------------------------------

def get_issue(owner: str, repo: str, number: int) -> dict:
    """Fetch issue (or PR) metadata from /repos/{owner}/{repo}/issues/{number}."""
    return _get(f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}")


def get_issue_comments(owner: str, repo: str, number: int) -> list:
    """Fetch all comments for an issue or PR (up to 100)."""
    return _get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}/comments",
        params={"per_page": 100},
    ) or []


def get_pr_details(owner: str, repo: str, number: int) -> dict:
    """Fetch PR-specific metadata (merge base, head, etc.)."""
    return _get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}")


def get_pr_files(owner: str, repo: str, number: int) -> list:
    """Fetch the list of files changed in a PR, including patch diffs (up to 100)."""
    return _get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/files",
        params={"per_page": 100},
    ) or []


def get_repo_info(owner: str, repo: str) -> dict:
    """Fetch basic repo metadata (description, default branch, language)."""
    return _get(f"{GITHUB_API}/repos/{owner}/{repo}")


def get_repo_tree(owner: str, repo: str, branch: str) -> list:
    """Fetch the full (recursive) file tree of the repo, truncated to 300 entries."""
    data = _get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}",
        params={"recursive": "1"},
    )
    if not data:
        return []
    return data.get("tree", [])[:300]


def get_file_content(owner: str, repo: str, path: str) -> str | None:
    """Fetch and decode the content of a single file (max 1 MB).

    Returns the decoded text, or None if the file is too large or not text.
    """
    try:
        data = _get(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}")
    except GitHubFetchError:
        return None

    if not isinstance(data, dict):
        return None
    if data.get("encoding") != "base64":
        return None
    size = data.get("size", 0)
    if size > 100_000:  # skip files larger than 100 KB
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Relevance heuristic
# ---------------------------------------------------------------------------

def _has_source_extension(path: str) -> bool:
    for ext in SOURCE_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def select_relevant_files(
    file_tree: list,
    issue_body: str,
    changed_files: list,
    max_files: int = 5,
) -> list[str]:
    """Return up to `max_files` file paths most relevant to the issue.

    Priority:
      1. Files explicitly mentioned in the issue body
      2. Files changed in the PR diff
      3. Source files at the top level of the tree
    """
    mentioned = set()
    if issue_body:
        # Extract anything that looks like a file path in the issue text
        for token in re.findall(r"[\w/\-\.]+\.\w+", issue_body):
            mentioned.add(token.lower())

    scored: list[tuple[int, str]] = []
    changed_paths = {f.get("filename", "") for f in changed_files}

    for entry in file_tree:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        if not _has_source_extension(path):
            continue

        score = 0
        name = path.split("/")[-1].lower()
        if path in changed_paths:
            score += 10
        if name in mentioned or path.lower() in mentioned:
            score += 5
        if "/" not in path:
            score += 1  # top-level files
        scored.append((score, path))

    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:max_files]]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_issue_context(url: str) -> dict:
    """Fetch all GitHub context for a given issue or PR URL.

    Returns a structured dict with:
      - parsed: URL components
      - repo: repo metadata
      - issue: issue/PR metadata
      - comments: list of comment bodies
      - is_pr: bool
      - pr_details: PR metadata (if PR)
      - changed_files: list of {filename, patch, additions, deletions} (if PR)
      - file_tree: list of file paths in the repo
      - relevant_files: {path: content} for up to 5 key files
    """
    parsed = parse_github_url(url)
    owner, repo_name, number, kind = (
        parsed["owner"], parsed["repo"], parsed["number"], parsed["type"]
    )

    # Repo info (needed for default branch)
    repo_info = get_repo_info(owner, repo_name)
    default_branch = repo_info.get("default_branch", "main")

    # Issue data
    issue = get_issue(owner, repo_name, number)
    comments_raw = get_issue_comments(owner, repo_name, number)
    comments = [
        {
            "author": c.get("user", {}).get("login", "unknown"),
            "body": c.get("body", ""),
            "created_at": c.get("created_at", ""),
        }
        for c in comments_raw
    ]

    # PR-specific data
    is_pr = kind == "pr"
    pr_details = None
    changed_files = []
    if is_pr:
        try:
            pr_details = get_pr_details(owner, repo_name, number)
        except GitHubFetchError:
            pr_details = {}
        raw_files = get_pr_files(owner, repo_name, number)
        changed_files = [
            {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch", "")[:3000],  # cap patch size
            }
            for f in raw_files
        ]

    # Repo file tree
    file_tree = get_repo_tree(owner, repo_name, default_branch)

    # Select and fetch relevant source files
    issue_body = issue.get("body") or ""
    relevant_paths = select_relevant_files(file_tree, issue_body, changed_files)
    relevant_files = {}
    for path in relevant_paths:
        content = get_file_content(owner, repo_name, path)
        if content:
            relevant_files[path] = content[:4000]  # cap individual file size

    return {
        "parsed": parsed,
        "repo": {
            "full_name": repo_info.get("full_name", f"{owner}/{repo_name}"),
            "description": repo_info.get("description", ""),
            "language": repo_info.get("language", ""),
            "default_branch": default_branch,
            "topics": repo_info.get("topics", []),
        },
        "issue": {
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "body": issue_body,
            "state": issue.get("state", ""),
            "labels": [
                {"name": lb.get("name", ""), "color": lb.get("color", "555555")}
                for lb in issue.get("labels", [])
            ],
            "author": issue.get("user", {}).get("login", "unknown"),
            "author_avatar": issue.get("user", {}).get("avatar_url", ""),
            "created_at": issue.get("created_at", ""),
            "updated_at": issue.get("updated_at", ""),
            "comments": issue.get("comments", 0),
        },
        "pr_branches": {
            "head": pr_details.get("head", {}).get("label", "") if pr_details else "",
            "base": pr_details.get("base", {}).get("label", "") if pr_details else "",
        } if is_pr else None,
        "comments": comments,
        "is_pr": is_pr,
        "pr_details": pr_details,
        "changed_files": changed_files,
        "file_tree": [e.get("path", "") for e in file_tree if e.get("type") == "blob"],
        "relevant_files": relevant_files,
    }

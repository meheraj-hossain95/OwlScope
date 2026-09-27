"""Section-by-section report generator for OwlScope.

Takes the context dict from github_fetcher.fetch_issue_context() and
generates a structured investigation report by calling the LLM once
per section.  Each section gets a focused, targeted prompt so the
quality of each section stays high.
"""

import json
from datetime import datetime, timezone

import llm_client

# ---------------------------------------------------------------------------
# Context serialiser
# ---------------------------------------------------------------------------

# Rough token budget: 6000 chars ≈ ~1500 tokens, safe for most 7B models
_CONTEXT_CHAR_LIMIT = 18_000


def build_context_string(ctx: dict) -> str:
    """Serialise the GitHub context dict into a compact text block for the LLM."""
    parts = []

    repo = ctx.get("repo", {})
    issue = ctx.get("issue", {})

    parts.append(f"REPOSITORY: {repo.get('full_name', 'unknown')}")
    if repo.get("description"):
        parts.append(f"DESCRIPTION: {repo['description']}")
    if repo.get("language"):
        parts.append(f"PRIMARY LANGUAGE: {repo['language']}")

    parts.append("")
    issue_type = "PULL REQUEST" if ctx.get("is_pr") else "ISSUE"
    parts.append(f"{issue_type} #{issue.get('number')}: {issue.get('title', '')}")
    parts.append(f"State: {issue.get('state', '')}  |  Author: {issue.get('author', '')}")
    if issue.get("labels"):
        label_names = [lb["name"] if isinstance(lb, dict) else lb for lb in issue["labels"]]
        parts.append(f"Labels: {', '.join(label_names)}")
    parts.append("")
    parts.append("--- BODY ---")
    parts.append(issue.get("body") or "(no body)")

    comments = ctx.get("comments", [])
    if comments:
        parts.append("")
        parts.append("--- COMMENTS ---")
        for c in comments[:10]:  # cap to 10 comments
            parts.append(f"[{c.get('author', '?')}]: {c.get('body', '')[:500]}")

    changed_files = ctx.get("changed_files", [])
    if changed_files:
        parts.append("")
        parts.append("--- CHANGED FILES (PR DIFF) ---")
        for f in changed_files:
            parts.append(
                f"  {f['filename']}  (+{f['additions']} -{f['deletions']}, {f['status']})"
            )
            if f.get("patch"):
                parts.append(f"  PATCH:\n{f['patch'][:1500]}")

    file_tree = ctx.get("file_tree", [])
    if file_tree:
        parts.append("")
        parts.append("--- REPO FILE TREE (sample) ---")
        parts.append("\n".join(file_tree[:80]))

    relevant_files = ctx.get("relevant_files", {})
    if relevant_files:
        parts.append("")
        parts.append("--- KEY SOURCE FILES ---")
        for path, content in relevant_files.items():
            parts.append(f"\n## {path}\n{content[:3000]}")

    full = "\n".join(parts)
    if len(full) > _CONTEXT_CHAR_LIMIT:
        full = full[:_CONTEXT_CHAR_LIMIT] + "\n... [context truncated for length]"
    return full


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are OwlScope, an expert software engineering assistant. "
    "You analyse GitHub issues and pull requests to help developers understand "
    "their codebase and fix problems faster. "
    "Be concise, specific, and technical. Use Markdown formatting in your responses. "
    "Base all reasoning strictly on the provided context — do not invent details."
)


# ---------------------------------------------------------------------------
# Section prompt templates
# ---------------------------------------------------------------------------

_SECTION_PROMPTS = {
    "issue_summary": (
        "Write a concise **Issue Summary** section.\n"
        "Include:\n"
        "- Plain-language restatement of what is broken or being requested\n"
        "- Reproduction steps if it is a bug report\n"
        "- The reporter's environment details if mentioned\n"
        "Keep it under 200 words."
    ),
    "feature_impact": (
        "Write a **Feature Impact** section.\n"
        "Identify which existing features, user-facing routes, API endpoints, "
        "or user flows might be affected by this issue or PR. "
        "Be specific — name the routes/endpoints/features you can infer from the code context. "
        "If this is a PR, describe what the changes enable or break."
    ),
    "code_impact": (
        "Write a **Code Impact** section.\n"
        "List the specific files, modules, classes, and functions that are involved in or "
        "affected by this issue. For each, briefly explain *why* it is relevant. "
        "Use code references like `file.py::ClassName.method_name` where possible."
    ),
    "visualization": (
        "Write a **Call Graph / Visualization** section.\n"
        "Based on the code context, describe the call chain relevant to this issue. "
        "Show what calls the affected code and what the affected code calls. "
        "Use a simple ASCII or Markdown text diagram, for example:\n"
        "```\nrequestHandler() → processData() → validateInput() → saveRecord()\n```\n"
        "Also note any event emitters, hooks, or middleware chains involved."
    ),
    "root_cause": (
        "Write a **Root Cause Location** section.\n"
        "Identify the most likely file(s) and line/function where the root cause lives. "
        "Explain your reasoning — why does the evidence point to this location? "
        "If you cannot pinpoint a line, name the function and explain what logic is suspect."
    ),
    "fix_suggestions": (
        "Write a **Fix Suggestions** section.\n"
        "Propose 1–2 concrete approaches to fix this issue. For each approach:\n"
        "- Describe what change to make and where\n"
        "- List the tradeoffs (pros/cons)\n"
        "Do NOT write full code — just clear descriptions a developer can act on."
    ),
    "test_generation": (
        "Write a **Test Generation** section.\n"
        "List specific test cases that should be written to verify the fix. For each test:\n"
        "- Name the test (e.g. `test_invalid_input_raises_value_error`)\n"
        "- Describe what it tests and the expected outcome\n"
        "- Mention the testing framework idiomatic for the repo language if apparent\n"
        "Cover happy paths, edge cases, and regression cases."
    ),
    "security_impact": (
        "Write a **Security Impact** section.\n"
        "Analyse whether this issue or the proposed fix could introduce security risks. "
        "Consider: injection attacks, authentication/authorisation bypass, data exposure, "
        "insecure defaults, dependency risks, or privilege escalation. "
        "If no security risks are apparent, state that clearly with brief reasoning."
    ),
}

SECTION_ORDER = [
    "issue_summary",
    "feature_impact",
    "code_impact",
    "visualization",
    "root_cause",
    "fix_suggestions",
    "test_generation",
    "security_impact",
]

SECTION_LABELS = {
    "issue_summary":   "Issue Summary",
    "feature_impact":  "Feature Impact",
    "code_impact":     "Code Impact",
    "visualization":   "Call Graph / Visualization",
    "root_cause":      "Root Cause Location",
    "fix_suggestions": "Fix Suggestions",
    "test_generation": "Test Generation",
    "security_impact": "Security Impact",
}


# ---------------------------------------------------------------------------
# Section generator
# ---------------------------------------------------------------------------

def generate_section(section_key: str, context_string: str) -> str:
    """Generate one report section by prompting the LLM.

    Returns the section text, or an error notice if LLM fails.
    """
    section_prompt = _SECTION_PROMPTS[section_key]
    prompt = (
        f"=== GITHUB CONTEXT ===\n{context_string}\n\n"
        f"=== YOUR TASK ===\n{section_prompt}"
    )
    try:
        return llm_client.generate(prompt, system=_SYSTEM)
    except llm_client.LLMError as exc:
        return f"*[Generation failed for this section: {exc}]*"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(context: dict, url: str = "") -> dict:
    """Generate a full OwlScope investigation report from GitHub context.

    Args:
        context: The dict returned by github_fetcher.fetch_issue_context().
        url:     The original GitHub URL (stored in the report for reference).

    Returns:
        A report dict with keys for each section plus metadata.
    """
    context_string = build_context_string(context)
    sections = {}
    for key in SECTION_ORDER:
        sections[key] = generate_section(key, context_string)

    return {
        "url": url,
        "issue": context.get("issue", {}),
        "repo": context.get("repo", {}),
        "is_pr": context.get("is_pr", False),
        "pr_branches": context.get("pr_branches"),
        "sections": sections,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

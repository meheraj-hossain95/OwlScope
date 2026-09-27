# OwlScope — Issue Investigator

> **Paste a GitHub issue or PR URL. Get a full AI-powered investigation report in seconds.**

---

## Short Description

OwlScope is a local-first AI tool that takes any GitHub issue or pull request URL and generates a structured, multi-section investigation report — covering issue summary, feature impact, code impact, call graph visualization, root cause location, fix suggestions, test generation, and security impact — all powered by a local LLM via Ollama, with zero data leaving your machine.

---

## Long Description

Modern software development moves fast. When a bug is filed or a pull request is opened, developers often spend 30–60 minutes just *reading context* — skimming through comments, opening files, tracing call chains, and mentally mapping what could break. OwlScope eliminates that ramp-up time.

You paste a GitHub issue or PR URL. OwlScope's backend silently fetches the full context: the issue title, body, labels, state, comments, the repository file tree, and the content of the most relevant source files — all through the free GitHub API with no cloning. It then assembles a precise, structured prompt and sends it to your local Ollama instance. Within seconds, a complete investigation report appears in your browser — collapsible cards, one per section, rendered in clean Markdown with syntax-highlighted code blocks.

The report is not generic AI output. It is grounded in the actual code of the repository being investigated. Every section — from root cause pinpointing to suggested test names — references real file paths, real function names, and real PR diffs that were fetched from GitHub. The LLM acts as a reasoning engine on top of real data, not a hallucination factory.

OwlScope runs entirely offline after setup. There is no login, no database, no cloud dependency. Reports are cached locally as JSON and can be downloaded as Markdown or printed to PDF directly from the browser.

---

## Technology & Category Tags

| Category         | Technologies                                                                 |
|------------------|------------------------------------------------------------------------------|
| **Language**     | Python 3.11+                                                                 |
| **Backend**      | Flask 3.x, Jinja2                                                            |
| **AI / LLM**     | Ollama (local inference), `qwen2.5-coder:7b` (default), any Ollama model    |
| **Data Source**  | GitHub REST API v3 (free tier, no cloning)                                   |
| **Frontend**     | Vanilla HTML/CSS/JS, Markdown rendering via `python-markdown`                |
| **Deps**         | `flask`, `requests`, `python-dotenv`, `markdown`, `pytest`                   |
| **Theme**        | Dark, minimal — inspired by Linear, GitHub, Raycast                          |
| **Category**     | Developer Tools · AI Assistants · Code Review · Static Analysis              |
| **License**      | MIT                                                                          |

---

## The Full Idea — What OwlScope Does

### The Problem It Solves

Every developer knows the feeling: a GitHub issue lands in your queue with a vague title, a two-line description, and a wall of stack traces in the comments. Or a PR appears that touches 12 files across 4 modules, and you need to review it in 20 minutes. Context gathering is the silent tax on developer productivity — and it scales poorly as codebases grow.

OwlScope is built to answer one question: **"What is actually going on with this issue or PR?"** — and answer it fast, with specifics.

---

### How It Works — The Full Flow

```
User pastes URL
      │
      ▼
Flask parses github.com/owner/repo/issues|pull/N
      │
      ▼
GitHub API fetches:
  • Issue/PR metadata (title, body, labels, state, author, dates, comments)
  • PR diff + changed file list (if PR)
  • Repository file tree (up to 300 entries, recursive)
  • Content of up to 5 most relevant source files (scored by mention + diff)
      │
      ▼
Context assembled into structured text block (~18k chars)
      │
      ▼
Ollama (local LLM) generates all selected sections in one shot
      │
      ▼
Report rendered as collapsible cards in browser
      │
      ▼
User downloads as Markdown or prints to PDF
```

#### Step 1 — URL Parsing
The app extracts `owner`, `repo`, `number`, and `type` (issue or PR) from the URL using a regex parser. It supports both `github.com/owner/repo/issues/N` and `github.com/owner/repo/pull/N` with fragment stripping.

#### Step 2 — GitHub Context Fetching
Using only the free GitHub REST API (no OAuth, no token required for public repos):

- **Issue metadata**: title, body, state (open/closed/merged), labels with real hex colors, author login, avatar URL, created/updated timestamps, comment count
- **Comments**: up to 100 comments, each with author and body
- **PR details** (if PR): head and base branch labels, changed files list with addition/deletion counts and diff patches (capped at 3,000 chars per file)
- **Repository file tree**: recursive tree up to 300 entries
- **Relevant source files**: scored by whether files are mentioned in the issue body, appear in the PR diff, or sit at the repo root — top 5 fetched, content capped at 4,000 chars each

A GitHub Personal Access Token can optionally be set in `.env` to raise the rate limit from 60 to 5,000 requests/hour.

#### Step 3 — LLM Prompting
The context is serialized into a compact text block (capped at 18,000 chars to stay within 7B model context windows). A system prompt establishes OwlScope's persona as a senior software engineering analyst. The context and a targeted section-specific instruction are concatenated and sent to Ollama with `stream=False` — the full response is awaited before rendering.

#### Step 4 — Report Rendering
The response is parsed into 8 named sections. Each section is rendered as a collapsible card in the browser using `python-markdown` with fenced code blocks and table support. The first card is open by default; the rest are collapsed. Each card has a unique SVG icon matching its purpose.

---

### The 8 Report Sections

As seen in the screenshots of real OwlScope output investigating `openfaas/python-flask-template` PR #73 ("fix: ensure test layer is in the build DAG"):

#### 1. Issue Summary
A plain-language restatement of what is broken or being requested, including reproduction steps if the issue is a bug report. The LLM reads the issue body and comments and produces a concise, structured summary.

> *From the screenshot:* OwlScope correctly identified that modern Docker build systems were optimizing away the `test` layer in OpenFaaS Python Flask templates because it had no explicit dependency chain to the `ship` layer — and provided full numbered reproduction steps.

#### 2. Feature Impact
An analysis of which existing features, user-facing routes, API endpoints, or user flows are affected by the issue or PR. If it is a PR, this section describes what the changes enable or break.

> *From the screenshot:* OwlScope identified that the change impacts the build process, the testing infrastructure availability, user-defined testing flows, and documented the effect of the `TEST_ENABLED` flag interaction.

#### 3. Code Impact
A precise list of the specific files, modules, classes, and functions involved in or affected by the issue — with brief reasoning for each.

> *From the screenshot:* OwlScope listed all four affected Dockerfiles (`template/python3-flask-debian/Dockerfile`, `template/python3-flask/Dockerfile`, `template/python3-http-debian/Dockerfile`, `template/python3-http/Dockerfile`), explained the structural `FROM` directive change, and provided exact code references (`template/python3-flask-debian/Dockerfile::FROM build as ship`).

#### 4. Call Graph / Visualization
A text-based call chain showing what calls the affected code and what the affected code calls. For API-based projects this traces the route → handler → function call chain.

> *From the screenshot:* `main_route() → handler.handle() → handle()` — a clean, precise chain for this particular codebase.

#### 5. Root Cause Location
The most likely file(s) and line(s) where the root cause lives, with step-by-step reasoning backed by evidence from the PR diff and issue text.

> *From the screenshot:* OwlScope pinpointed `template/python3-flask-debian/Dockerfile` at lines 48 and 50, explained the multi-stage build structure (`build → test → ship`), the missing dependency between `test` and `ship`, and cited the PR's own diff as evidence.

#### 6. Fix Suggestions
One to two concrete approaches to fix the issue, each with a description of what to change, where to change it, and an explicit tradeoffs table (pros and cons).

> *From the screenshot:* Approach 1 was "Explicitly Include Test Layer in Build DAG" (change `FROM build as ship` to `FROM test as ship`) with an actual code snippet. Approach 2 was "Use Multi-Stage Builds with Explicit Layer Caching."

#### 7. Test Generation
Specific test cases that should be written to verify the fix, each with a test function name, description, expected outcome, and the testing framework idiomatic for the repo's language.

> *From the screenshot:* OwlScope generated 5 named test cases including `test_handler_valid_input`, `test_handler_empty_input`, `test_handler_invalid_input`, `test_handler_regression_valid_input`, and `test_handler_regression_empty_input` — all with pytest/unittest guidance.

#### 8. Security Impact
An analysis of whether the issue or proposed fix could introduce security risks. Considers injection, auth bypass, data exposure, insecure defaults, dependency risks, and privilege escalation. "None identified" is a valid result with reasoning.

> *From the screenshot:* OwlScope correctly assessed no security risk for this build-system PR, with clear reasoning that the change is limited to the build process and does not affect runtime code execution or data handling.

---

### Report Header
Every report begins with a rich metadata card showing:

- **Type badge**: `Issue` (blue) or `Pull Request` (purple)
- **State badge**: `Open` (green), `Closed` (red), or `Merged` (purple)
- **Repository link**: `owner/repo` with GitHub icon, linked to GitHub
- **Issue/PR number**: `#73`
- **Title**: Large, prominent — e.g. *"fix: ensure test layer is in the build DAG"*
- **Author**: Avatar + username inline
- **Dates**: Created + last updated
- **Comment count**: With chat icon
- **PR branches**: `head-branch → base-branch` with branch icon (PRs only)
- **Labels**: Small colored chips using GitHub's actual label hex colors
- **Generated timestamp**: UTC timestamp of when the report was produced

---

## UI Design

OwlScope's interface is deliberately minimal and professional. It takes design cues from **Linear**, **GitHub**, and **Raycast** — dark, sharp, dense, high-contrast.

### Color Palette

| Role                | Hex         |
|---------------------|-------------|
| Background (deep)   | `#0B0D10`   |
| Background (card)   | `#111318`   |
| Background (raised) | `#181B21`   |
| Background (input)  | `#252A32`   |
| Primary text        | `#F3F4F6`   |
| Dimmed text         | `#E7E3DA`   |
| Muted text          | `#8FA3BF`   |
| Faint text          | `#9AA2AE`   |
| Accent / success    | `#78A88B`   |
| Warning             | `#C4A86A`   |
| Danger              | `#C8747C`   |

### Home Page
The home page shows the OwlScope owl icon beside the two-line heading "Investigate any / GitHub Issue or PR", a concise subtitle, an Ollama connection status badge (live check on page load), a full-width URL input with an "Investigate" button, and a "Recent Reports" list showing the last 5 cached investigations.

### Report Page
The report page opens with a top bar containing an "Analyze Another" button (left) and Markdown/PDF download buttons (right). Below is the full report header card, then a "Jump To" navigation bar with frosted-glass pill buttons for each section, then the collapsible section cards.

---

## Project Structure

```
OwlScope/
├── app.py                  # Flask routes, Jinja filters, download endpoint
├── config.py               # Environment variable loading
├── github_fetcher.py       # GitHub REST API calls, URL parsing, file scoring
├── report_generator.py     # LLM prompts, section generation, context serializer
├── llm_client.py           # Ollama HTTP client, connection check
├── cache.py                # File-based JSON report cache
├── context_builder.py      # Context assembly helpers
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── static/
│   ├── style.css           # Full dark-theme stylesheet
│   └── icon.png            # OwlScope owl logo
└── templates/
    ├── base.html           # Base layout, footer
    ├── index.html          # Home page — input form, recent reports
    └── report.html         # Report page — header, TOC, section cards
```

---

## Setup & Installation

### Prerequisites

| Requirement     | Version      | Notes                                               |
|-----------------|--------------|-----------------------------------------------------|
| Python          | 3.10+        | 3.11 recommended                                    |
| Ollama          | Latest       | https://ollama.com — must be running locally        |
| Ollama model    | Any          | Default: `qwen2.5-coder:7b` — pull before first run|

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/owlscope.git
cd owlscope/OwlScope
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Local Ollama (default)
OLLAMA_HOST=http://localhost:11434

# Or a remote Ollama via ngrok tunnel
# OLLAMA_HOST=https://xxxx.ngrok-free.app

OLLAMA_MODEL=qwen2.5-coder:7b

# Optional — raises GitHub API rate limit from 60 to 5000 req/hour
GITHUB_TOKEN=your_github_pat_here

# Change this to a long random string in production
FLASK_SECRET_KEY=your-secret-key
```

### 5. Pull the Ollama Model

```bash
ollama pull qwen2.5-coder:7b
```

You can use any other model available in your Ollama instance. Larger models (14B+) produce more detailed reports.

### 6. Start Ollama

```bash
ollama serve
```

### 7. Run OwlScope

```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## Usage

1. Open `http://localhost:5000`
2. Confirm the green "Ollama connected" badge is visible
3. Paste any GitHub issue or PR URL, e.g.:
   - `https://github.com/openfaas/python-flask-template/pull/73`
   - `https://github.com/django/django/issues/16403`
4. Click **Investigate**
5. Wait for the report — typically 15–45 seconds depending on model size
6. Expand sections using the collapsible cards
7. Use **Jump To** pill buttons to navigate between sections
8. Download the report as **Markdown** or print to **PDF**

---

## Configuration Reference

| Variable          | Default                  | Description                                                  |
|-------------------|--------------------------|--------------------------------------------------------------|
| `OLLAMA_HOST`     | `http://localhost:11434` | Ollama server URL. Supports ngrok tunnels for remote Ollama. |
| `OLLAMA_MODEL`    | `qwen2.5-coder:7b`       | Any model installed in your Ollama instance.                 |
| `GITHUB_TOKEN`    | *(empty)*                | Optional PAT. Raises rate limit to 5,000 req/hour.          |
| `FLASK_SECRET_KEY`| *(dev default)*          | Flask session secret. Change in production.                  |
| `CACHE_DIR`       | `./cache`                | Directory for cached report JSON files.                      |

---

## Error Handling

OwlScope surfaces all errors as inline banner messages — never silent failures:

| Condition                         | Message shown                                               |
|-----------------------------------|-------------------------------------------------------------|
| Invalid GitHub URL                | "Invalid GitHub URL. Expected format: …"                   |
| Issue / PR not found              | "GitHub returned 404 — resource not found"                 |
| API rate limit exceeded           | "GitHub API rate limit hit or access denied (403)"         |
| Private repo without token        | "GitHub API returned 401 — invalid token"                  |
| Ollama not reachable              | Status badge turns amber with connection error detail       |
| Model not found in Ollama         | Error surfaced from LLM client with model name             |
| Network timeout                   | "Network error calling GitHub API: …"                      |

---

## Running Tests

```bash
pytest tests/
```

---

## What OwlScope Does NOT Do

- No login, accounts, or authentication
- No database — reports are cached as local JSON files
- No multi-repo comparison
- No GitLab, Bitbucket, or self-hosted GitHub Enterprise support
- Does not clone repositories — all data fetched via GitHub API only
- Does not stream LLM output — waits for the full response before rendering

---

## License

MIT — free to use, modify, and distribute.

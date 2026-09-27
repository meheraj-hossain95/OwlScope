"""OwlScope — Flask application entry point.

Routes:
  GET  /                          Input form
  POST /analyze                   Validate URL, fetch context, generate report
  GET  /report/<cache_key>        View a generated report
  GET  /report/<cache_key>/download  Download report as Markdown
  GET  /health                    Ollama connectivity check (JSON)
  GET  /debug                     Human-readable config + connection diagnostics
"""

import os
import sys

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
)
from dotenv import load_dotenv

# Ensure OwlScope package root is on sys.path when running app.py directly
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

from config import FLASK_SECRET_KEY
import cache
import llm_client
import github_fetcher
import report_generator
from report_generator import SECTION_ORDER, SECTION_LABELS

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


# ---------------------------------------------------------------------------
# Jinja filters
# ---------------------------------------------------------------------------

import markdown as _markdown
import markupsafe


@app.template_filter("md")
def markdown_filter(text: str) -> markupsafe.Markup:
    """Render a Markdown string to safe HTML."""
    if not text:
        return markupsafe.Markup("")
    html = _markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "nl2br"],
    )
    return markupsafe.Markup(html)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def report_to_markdown(report: dict) -> str:
    """Convert a report dict to a clean Markdown document."""
    lines = []
    issue = report.get("issue", {})
    repo = report.get("repo", {})
    kind = "Pull Request" if report.get("is_pr") else "Issue"

    lines.append("# OwlScope Investigation Report")
    lines.append("")
    lines.append(f"**{kind}:** [{repo.get('full_name', '')} #{issue.get('number', '')}]({report.get('url', '')})")
    lines.append(f"**Title:** {issue.get('title', '')}")
    lines.append(f"**Generated:** {report.get('generated_at', '')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    sections = report.get("sections", {})
    for key in SECTION_ORDER:
        label = SECTION_LABELS.get(key, key)
        lines.append(f"## {label}")
        lines.append("")
        lines.append(sections.get(key, "*Not generated.*"))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    recent = cache.list_cached_reports()[:5]
    ok, _ = llm_client.check_connection()
    return render_template("index.html", recent=recent, ollama_ok=ok)


@app.route("/analyze", methods=["POST"])
def analyze():
    url = request.form.get("url", "").strip()

    if not url:
        flash("Please paste a GitHub issue or PR URL.", "error")
        return redirect(url_for("index"))

    # Validate URL format early
    try:
        github_fetcher.parse_github_url(url)
    except github_fetcher.GitHubFetchError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    # Cache hit — skip generation
    cached = cache.get_cached_report(url)
    if cached:
        key = cache.url_to_cache_key(url)
        return redirect(url_for("view_report", cache_key=key))

    # Fetch GitHub context
    try:
        context = github_fetcher.fetch_issue_context(url)
    except github_fetcher.GitHubFetchError as exc:
        flash(f"GitHub API error: {exc}", "error")
        return redirect(url_for("index"))

    # Generate report
    try:
        report = report_generator.generate_report(context, url=url)
    except Exception as exc:
        flash(f"Report generation failed: {exc}", "error")
        return redirect(url_for("index"))

    # Save to cache
    key = cache.save_report(url, report)
    return redirect(url_for("view_report", cache_key=key))


@app.route("/report/<cache_key>")
def view_report(cache_key: str):
    report = cache.get_report_by_key(cache_key)
    if not report:
        flash("Report not found. It may have been deleted.", "error")
        return redirect(url_for("index"))

    return render_template(
        "report.html",
        report=report,
        cache_key=cache_key,
        section_order=SECTION_ORDER,
        section_labels=SECTION_LABELS,
        section_icons={
            "issue_summary":   "document",
            "feature_impact":  "lightning",
            "code_impact":     "code",
            "visualization":   "graph",
            "root_cause":      "target",
            "fix_suggestions": "wrench",
            "test_generation": "check",
            "security_impact": "shield",
        },
    )


@app.route("/report/<cache_key>/download")
def download_report(cache_key: str):
    report = cache.get_report_by_key(cache_key)
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("index"))

    md_content = report_to_markdown(report)
    issue = report.get("issue", {})
    filename = (
        f"owlscope-"
        f"{report.get('repo', {}).get('full_name', 'report').replace('/', '-')}"
        f"-{issue.get('number', 'x')}.md"
    )

    return Response(
        md_content,
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/health")
def health():
    import config as cfg
    ok, reason = llm_client.check_connection()
    return jsonify({
        "status": "ok",
        "ollama": "connected" if ok else "unreachable",
        "ollama_reason": reason,
        "ollama_host": cfg.OLLAMA_HOST,
        "model": cfg.OLLAMA_MODEL,
    })


@app.route("/debug")
def debug():
    """Human-readable diagnostics page — shows config and connection status."""
    import config as cfg

    ok, reason = llm_client.check_connection()

    # Mask token if present
    token_display = ("*" * 8 + cfg.GITHUB_TOKEN[-4:]) if len(cfg.GITHUB_TOKEN) > 4 else ("(not set)" if not cfg.GITHUB_TOKEN else cfg.GITHUB_TOKEN)

    ngrok_instructions = ""
    if "403" in reason:
        ngrok_instructions = """
        <div class="fix-box">
          <strong>How to fix the 403:</strong><br>
          In your Kaggle notebook, make sure your pyngrok cell looks like this:<br>
          <pre>!pip install pyngrok
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")   # required
url = ngrok.connect(11434)
print(url)</pre>
          Then copy the printed URL (without trailing slash) into your <code>.env</code>:<br>
          <pre>OLLAMA_HOST=https://xxxx.ngrok-free.app</pre>
          Restart the Flask app after editing <code>.env</code>.
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>OwlScope Debug</title>
  <style>
    body {{ font-family: -apple-system, "Segoe UI", sans-serif; background:#0d1117; color:#e6edf3;
           max-width:760px; margin:2rem auto; padding:0 1.5rem; line-height:1.6; }}
    h1   {{ font-size:1.6rem; margin-bottom:0.25rem; }}
    h2   {{ font-size:1rem; color:#8b949e; text-transform:uppercase; letter-spacing:.06em;
           margin:1.5rem 0 .5rem; border-bottom:1px solid #30363d; padding-bottom:.4rem; }}
    table {{ width:100%; border-collapse:collapse; font-size:.9rem; margin:.5rem 0; }}
    td,th {{ padding:.5rem .75rem; border:1px solid #30363d; text-align:left; }}
    th    {{ background:#21262d; width:35%; }}
    .ok   {{ color:#3fb950; font-weight:700; }}
    .err  {{ color:#f85149; font-weight:700; }}
    pre   {{ background:#21262d; border:1px solid #30363d; border-radius:6px;
            padding:.75rem 1rem; overflow-x:auto; font-size:.85rem; }}
    .fix-box {{ background:rgba(248,81,73,.1); border:1px solid rgba(248,81,73,.4);
               border-radius:8px; padding:1rem; margin:1rem 0; }}
    a     {{ color:#58a6ff; }}
    .back {{ display:inline-block; margin-top:1.5rem; color:#8b949e; }}
  </style>
</head>
<body>
  <h1>🦉 OwlScope — Debug & Diagnostics</h1>
  <p style="color:#8b949e">This page shows live configuration and connection status.</p>

  <h2>Configuration</h2>
  <table>
    <tr><th>OLLAMA_HOST</th><td><code>{cfg.OLLAMA_HOST}</code></td></tr>
    <tr><th>OLLAMA_MODEL</th><td><code>{cfg.OLLAMA_MODEL}</code></td></tr>
    <tr><th>GITHUB_TOKEN</th><td>{token_display}</td></tr>
    <tr><th>CACHE_DIR</th><td><code>{cfg.CACHE_DIR}</code></td></tr>
    <tr><th>.env file</th><td><code>{os.path.join(os.path.dirname(__file__), '.env')}</code></td></tr>
    <tr><th>.env exists?</th><td>{"✅ yes" if os.path.exists(os.path.join(os.path.dirname(__file__), '.env')) else "❌ NO — create it from .env.example"}</td></tr>
  </table>

  <h2>Ollama Connection</h2>
  <table>
    <tr><th>Status</th>
        <td class="{'ok' if ok else 'err'}">{'✅ Connected' if ok else '❌ Unreachable'}</td></tr>
    <tr><th>Detail</th><td>{reason}</td></tr>
    <tr><th>Test URL</th><td><code>{cfg.OLLAMA_HOST}/api/tags</code></td></tr>
  </table>

  {ngrok_instructions}

  <h2>Quick Fix Checklist</h2>
  <ol>
    <li>Make sure <code>OwlScope/.env</code> exists (copy from <code>.env.example</code>)</li>
    <li>Set <code>OLLAMA_HOST=https://your-ngrok-url.ngrok-free.app</code> (no trailing slash, no spaces around =)</li>
    <li>Confirm Ollama is running in Kaggle: <code>!ollama serve &</code> and the pyngrok tunnel is active</li>
    <li>Restart Flask: <kbd>Ctrl+C</kbd> then <code>python app.py</code></li>
    <li>Refresh this page to re-check</li>
  </ol>

  <a class="back" href="/">← Back to OwlScope</a>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cache._ensure_cache_dir()
    app.run(debug=True, host="0.0.0.0", port=5000)

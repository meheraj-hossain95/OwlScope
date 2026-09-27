# OwlScope — How to Start

**GitHub Issue Investigator** · Flask + Ollama (local or Ngrok tunnel)

---

## Prerequisites

- Python 3.10+
- Ollama running locally **or** a Ngrok tunnel URL pointing at a remote Ollama instance

---

## 1. Install dependencies

```bash
cd OwlScope
pip install -r requirements.txt
```

---

## 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your values:

| Variable | Required | What to put |
|---|---|---|
| `OLLAMA_HOST` | **Yes** | `http://localhost:11434` for local Ollama, or your Ngrok URL e.g. `https://crop-humid-reason.ngrok-free.app` — **no trailing slash** |
| `OLLAMA_MODEL` | **Yes** | Model name loaded in Ollama, e.g. `qwen2.5-coder:7b` or `llama3` |
| `GITHUB_TOKEN` | No | Leave blank for public repos (60 req/hr). Add a [GitHub PAT](https://github.com/settings/tokens) for 5000 req/hr. No scopes needed for public repos. |
| `FLASK_SECRET_KEY` | No | Any long random string. Defaults to a dev key. |
| `CACHE_DIR` | No | Where to store cached reports. Defaults to `cache/` inside `OwlScope/`. |

---

## 3. Run the app

```bash
cd OwlScope
python app.py
```

Open your browser at **http://localhost:5000**

---

## 4. Use it

1. Paste any public GitHub issue or pull request URL into the input box
2. Click **Investigate**
3. Wait for the report to generate (one LLM call per section — takes ~1–3 min depending on model)
4. View the 8-section report in the browser
5. Click **Download Markdown** to save the report as a `.md` file

Reports are cached — re-visiting the same URL is instant.

---

## 5. Check Ollama connectivity

```
GET http://localhost:5000/health
```

Returns JSON with `ollama: "connected"` or `"unreachable"`. Useful when debugging Ngrok tunnels.

---

## 6. Run tests

```bash
cd OwlScope
python -m pytest tests/ -v
```

All 64 tests run without a live GitHub or Ollama connection (fully mocked).

---

## File layout

```
OwlScope/
├── app.py               ← Flask app entry point
├── config.py            ← All env vars
├── github_fetcher.py    ← GitHub REST API calls
├── llm_client.py        ← Ollama HTTP client
├── report_generator.py  ← 8-section LLM report generation
├── cache.py             ← JSON file cache
├── context_builder.py   ← Context serialisation helpers
├── templates/           ← Jinja2 HTML templates
├── static/              ← CSS + icon
├── tests/               ← pytest test suite
├── requirements.txt
└── .env.example         ← Copy to .env and fill in
```

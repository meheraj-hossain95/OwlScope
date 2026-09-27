"""Ollama HTTP client for OwlScope.

Communicates with an Ollama instance (local or via Ngrok tunnel).

Ngrok free tunnels: we send `ngrok-skip-browser-warning: true` on every
request to bypass the HTML interstitial page.

If your Ngrok tunnel returns 403, the tunnel was started without allowing
anonymous access.  In your Kaggle notebook make sure you run:
    from pyngrok import ngrok
    ngrok.set_auth_token("YOUR_TOKEN")
    url = ngrok.connect(11434, bind_tls=True)
"""

import requests

from config import OLLAMA_HOST, OLLAMA_MODEL


class LLMError(Exception):
    """Raised when the Ollama API is unreachable or returns an error."""


def _headers() -> dict:
    """Headers sent on every Ollama request.

    ngrok-skip-browser-warning bypasses the Ngrok interstitial page.
    It is a no-op for non-Ngrok hosts.
    """
    return {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "OwlScope/1.0",
    }


def check_connection() -> tuple[bool, str]:
    """Check if the Ollama instance is reachable.

    Returns:
        (True, "ok") if reachable and Ollama responds correctly.
        (False, reason_string) if not reachable, with a human-readable reason.
    """
    try:
        resp = requests.get(
            f"{OLLAMA_HOST}/api/tags",
            headers=_headers(),
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return False, f"Connection refused — cannot reach {OLLAMA_HOST}"
    except requests.exceptions.Timeout:
        return False, f"Timeout — {OLLAMA_HOST} did not respond within 10s"
    except requests.exceptions.RequestException as exc:
        return False, f"Network error: {exc}"

    if resp.status_code == 403:
        return False, (
            "403 Forbidden — Ngrok tunnel requires auth. "
            "In your Kaggle notebook add: ngrok.set_auth_token('TOKEN') "
            "before ngrok.connect(11434)"
        )
    if resp.status_code == 404:
        return False, f"404 — {OLLAMA_HOST} is reachable but /api/tags not found. Is Ollama running?"
    if not resp.ok:
        return False, f"HTTP {resp.status_code} — {resp.text[:120]}"

    # Verify it looks like an Ollama response
    try:
        data = resp.json()
        if "models" not in data and "error" not in data:
            return False, f"Unexpected response from {OLLAMA_HOST} — not an Ollama server?"
    except Exception:
        return False, "Response was not valid JSON — not an Ollama server?"

    return True, "ok"


def generate(prompt: str, system: str = None) -> str:
    """Send a prompt to Ollama and return the completion text.

    Args:
        prompt: The user prompt to send.
        system: Optional system message to prepend as context.

    Returns:
        The model's response as a plain string.

    Raises:
        LLMError: If the request fails or Ollama returns an error body.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            headers=_headers(),
            timeout=180,
        )
    except requests.exceptions.ConnectionError as exc:
        raise LLMError(
            f"Cannot reach Ollama at {OLLAMA_HOST}. "
            "Is Ollama running? Check /debug for diagnostics."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise LLMError("Ollama request timed out after 180 seconds.") from exc
    except requests.exceptions.RequestException as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc

    if resp.status_code == 403:
        raise LLMError(
            "403 Forbidden from Ngrok — tunnel requires auth. "
            "See /debug for instructions."
        )
    if not resp.ok:
        raise LLMError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except Exception:
        raise LLMError(f"Ollama response was not valid JSON: {resp.text[:200]}")

    if "error" in data:
        raise LLMError(f"Ollama error: {data['error']}")

    return data.get("response", "").strip()

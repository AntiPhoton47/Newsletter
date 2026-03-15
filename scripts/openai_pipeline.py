#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
REQUEST_TIMEOUT = 60


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def ai_enabled() -> bool:
    load_env_file()
    if not env_flag("NEWSLETTER_USE_AI", default=True):
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))


def require_ai() -> bool:
    load_env_file()
    return env_flag("NEWSLETTER_REQUIRE_AI", default=False)


def review_min_score() -> int:
    load_env_file()
    raw = os.environ.get("NEWSLETTER_AI_REVIEW_MIN_SCORE", "85").strip()
    try:
        return int(raw)
    except ValueError:
        return 85


def base_url() -> str:
    load_env_file()
    return os.environ.get("NEWSLETTER_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def draft_model() -> str:
    load_env_file()
    return os.environ.get("NEWSLETTER_OPENAI_DRAFT_MODEL", "gpt-4.1-mini").strip()


def review_model() -> str:
    load_env_file()
    return os.environ.get("NEWSLETTER_OPENAI_REVIEW_MODEL", "gpt-4.1-mini").strip()


def _request(url: str, payload: dict) -> dict:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc
    except Exception:
        insecure_context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=insecure_context) as response:
            return json.loads(response.read().decode("utf-8"))


def _extract_responses_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    outputs = data.get("output", [])
    for item in outputs:
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise RuntimeError("No text output returned from Responses API")


def _extract_chat_text(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices returned from Chat Completions API")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "".join(parts)
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise RuntimeError("No text output returned from Chat Completions API")


def call_openai_text(prompt: str, model: str) -> str:
    responses_payload = {
        "model": model,
        "input": prompt,
    }
    try:
        data = _request(f"{base_url()}/responses", responses_payload)
        return _extract_responses_text(data)
    except Exception:
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        data = _request(f"{base_url()}/chat/completions", chat_payload)
        return _extract_chat_text(data)


def call_openai_json(prompt: str, model: str) -> dict:
    responses_payload = {
        "model": model,
        "input": prompt + "\n\nReturn valid JSON only.",
        "text": {
            "format": {
                "type": "json_object",
            }
        },
    }
    try:
        data = _request(f"{base_url()}/responses", responses_payload)
        return json.loads(_extract_responses_text(data))
    except Exception:
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt + "\n\nReturn valid JSON only."},
            ],
            "response_format": {"type": "json_object"},
        }
        data = _request(f"{base_url()}/chat/completions", chat_payload)
        return json.loads(_extract_chat_text(data))

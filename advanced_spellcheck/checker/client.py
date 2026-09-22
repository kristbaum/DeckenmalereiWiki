"""OpenRouter access: credentials, requests, retries, response parsing."""

import json
import os
import random
import re
import threading
import time

import requests

from checker.config import (
    ENV_FILE,
    FALLBACK_PRICES,
    OPENROUTER_MODELS_URL,
    OPENROUTER_URL,
)

# --------------------------------------------------------------------------
# OpenRouter client
# --------------------------------------------------------------------------


def read_api_key() -> str | None:
    """The OpenRouter key, from the environment or a git-ignored .env file."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    if not ENV_FILE.exists():
        return None
    # Tolerant of the shapes a key file actually arrives in: surrounding
    # quotes on either side of the "=", "export " prefixes, no trailing
    # newline, or a file holding nothing but the key.
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip().strip("\"'")
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if not sep:
            if line.startswith("sk-"):
                return line
            continue
        if name.strip().strip("\"'") == "OPENROUTER_API_KEY":
            return value.strip().strip("\"'") or None
    return None


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    """Minimal OpenRouter chat client with retries and backoff."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        max_retries: int = 5,
        timeout: int = 180,
        echo: bool = False,
    ):
        self.api_key = api_key
        self.model = model
        # When set, every prompt and every raw answer is printed. Only useful
        # with one worker, otherwise the output of parallel calls interleaves.
        self.echo = echo
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._lock = threading.Lock()

    def complete(self, system: str, user: str, *, max_tokens: int, reasoning: str | None) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Determinism: the same text must produce the same findings so two
            # runs (or two models) can be compared.
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if reasoning:
            payload["reasoning"] = {"effort": reasoning}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "DeckenmalereiWiki advanced spellcheck",
        }

        last_error = ""
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    OPENROUTER_URL, headers=headers, json=payload, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                self._sleep(attempt, None)
                continue

            if response.status_code == 200:
                data = response.json()
                if self.echo:
                    self._echo(user, data)
                usage = data.get("usage") or {}
                with self._lock:
                    self.prompt_tokens += usage.get("prompt_tokens", 0)
                    self.completion_tokens += usage.get("completion_tokens", 0)
                choices = data.get("choices") or []
                if not choices:
                    raise OpenRouterError(f"no choices in response: {data}")
                return choices[0].get("message", {}).get("content") or ""

            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if (
                response.status_code in (400, 404, 422)
                and "response_format" in payload
                and "response_format" in response.text
            ):
                # The model or the provider it routed to does not support JSON
                # mode; the prompt already demands JSON, so drop the hint.
                payload.pop("response_format")
                continue
            if response.status_code in (408, 429, 500, 502, 503, 504):
                self._sleep(attempt, response.headers.get("Retry-After"))
                continue
            raise OpenRouterError(last_error)

        raise OpenRouterError(f"giving up after {self.max_retries} attempts - {last_error}")

    def _echo(self, user: str, data: dict) -> None:
        """Print the prompt and the untouched answer, for judging a pilot."""
        message = (data.get("choices") or [{}])[0].get("message", {})
        usage = data.get("usage") or {}
        with self._lock:
            print("\n" + "=" * 78)
            print(f"PROMPT  ({self.model})")
            print("=" * 78)
            print(user)
            reasoning = message.get("reasoning")
            if reasoning:
                print("-" * 78)
                print("REASONING")
                print("-" * 78)
                print(reasoning.strip()[:2000])
            print("-" * 78)
            print(
                f"ANSWER  ({usage.get('prompt_tokens', '?')} in / "
                f"{usage.get('completion_tokens', '?')} out)"
            )
            print("-" * 78)
            print((message.get("content") or "").strip())
            print("=" * 78 + "\n")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 60))
                return
            except ValueError:
                pass
        time.sleep(min(2**attempt, 60) + random.random())


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_findings(raw: str) -> list[dict]:
    """Extract the findings list from a model response.

    Models wrap JSON in prose or code fences often enough that this has to be
    forgiving; an unparseable response costs one chunk, not the run.
    """
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    findings = data.get("funde") if isinstance(data, dict) else data
    if not isinstance(findings, list):
        return []
    return [f for f in findings if isinstance(f, dict) and f.get("zitat")]


# --------------------------------------------------------------------------
# Cost estimate
# --------------------------------------------------------------------------


def fetch_prices(model: str) -> tuple[float, float]:
    """Live prices in USD per million tokens, with a hardcoded fallback."""
    try:
        response = requests.get(OPENROUTER_MODELS_URL, timeout=30)
        response.raise_for_status()
        for entry in response.json()["data"]:
            if entry["id"] == model:
                pricing = entry.get("pricing", {})
                return (
                    float(pricing.get("prompt", 0)) * 1e6,
                    float(pricing.get("completion", 0)) * 1e6,
                )
    except (requests.RequestException, KeyError, ValueError, TypeError):
        pass
    return FALLBACK_PRICES.get(model, (0.0, 0.0))

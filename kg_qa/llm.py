"""
llm.py | one small client for any OpenAI-compatible chat-completions endpoint.

Works with OpenAI, Groq, OpenRouter, Google Gemini (OpenAI-compatible endpoint), and local servers such as Ollama or LM Studio.
Configuration comes from environment variables (copy .env.example to .env); no key is stored in the code.
    LLM_BASE_URL   e.g. https://generativelanguage.googleapis.com/v1beta/openai   or  http://localhost:11434/v1
    LLM_MODEL      model name understood by that endpoint
    LLM_API_KEY    key (may be empty for a local server)
The same client and the same settings (temperature 0) are used for the LLM-only and the KG-grounded condition.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_dotenv(root: Path):
    f = root / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.0, max_tokens: int = 500, timeout: int = 90):
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.temperature, self.max_tokens, self.timeout = temperature, max_tokens, timeout

    @classmethod
    def from_env(cls, root: Path | None = None):
        root = root or Path(__file__).resolve().parent.parent
        load_dotenv(root)
        base, model = os.environ.get("LLM_BASE_URL"), os.environ.get("LLM_MODEL")
        if not base or not model:
            return None
        return cls(base, model, os.environ.get("LLM_API_KEY", ""), float(os.environ.get("LLM_TEMPERATURE", "0")),
                   int(os.environ.get("LLM_MAX_TOKENS", "500")))

    @property
    def name(self) -> str:
        return f"{self.model} @ {self.base_url}"

    def chat(self, system: str, user: str) -> str:
        body = json.dumps({"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "licensegraph-pypi/1.0 (coursework)"}   # some providers (Cloudflare) reject the default Python user agent with 403 / error 1010
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body, headers=headers, method="POST")
        last = None
        for attempt in range(4):                       # free tiers rate-limit; back off and retry
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return (data["choices"][0]["message"]["content"] or "").strip()
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                if e.code not in (429, 500, 502, 503):
                    break
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last = repr(e)
            time.sleep(2 ** attempt * 2)
        raise LLMError(f"LLM call failed: {last}")

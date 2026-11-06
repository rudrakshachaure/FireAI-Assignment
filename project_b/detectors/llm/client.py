
"""Gemini wrapper: JSON-schema output, on-disk response cache,
backoff on 429, token logging, and graceful handling of invalid API keys.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from common import CACHE_DIR, GEMINI_MODEL, OUT_DIR


class RowVerdict(BaseModel):
    flag: bool
    reason: str


class BatchVerdict(BaseModel):
    flag: bool
    reason: str
    bad_rows: list[int]


@dataclass
class CallResult:
    text: str
    in_tokens: int
    out_tokens: int
    cached: bool


class LLMClient:
    def __init__(
        self,
        model: str = GEMINI_MODEL,
        call_fn: Callable | None = None,
        rpm: int | None = None
    ):
        self.model = model
        self.call_fn = call_fn
        self.rpm = rpm or int(os.getenv("LLM_RPM", "10"))
        self.disabled = False
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def ask(self, prompt: str, schema: type[BaseModel]) -> CallResult | None:
        """Returns None if Gemini is unavailable and no cached answer exists."""

        key = hashlib.sha256(
            f"{self.model}|{schema.__name__}|{prompt}".encode()
        ).hexdigest()

        path = CACHE_DIR / f"{key}.json"

        # Always prefer an existing cached answer.
        if path.exists():
            d = json.loads(path.read_text())
            return CallResult(d["text"], d["in"], d["out"], cached=True)

        # No API key: skip without crashing.
        if self.call_fn is None:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if not api_key or self.disabled:
                return None

        try:
            text, tin, tout = self._call_with_backoff(prompt, schema)

        except Exception as e:
            message = str(e).upper()

            # Invalid key or authentication failure:
            # disable further Gemini requests for this run.
            if any(term in message for term in (
                "API_KEY_INVALID",
                "API KEY NOT VALID",
                "INVALID API KEY",
                "UNAUTHENTICATED",
                "PERMISSION_DENIED",
                "401",
            )):
                print(
                    "Gemini authentication failed. "
                    "Skipping remaining uncached LLM requests."
                )
                self.disabled = True
                return None

            # Other errors should remain visible.
            raise

        path.write_text(
            json.dumps({"text": text, "in": tin, "out": tout})
        )

        OUT_DIR.mkdir(parents=True, exist_ok=True)

        with open(OUT_DIR / "llm_tokens.jsonl", "a") as f:
            f.write(
                json.dumps({
                    "model": self.model,
                    "in": tin,
                    "out": tout,
                    "t": time.time()
                }) + "\n"
            )

        if self.call_fn is None:
            time.sleep(60 / self.rpm)

        return CallResult(text, tin, tout, cached=False)

    def _call_with_backoff(self, prompt: str, schema: type[BaseModel]):
        for attempt in range(7):
            try:
                return (self.call_fn or self._gemini)(prompt, schema)

            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(min(90, 5 * 2 ** attempt))
                    continue
                raise

        raise RuntimeError("Gemini still rate-limited after 7 retries")

    def _gemini(self, prompt: str, schema: type[BaseModel]):
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"].strip()
        )

        resp = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0
            )
        )

        u = resp.usage_metadata
        out = (
            (u.candidates_token_count or 0)
            + (getattr(u, "thoughts_token_count", 0) or 0)
        )

        return resp.text, (u.prompt_token_count or 0), out

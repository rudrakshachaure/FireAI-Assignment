"""Gemini wrapper: disk cache, 429 backoff, token log.

Cache key = sha256(model, temperature, system, schema name, rule-text hash, prompt).
The rule-text hash is an explicit component, so changing a rule can never hit a
stale entry (tests/test_llm_cache.py proves it). Set use_cache=False for the
determinism experiment only."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

from .models import RuleError

CACHE_DIR = Path(os.environ.get("LLM_CACHE_DIR", ".cache/llm"))
TOKEN_LOG = Path(os.environ.get("LLM_TOKEN_LOG", ".cache/token_log.csv"))
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # TODO-VERIFY current free-tier model + limits
_rng = random.Random(0)
_calls: list["LLMResult"] = []


@dataclass
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int
    latency_s: float          # latency of the ORIGINAL call (also when served from cache)
    from_cache: bool
    key: str


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(model: str, system: str, prompt: str, schema_name: str, rule_hash: str, temperature: float = 0.0) -> str:
    return sha(json.dumps([model, temperature, system, schema_name, rule_hash, prompt]))


def drain_calls() -> list[LLMResult]:
    """Calls made since the last drain (eval uses this for per-request latency/tokens)."""
    out = _calls[:]
    _calls.clear()
    return out


def _log(model: str, r: LLMResult) -> None:
    TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not TOKEN_LOG.exists()
    with open(TOKEN_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "model", "key12", "tokens_in", "tokens_out", "latency_s", "cached"])
        w.writerow([int(time.time()), model, r.key[:12], r.tokens_in, r.tokens_out, round(r.latency_s, 3), r.from_cache])


def generate_json(prompt: str, *, schema, system: str = "", rule_text: str = "", model: str | None = None,
                  use_cache: bool = True, max_retries: int = 6) -> LLMResult:
    model = model or DEFAULT_MODEL
    key = cache_key(model, system, prompt, schema.__name__, sha(rule_text))
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        r = LLMResult(d["text"], d["tokens_in"], d["tokens_out"], d["latency_s"], True, key)
        _calls.append(r)
        _log(model, r)
        return r

    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as e:  # LOUD
        raise RuleError("google-genai not installed (pip install -r requirements.txt)") from e
    if "GEMINI_API_KEY" not in os.environ:
        raise RuleError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(system_instruction=system or None, temperature=0.0, seed=0,
                                         response_mime_type="application/json", response_schema=schema)
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            break
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if attempt == max_retries or not (code == 429 or (code or 0) >= 500):
                raise
            time.sleep(min(60.0, 2.0 ** attempt + _rng.random()))
    latency = time.perf_counter() - t0
    um = resp.usage_metadata
    r = LLMResult(resp.text or "", getattr(um, "prompt_token_count", 0) or 0,
                  getattr(um, "candidates_token_count", 0) or 0, latency, False, key)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"text": r.text, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                                "latency_s": r.latency_s, "model": model}), encoding="utf-8")
    _calls.append(r)
    _log(model, r)
    return r

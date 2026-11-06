"""Cache key must change when the rule text changes (stale-cache guard)."""
from __future__ import annotations

from project_a.llm_client import cache_key, sha


def test_rule_hash_is_part_of_key() -> None:
    a = cache_key("m", "sys", "prompt", "TaxOutput", sha("rules v1"))
    b = cache_key("m", "sys", "prompt", "TaxOutput", sha("rules v2"))
    assert a != b
    assert a == cache_key("m", "sys", "prompt", "TaxOutput", sha("rules v1"))
    assert a != cache_key("m2", "sys", "prompt", "TaxOutput", sha("rules v1"))

import json
from pathlib import Path

p = Path("project_a/impl_c_llm_compiled/frozen/rules_fy2024-25.json")
d = json.loads(p.read_text(encoding="utf-8"))

print("BEFORE old:", [(s["age_band"], [(x["upto"], x["rate_pct"]) for x in s["slabs"]]) for s in d["old"]["slab_sets"]])
print("BEFORE new:", [s["age_band"] for s in d["new"]["slab_sets"]])

def slabs(*pairs):
    return [{"upto": u, "rate_pct": r} for u, r in pairs]

d["old"]["slab_sets"] = [
    {"age_band": "<60",   "slabs": slabs((250000, 0), (500000, 5), (1000000, 20), (None, 30))},
    {"age_band": "60-79", "slabs": slabs((300000, 0), (500000, 5), (1000000, 20), (None, 30))},
    {"age_band": "80+",   "slabs": slabs((500000, 0), (1000000, 20), (None, 30))},
]
for s in d["new"]["slab_sets"]:
    s["age_band"] = "all"

p.write_text(json.dumps(d, indent=2), encoding="utf-8")
print("fixed")
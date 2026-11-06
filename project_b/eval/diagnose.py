"""Which chosen detector causes the false alarms, and where is recall weak?"""
import json
import pandas as pd
from common import OUT_DIR

m = pd.read_csv(OUT_DIR / "master_all.csv")
plan = json.load(open(OUT_DIR / "hybrid_plan.json"))
m5 = m[m.rate == 0.05]
chosen = pd.DataFrame([m5[(m5.problem_type == p) & (m5.family == f)].iloc[0] for p, f in plan.items()])
cols = ["problem_type", "family", "recall", "precision", "fa_per_m_rows", "fa_unit", "errors"]
print(chosen[cols].round(3).to_string(index=False))
print("\nrecall < 0.5 (any cheap detector):")
print(m[(m.family != "llm") & (m.recall < 0.5)][["problem_type", "family", "rate", "recall"]].round(3).to_string(index=False))
print("\ndetectors that crashed:")
print(m[m.errors > 0][["problem_type", "family", "errors"]].drop_duplicates().to_string(index=False))
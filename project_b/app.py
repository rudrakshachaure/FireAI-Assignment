"""Simple dashboard for Project B.   Run:  streamlit run app.py
It only READS the files that `make all` wrote to eval/out/ (plus a live demo tab)."""
import json

import pandas as pd
import streamlit as st

from common import BATCH_LEVEL, OUT_DIR, PROBLEMS, PROFILE_OUT

st.set_page_config(page_title="Rules vs LLMs: data quality", layout="wide")


def load_csv(name):
    p = OUT_DIR / name
    return pd.read_csv(p) if p.exists() else None


master, per_type = load_csv("master_all.csv"), load_csv("hybrid_per_type.csv")
ablation, samples = load_csv("hybrid_ablation.csv"), load_csv("hybrid_sample_alerts.csv")
scale, llm = load_csv("scale.csv"), load_csv("llm_results.csv")

st.title("Rules vs LLMs")
st.caption("NYC 311 requests, 2023. 12 kinds of data problems, 3 ways to catch them, 1 hybrid pipeline.")
if master is None:
    st.error("No results yet. Run `make all` first, then reload this page.")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Summary", "Which detector wins?", "Hybrid pipeline", "At scale", "Try it live"])

# ---------------- 1. Summary ----------------
with tab1:
    st.subheader("Hybrid pipeline in one glance")
    if ablation is not None:
        row = ablation.set_index("config").loc["hybrid_with_llm"]
        c = st.columns(4)
        c[0].metric("Problems caught (recall)", f"{row.macro_recall:.0%}", help="Share of injected bad rows that were found")
        c[1].metric("Alerts that were real (precision)", f"{row.macro_precision:.0%}", help="Share of alerts that pointed at a truly bad row")
        c[2].metric("False alarms / million clean rows", f"{row.clean_fa_rows_per_m:,.0f}", help="Lower is better")
        c[3].metric("Cost per million rows", f"${row.total_usd_per_m:.4f}", help="Compute + LLM at list price")
        if row.llm_calls == 0:
            st.warning("The LLM did not run (no Gemini key or cache), so these numbers are the cheap checks only.")
    st.markdown("""
**How to read this app**
- **Rules** = fixed checks (formats, allowed values, duplicates). Cheap and explainable.
- **Stats** = learned from clean data (outliers, text classifiers). Cheap, a bit fuzzier.
- **LLM** = Gemini reads rows. Flexible, but costs money and is slower.
- **Hybrid** = cheap checks on every row, and the LLM only where it clearly helps.
""")
    p = PROFILE_OUT / "real_issues.csv"
    if p.exists():
        st.subheader("Real problems found in the raw 2023 data (top 10)")
        st.dataframe(pd.read_csv(p).head(10)[["issue", "count", "pct", "proposed_check_family"]], hide_index=True,
                     use_container_width=True)

# ---------------- 2. Detectors compared ----------------
with tab2:
    rate = st.select_slider("Share of rows corrupted", options=sorted(master.rate.unique()), value=0.05,
                            format_func=lambda r: f"{r:.1%}")
    m = master[master.rate == rate] if (master.rate == rate).any() else master[master.rate == 0.05]
    st.caption("LLM numbers exist only at 5% (they come from a small sample). Batch-level problems "
               "(schema_column, type_change, null_spike) count a whole batch as one hit.")
    recall = m.pivot_table(index="problem_type", columns="family", values="recall", aggfunc="max").reindex(PROBLEMS)
    st.subheader("Detection rate (recall): higher is better")
    st.dataframe(recall.style.format("{:.0%}", na_rep="n/a").background_gradient(cmap="Greens", vmin=0, vmax=1),
                 use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.subheader("False alarms per million clean rows")
        fa = m.pivot_table(index="problem_type", columns="family", values="fa_per_m_rows", aggfunc="max").reindex(PROBLEMS)
        st.dataframe(fa.style.format("{:,.0f}", na_rep="n/a"), use_container_width=True)
    with b:
        st.subheader("Cost per million rows (USD)")
        cost = m.pivot_table(index="problem_type", columns="family", values="total_usd_per_m", aggfunc="max").reindex(PROBLEMS)
        st.dataframe(cost.style.format("{:,.4f}", na_rep="n/a"), use_container_width=True)
    if llm is None or not (llm.status == "ok").any():
        st.info("LLM columns are empty because the LLM evaluation has not run yet (`make llm` with GEMINI_API_KEY set).")
    st.image(str(OUT_DIR / "heatmap.png")) if (OUT_DIR / "heatmap.png").exists() else None

# ---------------- 3. Hybrid ----------------
with tab3:
    plan = OUT_DIR / "hybrid_plan.csv"
    if per_type is not None:
        st.subheader("Results per problem type (mixed stream, all 12 types + clean batches)")
        st.dataframe(per_type.round(3), hide_index=True, use_container_width=True)
    if ablation is not None:
        st.subheader("Does the LLM earn its cost?")
        keep = ["config", "macro_recall", "macro_precision", "macro_f1", "clean_fa_rows_per_m", "llm_calls",
                "total_usd_per_m", "wall_seconds"]
        st.dataframe(ablation[keep].round(4), hide_index=True, use_container_width=True)
        gain = ablation.macro_f1.iloc[1] - ablation.macro_f1.iloc[0]
        st.write(f"**Quality gained by adding the LLM (F1): {gain:+.3f}** at "
                 f"${ablation.total_usd_per_m.iloc[1] - ablation.total_usd_per_m.iloc[0]:.4f} extra per million rows.")
    if plan.exists():
        st.subheader("Which detector the hybrid uses for each problem")
        st.dataframe(pd.read_csv(plan).round(3), hide_index=True, use_container_width=True)
    if samples is not None and len(samples):
        st.subheader("10 example alerts")
        st.dataframe(samples, hide_index=True, use_container_width=True)

# ---------------- 4. Scale ----------------
with tab4:
    if scale is None:
        st.info("No scale table yet.")
    else:
        st.subheader("50M rows/day across 120 customers")
        s = scale.copy()
        s["value"] = s["value"].map(lambda v: f"{v:,.4g}" if pd.notna(v) else "n/a")
        st.dataframe(s, hide_index=True, use_container_width=True)
        st.caption("Assumptions (peak factor, utilisation, CPU price) are listed in the last column and in eval/scale.py.")

# ---------------- 5. Try it live ----------------
with tab5:
    st.write("Pick a problem, corrupt a real clean batch, and watch the cheap detectors react.")
    c = st.columns(3)
    ptype = c[0].selectbox("Problem type", PROBLEMS)
    rate = c[1].select_slider("Rows corrupted", [0.001, 0.01, 0.05, 0.2], value=0.05, format_func=lambda r: f"{r:.1%}")
    seed = c[2].number_input("Random seed", 0, 10_000, 1)

    @st.cache_resource
    def get_stuff():
        from common import load_batches
        from detectors.reference import get_reference
        from injector import build_context
        ref, held = get_reference(), load_batches("heldout")
        return ref, held, build_context(pd.concat(load_batches("reference"), ignore_index=True))

    if st.button("Corrupt and detect"):
        from detectors.registry import DETECTORS
        from eval.metrics import flagged_rows, safe_run
        from injector import inject
        ref, held, ctx = get_stuff()
        bad, truth = inject(held[0], ptype, rate, int(seed), ctx)
        st.write(f"Injected **{ptype}**: " + ("whole-batch problem" if truth.row_ids is None else f"{len(truth.row_ids)} rows changed"))
        if truth.row_ids:
            st.caption("A few corrupted rows:")
            st.dataframe(bad.iloc[truth.row_ids[:5]], use_container_width=True)
        rows = []
        for fam in ("rules", "stats"):
            alerts, err = safe_run(DETECTORS[fam][ptype], bad, ref)
            if ptype in BATCH_LEVEL:
                rows.append({"detector": fam, "caught": "yes" if alerts else "NO", "alerts": len(alerts)})
            else:
                f, t = flagged_rows(alerts), set(truth.row_ids)
                rows.append({"detector": fam, "rows flagged": len(f), "real problems caught": len(f & t),
                             "recall": round(len(f & t) / len(t), 2), "precision": round(len(f & t) / len(f), 2) if f else 0.0})
            for a in alerts[:3]:
                st.write(f"**{fam}** says: {a.explanation}")
            if err:
                st.error(f"{fam} crashed: {err}")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
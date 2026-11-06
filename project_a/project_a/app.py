"""Simple Streamlit front end. From the repo root:  streamlit run project_a/app.py
Describe yourself in a sentence -> get one clear answer. Details are tucked away."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets `streamlit run project_a/app.py` import project_a

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from project_a.models import Deductions, RuleError, TaxInput, TaxOutput  # noqa: E402
from project_a.trace import check_trace  # noqa: E402

FROZEN = Path(__file__).parent / "impl_c_llm_compiled" / "frozen"
ENGINES = {"Hand-coded rules (default)": "a", "LLM-compiled rules": "c", "LLM does the maths (slow, often wrong)": "b"}

st.set_page_config(page_title="Old vs new tax regime", page_icon="🧾", layout="centered")


def inr(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def get_engine(code: str):
    if code == "a":
        from project_a.impl_a_rules import compute
    elif code == "b":
        from project_a.impl_b_llm_runtime import compute
    else:
        from project_a.impl_c_llm_compiled import compute
    return compute


def show_result(out: TaxOutput) -> None:
    o, n = out.old, out.new
    better, worse = (o, n) if out.recommended_regime == "old" else (n, o)
    saving = worse.total_tax - better.total_tax
    if saving > 0:
        st.success(f"### Choose the **{out.recommended_regime.upper()}** regime\nYou pay {inr(better.total_tax)} instead of "
                   f"{inr(worse.total_tax)}, so you save **{inr(saving)}** a year.")
    else:
        st.info(f"### Both regimes cost the same: {inr(o.total_tax)}\nChoose the new regime (simpler, no paperwork).")
    c1, c2 = st.columns(2)
    c1.metric("Old regime", inr(o.total_tax))
    c2.metric("New regime", inr(n.total_tax))

    def row(label: str, f) -> dict:
        return {"": label, "Old": inr(f(o)), "New": inr(f(n))}

    st.dataframe(pd.DataFrame([
        row("Taxable income", lambda r: r.taxable_income),
        row("Tax on it (after rebate)", lambda r: r.slab_tax - r.rebate + r.surcharge - r.marginal_relief),
        row("Cess (4%)", lambda r: r.cess),
        row("Total tax (rounded to ₹10)", lambda r: r.total_tax)]), hide_index=True)

    with st.expander("How was this calculated?"):
        tabs = st.tabs(["Old regime", "New regime"])
        for tab, res in zip(tabs, (o, n), strict=True):
            with tab:
                st.dataframe(pd.DataFrame([{"Step": t.label, "Amount": inr(t.amount), "Rule": t.clause_id} for t in res.trace]),
                             hide_index=True)
                st.caption("✅ Steps add up to the total" if not check_trace(res) else "⚠️ " + "; ".join(check_trace(res)))


def run_engine(inp: TaxInput, code: str) -> None:
    try:
        with st.spinner("Calculating..."):
            out = get_engine(code)(inp)
    except RuleError as e:
        st.error(f"Could not calculate: {e}")
        return
    show_result(out)


# ---------- engine choice (hidden by default) ----------
engine = "a"
with st.sidebar:
    with st.expander("Advanced"):
        engine = ENGINES[st.selectbox("Calculation engine", list(ENGINES))]
        if engine == "c" and not list(FROZEN.glob("rules_fy*.json")):
            st.error("No reviewed compiled rules yet. Use the default engine.")
    st.caption("Salaried, resident, FY 2024-25. Salary income only. An estimate: check the official Income Tax calculator.")

st.title("🧾 Old or new tax regime?")
st.caption("Tell me about your salary in your own words. I'll ask if I need anything else.")

# ---------- 1. describe in words ----------
text = st.text_area("About you", key="nl_input", height=100, label_visibility="collapsed",
                    placeholder="e.g. I'm 30, earn 18 lakh a year, pay 40k rent a month in Pune, no investments")
if st.button("Compare regimes", type="primary"):
    st.session_state["convo"] = text.strip()
    st.session_state.pop("parsed", None)

convo = st.session_state.get("convo", "")
if convo:
    if st.session_state.get("parsed", (None, None))[0] != convo:
        try:
            from project_a.parser import parse
            with st.spinner("Reading..."):
                st.session_state["parsed"] = (convo, parse(convo))
        except RuleError:
            st.warning("Describing in words needs a Gemini key. Use the form below instead.")
            st.stop()
        except Exception:
            st.warning("Couldn't reach Gemini just now. Use the form below, or try again.")
            st.stop()
    res = st.session_state["parsed"][1]
    if res["status"] == "needs_clarification":
        st.info(res["question"])
        ans = st.text_input("Your answer", key=f"ans_{len(convo)}")
        if st.button("Send") and ans.strip():
            st.session_state["convo"] = f"{convo}\nQ: {res['question']}\nA: {ans.strip()}"
            st.rerun()
    else:
        if res["assumptions"]:
            st.caption("Assumed: " + "; ".join(res["assumptions"]))
        run_engine(TaxInput.model_validate(res["input"]), engine)

# ---------- 2. or fill the form ----------
with st.expander("Prefer a form?"):
    a, b = st.columns(2)
    gross = a.number_input("Yearly salary (₹)", 0, step=50_000, value=1_500_000)
    age = b.selectbox("Age", ["Under 60", "60 to 79", "80 or more"])
    rent = a.number_input("Rent you pay per year (₹)", 0, step=10_000, value=0)
    hra = b.number_input("HRA you get per year (₹)", 0, step=10_000, value=0)
    if rent or hra:
        basic = a.number_input("Basic + DA per year (₹)", 0, step=50_000, value=0)
        metro = b.checkbox("I rent in Delhi, Mumbai, Kolkata or Chennai")
    else:
        basic, metro = 0, False
    c80 = a.number_input("Investments: 80C (₹, max 1.5L counts)", 0, step=10_000, value=0)
    hl = b.number_input("Home-loan interest (₹)", 0, step=10_000, value=0)
    ds = a.number_input("Health insurance for you (₹)", 0, step=5_000, value=0)
    more = st.checkbox("More deductions")
    nps1b = dp = nps2 = 0
    ps = False
    if more:
        nps1b = a.number_input("NPS you pay: 80CCD(1B) (₹)", 0, step=10_000, value=0)
        nps2 = b.number_input("NPS your employer pays (₹)", 0, step=10_000, value=0)
        dp = a.number_input("Health insurance for parents (₹)", 0, step=5_000, value=0)
        ps = b.checkbox("Parents are 60 or older")
    if st.button("Compare regimes", key="form_go"):
        try:
            inp = TaxInput(gross_salary=int(gross), basic_plus_da=int(basic), hra_received=int(hra), rent_paid_annual=int(rent),
                           metro=metro, age_band={"Under 60": "<60", "60 to 79": "60-79", "80 or more": "80+"}[age],  # type: ignore[arg-type]
                           parent_senior=ps, employer_nps=int(nps2),
                           deductions=Deductions(sec_80c=int(c80), sec_80ccd_1b=int(nps1b), sec_80d_self=int(ds),
                                                 sec_80d_parents=int(dp), home_loan_interest=int(hl)))
        except ValueError as e:
            st.error(f"Please check the numbers: {e}")
        else:
            run_engine(inp, engine)
"""One command: python -m project_a.run_all [--llm]
Always: generate cases, run pytest, evaluate impl A (+ impl C if a frozen artifact exists), write summary.
--llm : also evaluate impl B (--llm-sample N cases, default 40) and the parser (uses Gemini quota; cached)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(*args: str) -> None:
    print("\n$", " ".join(args), flush=True)
    subprocess.run(args, check=True, cwd=HERE.parent)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--llm-sample", type=int, default=40)
    ap.add_argument("--det-sample", type=int, default=10)
    a = ap.parse_args()
    py = sys.executable
    run(py, "-m", "project_a.tests.gen_cases")
    run(py, "-m", "pytest", "-q", "project_a/tests")
    run(py, "-m", "project_a.eval.run_eval", "--impl", "a")
    if list((HERE / "impl_c_llm_compiled" / "frozen").glob("rules_fy*.json")):
        run(py, "-m", "project_a.eval.run_eval", "--impl", "c")
    else:
        print("\n[skip] impl C: no frozen artifact yet (compile + review first) [HUMAN]")
    if a.llm:
        run(py, "-m", "project_a.eval.run_eval", "--impl", "b", "--sample", str(a.llm_sample), "--det-sample", str(a.det_sample))
        run(py, "-m", "project_a.eval.parser_eval")
    run(py, "-m", "project_a.eval.report")
    print("\nOfficial calculator check:")
    subprocess.run([py, "-m", "project_a.tests.diff_official"], cwd=HERE.parent)


if __name__ == "__main__":
    main()

# Project A: Rules vs LLMs, India salaried income tax

Run from the repo root (the folder containing `project_a/`).

```
pip install -r requirements.txt
make all            # tests + impl A (+ C if frozen) + summary, no API key needed
export GEMINI_API_KEY=...
make all-llm        # also impl B (sampled) + parser eval, cached in .cache/llm
python -m streamlit run project_a/app.py
```

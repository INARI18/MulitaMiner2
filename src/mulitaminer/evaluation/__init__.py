"""Native evaluation subsystem: score a run's extraction against a baseline.

Modules (design spec 2026-07-21-native-evaluation-design.md):
    scorers  — metric registry (exact, set_f1, token_f1, rouge_l, bertscore)
    fields   — Pydantic annotation -> metric kind, scanner-JSON overrides
    align    — composite keys + Hungarian assignment against the baseline
    runner   — evaluate_run orchestration (loaders, structural scoring)
    report   — evaluation.json / evaluation.md writers
"""
from mulitaminer.evaluation.runner import EvalResult, evaluate_run

__all__ = ["EvalResult", "evaluate_run"]

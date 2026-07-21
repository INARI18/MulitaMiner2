"""Orchestration: load extraction + baseline, align, score, aggregate.

``evaluate_run`` is the single entry point (re-exported by the package).
The target is a run directory (results.json + run.json, baseline
auto-discovered from the run's config.input) or a bare results.json file
(baseline path then required). Evaluation NEVER runs extraction — it only
consumes existing outputs.
"""
from __future__ import annotations

import ast
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from mulitaminer.evaluation.align import AlignmentResult, align, key_parts_for_source
from mulitaminer.evaluation.fields import FieldPlan, field_plans
from mulitaminer.evaluation.scorers import (
    SCORERS,
    Scorer,
    _as_number,
    pair_score,
    render_text,
    text_scorers,
)
from mulitaminer.models import VulnRecord, record_type_for_source

# Convenience aliases accepted by --metrics.
_METRIC_ALIASES = {"bert": "bertscore", "rouge": "rouge_l"}

# Minimum key-field similarity to pair two structural list items (instances).
_ITEM_MATCH_THRESHOLD = 0.7


@dataclass
class EvalResult:
    meta: dict
    coverage: dict
    fields: dict[str, dict[str, dict]]  # field -> metric -> summary stats
    pairs: list[dict]
    mapping_debug: list[dict]
    unevaluated_baseline_columns: list[str] = field(default_factory=list)


# --- loaders -----------------------------------------------------------------


def _parse_cell(value: Any) -> Any:
    """XLSX cell -> Python value; the GT serializes lists/dicts as repr strings."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, str):
        s = value.strip()
        if s.startswith(("[", "{")):
            try:
                return ast.literal_eval(s)
            except (ValueError, SyntaxError):
                return value
    return value


def load_baseline(path: Path) -> tuple[list[dict], dict]:
    """Baseline XLSX -> (rows, provenance).

    When ``<stem>_instances_generated.xlsx`` exists alongside (deterministic
    re-annotation of the instances column), its instances column replaces the
    original one — the original files mostly left it unfilled.
    """
    df = pd.read_excel(path)
    provenance = {"baseline": str(path), "instances_from": None}
    generated = path.with_name(f"{path.stem}_instances_generated{path.suffix}")
    if generated.is_file():
        gdf = pd.read_excel(generated)
        if "instances" in gdf.columns and len(gdf) == len(df):
            df["instances"] = gdf["instances"]
            provenance["instances_from"] = str(generated)
    rows = [
        {k: _parse_cell(v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]
    return rows, provenance


def load_extraction(path: Path) -> list[VulnRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [record_type_for_source(d.get("source"))(**d) for d in data]


def _resolve_target(target: Path) -> tuple[Path, dict | None]:
    """-> (results.json path, run.json dict or None)."""
    if target.is_dir():
        results = target / "results.json"
        if not results.is_file():
            raise FileNotFoundError(f"No results.json in {target}")
        run_json = target / "run.json"
        run = json.loads(run_json.read_text(encoding="utf-8")) if run_json.is_file() else None
        return results, run
    if target.is_file():
        return target, None
    raise FileNotFoundError(f"Target not found: {target}")


def discover_baseline(run: dict | None) -> Path | None:
    """The baseline XLSX sits next to the input PDF, same stem."""
    input_path = (run or {}).get("config", {}).get("input")
    if not input_path:
        return None
    candidate = Path(input_path).with_suffix(".xlsx")
    return candidate if candidate.is_file() else None


def _overrides_for_source(source: str | None) -> dict[str, str]:
    """Match a scanner profile by record source; no profile -> no overrides."""
    from mulitaminer.scanner_engine import all_scanners

    for profile in all_scanners().values():
        if profile.source == (source or ""):
            return dict(profile.field_metric_overrides)
    return {}


def resolve_metrics(spec: str | None) -> list[Scorer]:
    """--metrics value -> text scorers to run ("all" = every installed one)."""
    if spec in (None, "", "all"):
        return [s for s in text_scorers() if s.available]
    chosen: list[Scorer] = []
    for raw in spec.split(","):
        name = _METRIC_ALIASES.get(raw.strip().lower(), raw.strip().lower())
        scorer = SCORERS.get(name)
        if scorer is None or scorer.kind != "text":
            valid = sorted(s.name for s in text_scorers())
            raise ValueError(f"Unknown text metric '{raw.strip()}'; valid: {valid}")
        if not scorer.available:
            raise RuntimeError(f"Metric '{name}' is unavailable — {scorer.hint}")
        chosen.append(scorer)
    return chosen


# --- structural scoring ------------------------------------------------------


def _leaf_score(a: Any, b: Any) -> tuple[float, bool]:
    """Leaf compare inside structural recursion: numeric pairs exactly,
    text by token F1 (cheap and symmetric)."""
    if _as_number(a) is not None and _as_number(b) is not None:
        return pair_score(SCORERS["exact"], a, b)
    return pair_score(SCORERS["token_f1"], a, b)


def _dict_score(sub_model, ext_val: Any, base_val: Any) -> float:
    """Field-by-field mean over a nested dict/model pair."""
    e = ext_val if isinstance(ext_val, dict) else {}
    b = base_val if isinstance(base_val, dict) else {}
    if not isinstance(ext_val, dict) or not isinstance(base_val, dict):
        # One side is not structured (e.g. literal_eval fell back to a raw
        # string) — degrade to text comparison rather than scoring 0.
        return pair_score(SCORERS["token_f1"], ext_val, base_val)[0]
    keys = list(sub_model.model_fields) if sub_model else sorted(set(e) | set(b))
    scores = [_leaf_score(e.get(k), b.get(k))[0] for k in keys]
    return sum(scores) / len(scores) if scores else 1.0


def _list_score(sub_model, ext_val: Any, base_val: Any) -> float:
    """Sub-align list items by their key field, recurse, and normalize by the
    larger side so missing/spurious items cost score.

    The key field is the sub-model's first declared field (e.g.
    ``Instance.instance`` — the URL), which by convention identifies the item.
    """
    ext_items = ext_val if isinstance(ext_val, list) else [ext_val]
    base_items = base_val if isinstance(base_val, list) else [base_val]
    key = next(iter(sub_model.model_fields)) if sub_model else None

    def _key_text(item: Any) -> str:
        if key and isinstance(item, dict):
            return render_text(item.get(key))
        return render_text(item)

    used: set[int] = set()
    pair_scores: list[float] = []
    for e_item in ext_items:
        best_j, best_sim = None, 0.0
        for j, b_item in enumerate(base_items):
            if j in used:
                continue
            sim = fuzz.ratio(_key_text(e_item), _key_text(b_item)) / 100.0
            if sim > best_sim:
                best_j, best_sim = j, sim
        if best_j is not None and best_sim >= _ITEM_MATCH_THRESHOLD:
            used.add(best_j)
            pair_scores.append(_dict_score(sub_model, e_item, base_items[best_j]))
    denom = max(len(ext_items), len(base_items))
    return sum(pair_scores) / denom if denom else 1.0


def _structural_score(plan: FieldPlan, ext_val: Any, base_val: Any) -> tuple[float, bool]:
    e, b = render_text(ext_val), render_text(base_val)
    if not e and not b:
        return 1.0, True
    if not e or not b:
        return 0.0, False
    if plan.is_list:
        return _list_score(plan.sub_model, ext_val, base_val), False
    return _dict_score(plan.sub_model, ext_val, base_val), False


# --- aggregation -------------------------------------------------------------


def _row_value(row: dict, name: str) -> Any:
    """Field access tolerating the Name/name alias split."""
    if name in row:
        return row[name]
    return row.get("Name") if name == "name" else None


def _score_pair(
    plans: list[FieldPlan],
    selected_text: list[Scorer],
    ext_row: dict,
    base_row: dict,
) -> dict[str, dict[str, tuple[float, bool]]]:
    """-> {field: {metric: (score, vacuous)}}."""
    out: dict[str, dict[str, tuple[float, bool]]] = {}
    for plan in plans:
        ext_val = _row_value(ext_row, plan.name)
        base_val = _row_value(base_row, plan.name)
        if plan.metric == "text":
            out[plan.name] = {
                s.name: pair_score(s, ext_val, base_val) for s in selected_text
            }
        elif plan.metric == "structural":
            out[plan.name] = {"structural": _structural_score(plan, ext_val, base_val)}
        else:  # a single scorer name (exact, set_f1, or an override)
            out[plan.name] = {
                plan.metric: pair_score(SCORERS[plan.metric], ext_val, base_val)
            }
    return out


def _summarize(
    pair_scores: list[dict[str, dict[str, tuple[float, bool]]]],
    ext_rows: list[dict],
    base_rows: list[dict],
    alignment: AlignmentResult,
    plans: list[FieldPlan],
) -> dict[str, dict[str, dict]]:
    fields_summary: dict[str, dict[str, dict]] = {}
    for plan in plans:
        metrics: dict[str, dict] = {}
        metric_names = set()
        for ps in pair_scores:
            metric_names.update(ps.get(plan.name, {}))
        for metric in sorted(metric_names):
            values = [ps[plan.name][metric][0] for ps in pair_scores if plan.name in ps]
            vacuous = [ps[plan.name][metric][1] for ps in pair_scores if plan.name in ps]
            if not values:
                continue
            filled_ext = filled_base = 0
            for i, j in alignment.pairs:
                if render_text(_row_value(ext_rows[i], plan.name)):
                    filled_ext += 1
                if render_text(_row_value(base_rows[j], plan.name)):
                    filled_base += 1
            metrics[metric] = {
                "mean": round(statistics.fmean(values), 4),
                "min": round(min(values), 4),
                "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
                "n": len(values),
                "vacuous_n": sum(vacuous),
                "fill_rate_extraction": round(filled_ext / len(values), 4),
                "fill_rate_baseline": round(filled_base / len(values), 4),
            }
        fields_summary[plan.name] = metrics
    return fields_summary


# --- entry point -------------------------------------------------------------


def evaluate_run(
    target: Path,
    baseline: Path | None = None,
    metrics: str | None = "all",
    threshold: float = 0.7,
) -> EvalResult:
    results_path, run = _resolve_target(Path(target))
    baseline_path = baseline or discover_baseline(run)
    if baseline_path is None:
        raise ValueError(
            "No baseline: pass one explicitly (--baseline) — auto-discovery "
            "needs a run directory whose run.json points at the source PDF."
        )

    records = load_extraction(results_path)
    if not records:
        raise ValueError(f"{results_path} contains no records")
    base_rows, provenance = load_baseline(Path(baseline_path))

    source = records[0].source
    record_type = record_type_for_source(source)
    plans = field_plans(record_type, _overrides_for_source(source))
    selected_text = resolve_metrics(metrics)

    ext_rows = [r.model_dump(mode="json", by_alias=True) for r in records]
    alignment = align(ext_rows, base_rows, key_parts_for_source(source), threshold)

    pair_scores = [
        _score_pair(plans, selected_text, ext_rows[i], base_rows[j])
        for i, j in alignment.pairs
    ]

    def _name(row: dict) -> str:
        return str(row.get("Name") or row.get("name") or "")

    pairs_out = [
        {
            "extraction_index": i,
            "baseline_index": j,
            "name": _name(base_rows[j]),
            "scores": {
                f: {m: {"score": round(s, 4), "vacuous": v} for m, (s, v) in ms.items()}
                for f, ms in ps.items()
            },
        }
        for (i, j), ps in zip(alignment.pairs, pair_scores)
    ]

    model_fields = {f.lower() for f in record_type.model_fields} | {"name"}
    unevaluated = sorted(
        {c for c in (base_rows[0] if base_rows else {}) if c.lower() not in model_fields}
    )

    coverage = {
        "baseline_count": len(base_rows),
        "extraction_count": len(ext_rows),
        "matched": len(alignment.pairs),
        "recall": round(len(alignment.pairs) / len(base_rows), 4) if base_rows else 0.0,
        "precision": round(len(alignment.pairs) / len(ext_rows), 4) if ext_rows else 0.0,
        "missed": [_name(base_rows[j]) for j in alignment.unmatched_baseline],
        "spurious": [_name(ext_rows[i]) for i in alignment.unmatched_extraction],
    }

    meta = {
        "results": str(results_path),
        **provenance,
        "source": source,
        "threshold": threshold,
        "text_metrics": [s.name for s in selected_text],
        "unavailable_metrics": {
            s.name: s.hint for s in text_scorers() if not s.available
        },
    }

    return EvalResult(
        meta=meta,
        coverage=coverage,
        fields=_summarize(pair_scores, ext_rows, base_rows, alignment, plans),
        pairs=pairs_out,
        mapping_debug=alignment.debug_rows,
        unevaluated_baseline_columns=unevaluated,
    )


__all__ = ["EvalResult", "evaluate_run", "load_baseline", "load_extraction", "resolve_metrics"]

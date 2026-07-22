"""Report writers: evaluation.json (machine) + evaluation.md (human).

Both are written next to the evaluated results file; the console gets the
field x metric summary table.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from mulitaminer.evaluation.runner import EvalResult

# How many worst-scoring pairs to list per field in the Markdown report.
_WORST_N = 5


def _version() -> str:
    try:
        return metadata.version("mulitaminer")
    except metadata.PackageNotFoundError:
        return "unknown"


def _metric_columns(result: EvalResult) -> list[str]:
    cols: set[str] = set()
    for metrics in result.fields.values():
        cols.update(metrics)
    # Stable, readable order: structural first, then text alphabetically.
    order = ["exact", "set_f1", "set_f1_ids", "structural"]
    return [c for c in order if c in cols] + sorted(c for c in cols if c not in order)


def summary_table(result: EvalResult) -> str:
    """Plain-text field x metric table of MEASURED means (vacuous excluded).

    Vacuous (empty x empty) pairs score 1.0 and inflate an inclusive mean;
    all-vacuous cells print n/a instead of a fake 1.000 (audit finding).
    """
    cols = _metric_columns(result)
    header = ["field", *cols]
    rows = [header, ["-" * len(h) for h in header]]
    for field_name, metrics in result.fields.items():
        row = [field_name]
        for c in cols:
            stats = metrics.get(c)
            # ASCII placeholders: Windows consoles often decode cp1252.
            if stats is None:
                row.append("-")
            elif stats["n_measured"] == 0:
                row.append("n/a")
            else:
                row.append(f"{stats['measured_mean']:.3f}")
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(r, widths)) for r in rows
    )


def _worst_pairs(result: EvalResult, field_name: str) -> list[tuple[str, float]]:
    scored = []
    for pair in result.pairs:
        metrics = pair["scores"].get(field_name)
        if not metrics:
            continue
        mean = sum(m["score"] for m in metrics.values()) / len(metrics)
        if mean < 1.0:
            scored.append((pair["name"], round(mean, 3)))
    return sorted(scored, key=lambda t: t[1])[:_WORST_N]


def render_markdown(result: EvalResult) -> str:
    cov = result.coverage
    lines = [
        "# Evaluation report",
        "",
        f"- results: `{result.meta['results']}`",
        f"- baseline: `{result.meta['baseline']}`",
        f"- source: {result.meta['source']} — threshold {result.meta['threshold']}"
        f" — text metrics: {', '.join(result.meta['text_metrics']) or 'none'}",
        "",
        "## Coverage",
        "",
        f"- baseline findings: {cov['baseline_count']}",
        f"- extracted records: {cov['extraction_count']}",
        f"- matched: {cov['matched']}  (recall {cov['recall']:.3f},"
        f" precision {cov['precision']:.3f})",
        "",
        "## Field scores (measured mean — vacuous empty×empty pairs excluded)",
        "",
        "```",
        summary_table(result),
        "```",
        "",
        "`n/a` = every matched pair was empty on both sides for that field "
        "(nothing to measure). Inclusive means and per-pair detail live in "
        "`evaluation.json`.",
        "",
    ]

    worst_sections = []
    for field_name in result.fields:
        worst = _worst_pairs(result, field_name)
        if worst:
            worst_sections.append(
                f"- **{field_name}**: "
                + "; ".join(f"{name} ({score})" for name, score in worst)
            )
    if worst_sections:
        lines += ["## Worst pairs per field", "", *worst_sections, ""]

    if cov["false_negatives"]:
        lines += ["## False negatives (in baseline, not extracted)", ""]
        lines += [f"- {n}" for n in cov["false_negatives"]] + [""]
    if cov["false_positives"]:
        lines += ["## False positives (extracted, not in baseline)", ""]
        lines += [f"- {n}" for n in cov["false_positives"]] + [""]

    notes = []
    if result.meta.get("reannotated_from"):
        cols = ", ".join(f"`{c}`" for c in result.meta.get("reannotated_columns", []))
        notes.append(
            f"{cols} ground truth taken from `{result.meta['reannotated_from']}` "
            "(deterministic re-annotation from the PDF)."
        )
    for name, hint in result.meta.get("unavailable_metrics", {}).items():
        notes.append(f"metric `{name}` not run — {hint}.")
    never_filled = [
        f for f, metrics in result.fields.items()
        if metrics and all(s["fill_rate_baseline"] == 0.0 for s in metrics.values())
    ]
    if never_filled:
        notes.append(
            "baseline never fills " + ", ".join(f"`{f}`" for f in never_filled)
            + " — scores there only measure presence agreement: 1.0 means the "
            "extraction also left the field empty; low values mean it filled a "
            "field the ground truth does not annotate."
        )
    if result.unevaluated_baseline_columns:
        notes.append(
            "baseline columns outside the record schema (not scored): "
            + ", ".join(f"`{c}`" for c in result.unevaluated_baseline_columns)
        )
    if notes:
        lines += ["## Notes", "", *[f"- {n}" for n in notes], ""]

    return "\n".join(lines)


def write_reports(result: EvalResult, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["meta"] = {
        **payload["meta"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": _version(),
    }
    json_path = out_dir / "evaluation.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path = out_dir / "evaluation.md"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return {"json": json_path, "md": md_path}

"""Self-contained HTML report for an experiment tree.

Reads experiment.json plus each run's evaluation.json and renders one offline
HTML file (inline SVG, no JavaScript, no external assets) styled after the
project's cream/orange deck. Series colors are the dataviz reference
categorical palette (first four slots, all-pairs CVD-safe); orange is reserved
for brand chrome so it never doubles as a series.
"""
from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Per-field primary metric, in priority order (first present wins).
_METRIC_PRIORITY = ("exact", "set_f1", "set_f1_ids", "structural", "token_f1", "rouge_l")
# Validated categorical slots (blue, green, magenta, yellow) for light / dark.
_SERIES_LIGHT = ["#2a78d6", "#008300", "#e87ba4", "#eda100"]


def _field_score(field_metrics: dict) -> float | None:
    for metric in _METRIC_PRIORITY:
        stats = field_metrics.get(metric)
        if stats and stats.get("n_measured"):
            return stats.get("measured_mean", stats.get("mean"))
    return None


def _aggregate(experiment_dir: Path) -> dict:
    manifest = json.loads((experiment_dir / "experiment.json").read_text(encoding="utf-8"))
    # (scanner, model) -> {"recall":[...], "precision":[...], "cost":[...],
    #                      "duration":[...], "fields": {field: [scores]}}
    cells: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"recall": [], "precision": [], "cost": [], "duration": [],
                 "fields": defaultdict(list)})
    for r in manifest["runs"]:
        if r["status"] not in ("ok", "cached"):
            continue
        cell = cells[(r["scanner"], r["model"])]
        cov = r.get("coverage")
        if cov:
            cell["recall"].append(cov["recall"])
            cell["precision"].append(cov["precision"])
        if "cost_usd" in r:
            cell["cost"].append(r["cost_usd"])
        if "duration_s" in r:
            cell["duration"].append(r["duration_s"])
        eval_path = Path(r["run_dir"]) / "evaluation.json"
        if eval_path.is_file():
            fields = json.loads(eval_path.read_text(encoding="utf-8")).get("fields", {})
            for field, metrics in fields.items():
                score = _field_score(metrics)
                if score is not None:
                    cell["fields"][field].append(score)
    return {"manifest": manifest, "cells": cells}


def _stats(values: list[float]) -> tuple[float, float, float] | None:
    if not values:
        return None
    return sum(values) / len(values), min(values), max(values)


# --- SVG primitives ----------------------------------------------------------

def _esc(text) -> str:
    return html.escape(str(text))


def _bar_chart(rows: list[tuple[str, float, float, float, int]], vmax: float,
               fmt: str = "{:.2f}") -> str:
    """rows: (label, mean, lo, hi, series_idx). Horizontal bars + min-max whisker."""
    row_h, gap, pad_l, top = 26, 10, 150, 8
    width, plot_w = 720, 720 - 150 - 60
    height = top + len(rows) * (row_h + gap)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'class="chart" preserveAspectRatio="xMinYMin meet">']
    for gx in (0.25, 0.5, 0.75, 1.0):
        x = pad_l + plot_w * gx * (1.0 / vmax if vmax else 1)
        if gx <= vmax:
            parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height}" '
                         f'class="grid"/>')
            parts.append(f'<text x="{x:.1f}" y="{top-1}" class="tick" '
                         f'text-anchor="middle">{gx:g}</text>')
    for i, (label, mean, lo, hi, sidx) in enumerate(rows):
        y = top + i * (row_h + gap) + gap
        bw = plot_w * (mean / vmax if vmax else 0)
        color = f"var(--s{sidx % 4})"
        parts.append(f'<text x="{pad_l-8}" y="{y+row_h*0.7:.1f}" class="rowlabel" '
                     f'text-anchor="end">{_esc(label)}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y}" width="{bw:.1f}" height="{row_h}" '
                     f'rx="4" fill="{color}"><title>{_esc(label)}: {fmt.format(mean)}'
                     f' (min {fmt.format(lo)}, max {fmt.format(hi)})</title></rect>')
        if hi > lo:
            xlo = pad_l + plot_w * (lo / vmax)
            xhi = pad_l + plot_w * (hi / vmax)
            ym = y + row_h / 2
            parts.append(f'<line x1="{xlo:.1f}" y1="{ym:.1f}" x2="{xhi:.1f}" y2="{ym:.1f}" '
                         f'class="whisker"/>')
        parts.append(f'<text x="{pad_l+bw+6:.1f}" y="{y+row_h*0.7:.1f}" '
                     f'class="value">{fmt.format(mean)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _dot_plot(fields: list[str], models: list[str], data: dict) -> str:
    """data[(field, model)] = (mean, lo, hi). Fields on y, models as colored dots."""
    row_h, pad_l, top = 24, 190, 24
    width, plot_w = 720, 720 - 190 - 30
    height = top + len(fields) * row_h + 8
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'class="chart" preserveAspectRatio="xMinYMin meet">']
    for gx in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = pad_l + plot_w * gx
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-8}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{top-1}" class="tick" text-anchor="middle">{gx:g}</text>')
    for i, field in enumerate(fields):
        y = top + i * row_h + row_h / 2
        parts.append(f'<text x="{pad_l-10}" y="{y+3:.1f}" class="rowlabel" '
                     f'text-anchor="end">{_esc(field)}</text>')
        for m, model in enumerate(models):
            cell = data.get((field, model))
            if cell is None:
                continue
            mean, lo, hi = cell
            color = f"var(--s{m % 4})"
            if hi > lo:
                parts.append(f'<line x1="{pad_l+plot_w*lo:.1f}" y1="{y:.1f}" '
                             f'x2="{pad_l+plot_w*hi:.1f}" y2="{y:.1f}" class="whisker"/>')
            parts.append(f'<circle cx="{pad_l+plot_w*mean:.1f}" cy="{y:.1f}" r="5" '
                         f'fill="{color}" class="dot"><title>{_esc(model)} · '
                         f'{_esc(field)}: {mean:.3f}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


def _legend(models: list[str]) -> str:
    items = "".join(
        f'<span class="lg"><span class="sw" style="background:var(--s{i%4})"></span>'
        f'{_esc(m)}</span>' for i, m in enumerate(models))
    return f'<div class="legend">{items}</div>'


# --- assembly ----------------------------------------------------------------

def build_report(experiment_dir: Path, out_path: Path | None = None) -> Path:
    agg = _aggregate(experiment_dir)
    manifest, cells = agg["manifest"], agg["cells"]
    out_path = out_path or (experiment_dir / "report.html")

    models = manifest["config"]["models"]
    scanners = sorted({s for (s, _m) in cells})
    cfg = manifest["config"]
    totals = manifest["totals"]

    sections: list[str] = []

    # Coverage (recall) per scanner, bars per model with run-to-run whiskers.
    for scanner in scanners:
        rows = []
        for i, model in enumerate(models):
            st = _stats(cells[(scanner, model)]["recall"])
            if st:
                rows.append((model, st[0], st[1], st[2], i))
        if rows:
            sections.append(
                f'<section><div class="kicker">Coverage · {_esc(scanner)}</div>'
                f'<h2>Recall per model</h2>'
                f'<p class="note">Bar = mean recall across runs; whisker = run-to-run range.</p>'
                f'{_bar_chart(rows, 1.0)}</section>')

    # Field quality dot plot per scanner.
    for scanner in scanners:
        field_set: list[str] = []
        data = {}
        for i, model in enumerate(models):
            for field, scores in cells[(scanner, model)]["fields"].items():
                st = _stats(scores)
                if st:
                    data[(field, model)] = st
                    if field not in field_set:
                        field_set.append(field)
        if data:
            sections.append(
                f'<section><div class="kicker">Field quality · {_esc(scanner)}</div>'
                f'<h2>Measured mean per field</h2>'
                f'<p class="note">Vacuous (empty×empty) pairs excluded; whisker = run-to-run range.</p>'
                f'{_legend(models)}{_dot_plot(field_set, models, data)}</section>')

    # Cost and latency per model (summed over its cells).
    cost_rows, dur_rows = [], []
    for i, model in enumerate(models):
        costs = [c for (s, m), cell in cells.items() if m == model for c in cell["cost"]]
        durs = [d for (s, m), cell in cells.items() if m == model for d in cell["duration"]]
        if costs:
            cost_rows.append((model, sum(costs) / len(costs), min(costs), max(costs), i))
        if durs:
            dur_rows.append((model, sum(durs) / len(durs), min(durs), max(durs), i))
    if cost_rows:
        vmax = max(r[3] for r in cost_rows) or 1
        sections.append(
            f'<section><div class="kicker">Cost</div><h2>Cost per run (USD)</h2>'
            f'{_bar_chart(cost_rows, vmax, "${:.4f}")}</section>')
    if dur_rows:
        vmax = max(r[3] for r in dur_rows) or 1
        sections.append(
            f'<section><div class="kicker">Latency</div><h2>Active seconds per run</h2>'
            f'{_bar_chart(dur_rows, vmax, "{:.0f}s")}</section>')

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    head = (
        f'<header><div class="kicker">Experiment report</div>'
        f'<h1>MulitaMiner</h1>'
        f'<dl class="meta">'
        f'<div><dt>models</dt><dd>{_esc(", ".join(models))}</dd></div>'
        f'<div><dt>reports</dt><dd>{len(cfg["reports"])}</dd></div>'
        f'<div><dt>runs each</dt><dd>{cfg["runs"]}</dd></div>'
        f'<div><dt>completed</dt><dd>{totals["done"]}/{totals["planned"]}</dd></div>'
        f'<div><dt>active time</dt><dd>{totals["active_seconds"]:.0f}s</dd></div>'
        f'<div><dt>cost</dt><dd>${totals["cost_usd"]:.4f}</dd></div>'
        f'<div><dt>generated</dt><dd>{_esc(generated)}</dd></div>'
        f'</dl></header>')

    doc = f"<!doctype html><html lang=en><meta charset=utf-8>" \
          f"<meta name=viewport content='width=device-width,initial-scale=1'>" \
          f"<title>MulitaMiner experiment report</title>" \
          f"<style>{_CSS}</style><main class=viz-root>{head}{''.join(sections)}</main></html>"
    out_path.write_text(doc, encoding="utf-8")
    return out_path


_CSS = """
:root{color-scheme:light dark}
.viz-root{
  --page:#f4f1ea; --card:#faf8f2; --ink:#1a1a17; --ink2:#52514e; --muted:#8a887f;
  --accent:#d9541e; --grid:#e6e3da; --baseline:#cfccc2;
  --s0:#2a78d6; --s1:#008300; --s2:#e87ba4; --s3:#eda100;
  background:var(--page); color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  max-width:860px; margin:0 auto; padding:32px 24px;
}
@media(prefers-color-scheme:dark){:root:where(:not([data-theme=light])) .viz-root{
  --page:#14130f; --card:#1c1b16; --ink:#f4f1ea; --ink2:#c3c2b7; --muted:#8a887f;
  --accent:#eb6834; --grid:#2c2c26; --baseline:#3a3932;
  --s0:#3987e5; --s1:#008300; --s2:#d55181; --s3:#c98500;
}}
:root[data-theme=dark] .viz-root{
  --page:#14130f; --card:#1c1b16; --ink:#f4f1ea; --ink2:#c3c2b7; --muted:#8a887f;
  --accent:#eb6834; --grid:#2c2c26; --baseline:#3a3932;
  --s0:#3987e5; --s1:#008300; --s2:#d55181; --s3:#c98500;
}
.kicker{font:600 11px/1 ui-monospace,monospace; letter-spacing:.12em;
  text-transform:uppercase; color:var(--accent); margin-bottom:8px}
h1{font-size:40px; margin:0 0 20px; letter-spacing:-.02em}
h2{font-size:19px; margin:0 0 4px}
header{border-bottom:2px solid var(--accent); padding-bottom:20px; margin-bottom:28px}
.meta{display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr));
  gap:12px 20px; margin:0}
.meta div{margin:0}
.meta dt{font:600 10px/1.4 ui-monospace,monospace; text-transform:uppercase;
  letter-spacing:.08em; color:var(--muted)}
.meta dd{margin:2px 0 0; font-variant-numeric:tabular-nums; font-weight:600}
section{background:var(--card); border:1px solid var(--grid); border-radius:10px;
  padding:18px 20px; margin-bottom:18px}
.note{color:var(--ink2); font-size:13px; margin:0 0 10px}
.chart{width:100%; height:auto; overflow:visible}
.grid{stroke:var(--grid); stroke-width:1}
.tick{fill:var(--muted); font:10px ui-monospace,monospace}
.rowlabel{fill:var(--ink2); font:12px system-ui,sans-serif}
.value{fill:var(--ink2); font:600 11px ui-monospace,monospace; dominant-baseline:middle}
.whisker{stroke:var(--baseline); stroke-width:2; stroke-linecap:round}
.dot{stroke:var(--card); stroke-width:2}
.legend{display:flex; flex-wrap:wrap; gap:14px; margin:6px 0 12px}
.lg{font-size:12px; color:var(--ink2); display:inline-flex; align-items:center; gap:6px}
.sw{width:12px; height:12px; border-radius:3px; display:inline-block}
"""

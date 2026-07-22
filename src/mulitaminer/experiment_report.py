"""Self-contained HTML report for an experiment tree: reads experiment.json plus
each run's evaluation.json and renders one offline inline-SVG dashboard (no JS
deps, no external assets), styled after the project's cream/orange deck.

A *target* is one report (its baseline XLSX is the gold); a *model* is an LLM
profile; spread is across the N runs. The similarity categories in the
distribution are a presentation binning (thresholds shown), not a pipeline
metric.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_TEXT = ("bertscore", "token_f1", "rouge_l")
_DET = ("exact", "set_f1", "set_f1_ids", "structural")


def _ms(values: list[float]) -> dict:
    if not values:
        return {"m": None, "s": 0.0}
    return {"m": round(statistics.fmean(values), 4),
            "s": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0}


def _box(values: list[float]) -> dict | None:
    if not values:
        return None
    vs = sorted(values)
    if len(vs) < 2:
        v = vs[0]
        return {"min": v, "q1": v, "med": v, "q3": v, "max": v, "n": 1}
    q1, med, q3 = statistics.quantiles(vs, n=4)
    return {"min": round(vs[0], 4), "q1": round(q1, 4), "med": round(med, 4),
            "q3": round(q3, 4), "max": round(vs[-1], 4), "n": len(vs)}


def _aggregate(experiment_dir: Path) -> dict:
    manifest = json.loads((experiment_dir / "experiment.json").read_text(encoding="utf-8"))
    models = manifest["config"]["models"]

    cov: dict = defaultdict(lambda: defaultdict(list))
    fmeas: dict = defaultdict(lambda: defaultdict(list))
    fill: dict = defaultdict(lambda: defaultdict(list))     # (t,m) -> field -> [gap per run]
    pairsc: dict = defaultdict(lambda: defaultdict(list))
    field_metrics: dict = defaultdict(set)
    targets: dict = {}

    for r in manifest["runs"]:
        if r["status"] not in ("ok", "cached"):
            continue
        target, model = Path(r["report"]).stem, r["model"]
        targets[target] = r["scanner"]
        key = (target, model)
        cv = r.get("coverage")
        if cv:
            cov[key]["recall"].append(cv["recall"])
            cov[key]["precision"].append(cv["precision"])
            cov[key]["missed"].append(len(cv.get("missed", [])))
            cov[key]["spurious"].append(len(cv.get("spurious", [])))
            bc = cv.get("baseline_count") or 0
            cov[key]["absent"].append(len(cv.get("missed", [])) / bc if bc else 0.0)
        if "cost_usd" in r:
            cov[key]["cost"].append(r["cost_usd"])
        if "duration_s" in r:
            cov[key]["duration"].append(r["duration_s"])
        ep = Path(r["run_dir"]) / "evaluation.json"
        if not ep.is_file():
            continue
        ev = json.loads(ep.read_text(encoding="utf-8"))
        for field, ms in ev.get("fields", {}).items():
            fb = fe = None
            for metric, st in ms.items():
                field_metrics[field].add(metric)
                if st.get("n_measured"):
                    fmeas[key][(field, metric)].append(st.get("measured_mean"))
                if fb is None and st.get("fill_rate_baseline") is not None:
                    fb, fe = st["fill_rate_baseline"], st.get("fill_rate_extraction", 0.0)
            if fb is not None:
                fill[key][field].append(max(0.0, fb - (fe or 0.0)))
        for pair in ev.get("pairs", []):
            scores = pair.get("scores", {})
            for metric in _TEXT:
                vals = [ms[metric]["score"] for ms in scores.values()
                        if metric in ms and not ms[metric]["vacuous"]]
                if vals:
                    pairsc[key][metric].append(statistics.fmean(vals))

    tsorted = sorted(targets)
    text_present = [m for m in _TEXT if any(m in ms for ms in field_metrics.values())]
    det_present = [m for m in _DET if any(m in ms for ms in field_metrics.values())]
    sem_fields = sorted(f for f, ms in field_metrics.items() if ms & set(_TEXT))
    det_fields = sorted(f for f, ms in field_metrics.items() if not (ms & set(_TEXT)))
    omit_fields = sorted({f for c in fill.values() for f in c})

    def pooled(model, key):
        return [v for (t, m), c in cov.items() if m == model for v in c[key]]

    overall = {m: {k: _ms(pooled(m, k)) for k in
                   ("recall", "precision", "missed", "spurious", "cost", "duration")}
               for m in models}
    by_target = {t: {m: {"recall": _ms(cov[(t, m)]["recall"]),
                         "precision": _ms(cov[(t, m)]["precision"])}
                     for m in models} for t in tsorted}

    def field_block(fields, metrics):
        return {metric: {t: {f: {m: _ms(fmeas[(t, m)].get((f, metric), []))
                                 for m in models} for f in fields} for t in tsorted}
                for metric in metrics}

    omission = {t: {f: {m: _ms(fill[(t, m)].get(f, [])) for m in models}
                    for f in omit_fields} for t in tsorted}

    def dist_box(metrics):
        return {metric: {m: _box([v for t in tsorted for v in pairsc[(t, m)].get(metric, [])])
                         for m in models} for metric in metrics}

    def _cat(scores, ab):
        matched = 1.0 - ab
        if not scores:
            return [0, 0, 0, 0, round(ab, 4)]
        n = len(scores)
        hi = sum(v >= 0.9 for v in scores) / n
        mo = sum(0.8 <= v < 0.9 for v in scores) / n
        sl = sum(0.7 <= v < 0.8 for v in scores) / n
        dv = sum(v < 0.7 for v in scores) / n
        return [round(x, 4) for x in (hi * matched, mo * matched, sl * matched, dv * matched, ab)]

    def dist_cat(metrics):
        # [High>=.9, Moderate>=.8, Slight>=.7, Divergent<.7, Absent] over the baseline.
        out: dict = {}
        for metric in metrics:
            out[metric] = {}
            for m in models:
                scores = [v for t in tsorted for v in pairsc[(t, m)].get(metric, [])]
                ab = statistics.fmean(pooled(m, "absent")) if pooled(m, "absent") else 0.0
                out[metric][m] = _cat(scores, ab)
        return out

    def dist_box_bt(metrics):
        # Per-report box, same shape as dist: {metric: {target: {model: box}}}
        return {metric: {t: {m: _box(pairsc[(t, m)].get(metric, []))
                             for m in models} for t in tsorted} for metric in metrics}

    def dist_cat_bt(metrics):
        out: dict = {}
        for metric in metrics:
            out[metric] = {}
            for t in tsorted:
                out[metric][t] = {}
                for m in models:
                    absent = cov[(t, m)]["absent"]
                    ab = statistics.fmean(absent) if absent else 0.0
                    out[metric][t][m] = _cat(pairsc[(t, m)].get(metric, []), ab)
        return out

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": manifest["config"], "totals": manifest["totals"],
        "models": models, "targets": tsorted, "scanners": targets,
        "text_metrics": text_present, "det_metrics": det_present,
        "sem_fields": sem_fields, "det_fields": det_fields, "omit_fields": omit_fields,
        "overall": overall, "by_target": by_target,
        "text_fields": field_block(sem_fields, text_present),
        "det_field_block": field_block(det_fields, det_present),
        "omission": omission,
        "dist": dist_box(text_present), "dist_cat": dist_cat(text_present),
        "dist_by_target": dist_box_bt(text_present),
        "dist_cat_by_target": dist_cat_bt(text_present),
    }


def build_report(experiment_dir: Path, out_path: Path | None = None) -> Path:
    data = _aggregate(experiment_dir)
    out_path = out_path or (experiment_dir / "report.html")
    doc = (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>MulitaMiner - experiment report</title>"
        f"<style>{_CSS}</style>{_BODY}"
        f"<script>const DATA={json.dumps(data, ensure_ascii=False)};{_JS}</script>"
        "</html>"
    )
    out_path.write_text(doc, encoding="utf-8")
    return out_path



_CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f4f1ea;--card:#faf8f2;--card2:#efece3;--accent:#d9541e;
  --ink:#1a1a17;--ink2:#52514e;--muted:#8a887f;--grid:#e6e3da;--border:#e2ded4}
body{background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-variant-numeric:tabular-nums;max-width:1040px;margin:0 auto;padding:2rem 1.5rem 4rem}
.kick{font:600 11px/1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
h1{font-size:2.2rem;letter-spacing:-.02em;margin:.35rem 0 .1rem;font-family:ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
h1 span{color:var(--accent)}
h2{font-size:1.12rem;margin:.1rem 0}
header{border-bottom:2px solid var(--accent);padding-bottom:1.1rem;margin-bottom:1.2rem;
  display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:1rem}
.meta{display:flex;flex-wrap:wrap;gap:.4rem 1.3rem;font:.7rem/1.4 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;color:var(--muted);text-align:right}
.meta b{color:var(--ink);font-weight:600}
.hero{display:grid;grid-template-columns:minmax(240px,1fr) 1.7fr;gap:1.2rem;margin-bottom:1.6rem;align-items:stretch}
@media(max-width:740px){.hero{grid-template-columns:1fr}}
.hero .dark{background:var(--ink);color:#faf8f2;border-radius:14px;padding:1.4rem 1.5rem;
  display:flex;flex-direction:column;justify-content:space-between;gap:1rem;min-height:150px}
.hero .dark .l{font:600 10px/1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.hero .dark .win{display:flex;align-items:center;gap:.55rem;margin-top:.6rem;font:700 1.4rem/1.1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;word-break:break-word}
.hero .dark .big{font:700 2.7rem/1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
.hero .dark .sub{font:.72rem/1.4 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;color:#c9c7bd;margin-top:.4rem}
.hero .lite{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:1.2rem 1.3rem;
  display:flex;flex-direction:column;overflow:hidden}
/* Bounded, scrollable ranking: the hero stays compact no matter the model count. */
#verdictBars{overflow-y:auto;overflow-x:hidden;max-height:190px;padding-right:.25rem;margin-right:-.25rem}
.brow{display:flex;align-items:center;gap:.6rem;margin-bottom:.4rem}
.brow:last-child{margin-bottom:0}
.brow .nm{width:84px;text-align:right;font:.7rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brow .track{flex:1;height:16px;background:var(--card2);border-radius:4px;overflow:hidden}
.brow .fill{height:100%;border-radius:4px}
.brow .vv{width:98px;font:.7rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;flex-shrink:0}
.brow .vv s{color:var(--muted);font-size:.6rem;text-decoration:none}
.dot{width:11px;height:11px;border-radius:50%;display:inline-block;flex-shrink:0}
nav{position:sticky;top:0;z-index:10;background:var(--bg);display:flex;flex-wrap:wrap;gap:.3rem;
  padding:.7rem 0;margin-bottom:1rem;border-bottom:1px solid var(--border)}
nav a{color:var(--ink2);text-decoration:none;font:.7rem/1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;padding:.4rem .6rem;border-radius:6px}
nav a:hover{background:var(--card2);color:var(--ink)}
section{margin:2.2rem 0;scroll-margin-top:3.4rem}
.sub{color:var(--ink2);font-size:.85rem;margin:.2rem 0 1rem;max-width:70ch}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.1rem 1.2rem;margin-bottom:1rem}
.card-t{font:600 .72rem/1.2 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  margin-bottom:.7rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:740px){.grid2{grid-template-columns:1fr}}
.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}
.tick{fill:var(--muted);font:10px ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
.axt{fill:var(--ink2);font:600 11px ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
.ylab{fill:var(--ink2);font:11px ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
.err{stroke:var(--ink);stroke-opacity:.4;stroke-width:1.4}
.wh{stroke:var(--ink2);stroke-width:1.3}
.toggle{display:flex;flex-wrap:wrap;gap:.3rem;align-items:center}
.toggle .lb{font:600 10px/1 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:.2rem}
.toggle button{background:var(--card2);color:var(--ink2);border:1px solid var(--border);font:.7rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;
  padding:.28rem .6rem;border-radius:999px;cursor:pointer}
.toggle button[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.toggle button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select{background:var(--card2);color:var(--ink);border:1px solid var(--border);border-radius:6px;
  padding:.3rem .55rem;font:.7rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1rem;margin-top:.6rem;font:.7rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:.35rem}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.mult{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:.8rem}
.htab-wrap{overflow-x:auto}
.htab{width:100%;border-collapse:collapse;font:.72rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace}
.htab th{font-weight:400;color:var(--muted);font-size:.64rem;padding:.5rem .6rem;border-bottom:1px solid var(--border);white-space:nowrap}
.htab th.l,.htab td.l{text-align:left}.htab th:not(.l){text-align:center}
.htab td{padding:.45rem .6rem;text-align:center;white-space:nowrap}
.htab td.l{color:var(--ink)}
.htab td s{display:block;font-size:.56rem;opacity:.7;text-decoration:none}
.empty{color:var(--muted);font:.75rem ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;padding:.5rem 0}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:#f4f1ea;padding:.4rem .6rem;border-radius:6px;
  font:.68rem/1.35 ui-monospace,'Cascadia Code','JetBrains Mono',Consolas,monospace;box-shadow:0 8px 22px rgba(0,0,0,.28);transform:translate(-50%,-120%);opacity:0;
  transition:opacity .12s;z-index:100;max-width:280px;white-space:pre-line}
#tip.on{opacity:1}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

_BODY = r"""
<header>

  <div>
    <div class="kick">Experiment report</div>
    <h1>Mulita<span>Miner</span></h1>
  </div>
  <div class="meta" id="meta"></div>
</header>

<div class="hero">
  <div class="dark" id="verdict"></div>
  <div class="lite"><div class="card-t" id="vbTitle">Overall recall by model · mean across reports (±std)</div>
    <div id="verdictBars"></div></div>
</div>

<nav>
  <a href="#coverage">Coverage</a><a href="#consistency">By report</a>
  <a href="#fields">Field quality</a><a href="#omission">Omission</a>
  <a href="#dist">Distribution</a><a href="#errors">Errors &amp; cost</a>
</nav>

<section id="coverage">
  <div class="kick">Coverage</div>
  <h2>Precision × recall - where each model sits</h2>
  <p class="sub">Top-right = extracts everything (recall) without hallucinating (precision).
     Whiskers = spread across runs. Averaged over reports and runs.</p>
  <div class="card"><div class="card-t">Precision × Recall by model (±std)</div>
    <div id="scatter"></div><div class="legend" id="scLegend"></div></div>
</section>

<section id="consistency">
  <div class="kick">Consistency</div>
  <h2>Does the winner hold across reports?</h2>
  <p class="sub">One panel per report (recall by model). If the order changes panel to panel,
     the overall mean is hiding it.</p>
  <div class="mult" id="sm"></div>
  <div class="legend" id="smLegend"></div>
</section>

<section id="fields">
  <div class="kick">Field quality</div>
  <h2>Where each model gets fields right</h2>
  <p class="sub">Rows = fields, columns = reports - the whole picture at once. Mean per field,
     empty×empty pairs excluded; a field empty everywhere (baseline and extraction) is never scored
     and is listed below the table. Darker = better; color scale fit to the data.</p>
  <div class="card">
    <div class="card-t">Text fields · semantic similarity
      <span class="toggle" id="txtMetric"><span class="lb">Metric</span></span>
      <span id="fldModelWrap" style="margin-left:auto;display:none;gap:.4rem;align-items:center">
        <span class="lb" style="font:600 10px/1 monospace;color:var(--muted)">Model</span><select id="fldModel"></select></span>
    </div>
    <div class="htab-wrap"><table class="htab" id="txtHeat"></table></div>
    <div class="legend" id="txtLegend"></div>
  </div>
  <div class="card">
    <div class="card-t">Structured fields · deterministic match
      <span class="toggle" id="detMetric"><span class="lb">Metric</span></span>
    </div>
    <div class="htab-wrap"><table class="htab" id="detHeat"></table></div>
    <div class="legend" id="detLegend"></div>
  </div>
</section>

<section id="omission">
  <div class="kick">Omission</div>
  <h2>Which fields each model leaves empty</h2>
  <p class="sub">Proxy: fraction of pairs where the baseline fills the field and the extraction does not
     (baseline-filled − extraction-filled). Redder = more omitted.</p>
  <div class="card">
    <div class="card-t">Field omission
      <span style="margin-left:auto;display:flex;gap:.4rem;align-items:center">
        <span class="lb" style="font:600 10px/1 monospace;color:var(--muted)">Report</span><select id="omTarget"></select></span>
    </div>
    <div class="htab-wrap"><table class="htab" id="omheat"></table></div>
    <div class="legend" id="omLegend"></div>
  </div>
</section>

<section id="dist">
  <div class="kick">Distribution</div>
  <h2>How per-pair scores spread</h2>
  <p class="sub">Box plot: box = interquartile range, line = median, ticks = min/max. The stacked bar bins
     the same per-pair scores into similarity bands (a presentation choice, thresholds shown), plus
     Absent = baseline vulns never recovered.</p>
  <div class="card"><div class="card-t"><span class="toggle" id="distMetric"><span class="lb">Metric</span></span>
      <span style="margin-left:auto;display:flex;gap:.4rem;align-items:center">
        <span class="lb" style="font:600 10px/1 monospace;color:var(--muted)">Report</span><select id="distTarget"></select></span></div>
    <div id="distBox"></div>
    <div style="margin-top:1.2rem"><div class="card-t" style="margin-bottom:.5rem">Similarity categories · share of baseline
      <span style="text-transform:none;letter-spacing:0;color:var(--muted)">(High ≥0.90 · Moderate ≥0.80 · Slight ≥0.70 · Divergent &lt;0.70 · Absent = omitted)</span></div>
      <div id="distCat"></div><div class="legend" id="catLegend"></div></div>
  </div>
</section>

<section id="errors">
  <div class="kick">Errors &amp; cost</div>
  <h2>Where coverage fails, and at what cost</h2>
  <p class="sub">Per run, against the baseline (the gold): missed = baseline vulns not recovered
     (false negatives); false positives = extracted records with no baseline match.</p>
  <div class="card" id="paretoCard" style="display:none"><div class="card-t">Cost vs recall · Pareto (mean/run)</div>
    <div id="pareto"></div><div class="legend" id="paretoLegend"></div></div>
  <div class="card"><div class="card-t">Missed vs false positives by model (mean/run)</div>
    <div id="err"></div>
    <div class="legend"><span><span class="sw" style="background:var(--accent)"></span>Missed (FN)</span>
      <span><span class="sw" style="background:var(--muted)"></span>False positives (FP)</span></div></div>
  <div class="grid2" id="cost" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))"></div>
</section>
<div id="tip" role="tooltip"></div>
"""

_JS = r"""
const M=DATA.models,TGT=DATA.targets,OV=DATA.overall;
const PAL=['#2a78d6','#008300','#a24bb0','#0f9d9d','#4a3aa7','#c81d54','#7a6a00','#946037'];
const MC={};M.forEach((m,i)=>MC[m]=PAL[i%PAL.length]);
const pct=v=>v==null?'-':(v*100).toFixed(1)+'%';
const f3=v=>v==null?'-':v.toFixed(3);
const avg=a=>{const x=a.filter(v=>v!=null);return x.length?x.reduce((s,v)=>s+v,0)/x.length:null;};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const el=id=>document.getElementById(id);
const orec=m=>OV[m].recall.m;

const tip=el('tip');
document.addEventListener('mouseover',e=>{const t=e.target.closest('[data-tip]');if(t){tip.textContent=t.getAttribute('data-tip');tip.classList.add('on');}});
document.addEventListener('mousemove',e=>{if(tip.classList.contains('on')){tip.style.left=e.clientX+'px';tip.style.top=e.clientY+'px';}});
document.addEventListener('mouseout',e=>{if(e.target.closest('[data-tip]'))tip.classList.remove('on');});

function axis(padL,plotW,top,bottom,min,max){let s='';[0,.25,.5,.75,1].forEach(t=>{
  const v=min+(max-min)*t,x=padL+t*plotW;
  s+=`<line class="grid" x1="${x}" y1="${top}" x2="${x}" y2="${bottom}"/>`+
     `<text class="tick" x="${x}" y="${top-7}" text-anchor="middle">${v.toFixed(2)}</text>`;});return s;}

function hDot(rows,{W=760,rowH=28,padL=120,min=0,max=1,ticks=true}={}){
  const padR=40,top=ticks?30:12,plotW=W-padL-padR,H=top+rows.length*rowH+12,bottom=H-12;
  const X=v=>padL+((v-min)/(max-min))*plotW;let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  if(ticks)s+=axis(padL,plotW,top,bottom,min,max);
  else [0,.5,1].forEach(t=>{const x=padL+t*plotW;s+=`<line class="grid" x1="${x}" y1="${top}" x2="${x}" y2="${bottom}"/>`;});
  rows.forEach((r,i)=>{const y=top+i*rowH+rowH/2;
    s+=`<text class="ylab" x="${padL-10}" y="${y+4}" text-anchor="end">${esc(r.label)}</text>`;
    r.points.forEach(p=>{if(p.v==null)return;const cx=X(p.v);
      if(p.err)s+=`<line class="err" x1="${X(Math.max(min,p.v-p.err))}" y1="${y}" x2="${X(Math.min(max,p.v+p.err))}" y2="${y}"/>`;
      s+=`<circle cx="${cx}" cy="${y}" r="6" fill="${p.color}" data-tip="${esc(p.tip)}"/>`;});});
  return s+'</svg>';
}

function hBox(rows,{W=760,rowH=38,padL=120}={}){
  const padR=40,top=30,plotW=W-padL-padR,H=top+rows.length*rowH+12,bottom=H-12;
  const X=v=>padL+v*plotW;let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`+axis(padL,plotW,top,bottom,0,1);
  rows.forEach((r,i)=>{const y=top+i*rowH+rowH/2;
    s+=`<text class="ylab" x="${padL-10}" y="${y+4}" text-anchor="end">${esc(r.label)}</text>`;
    const b=r.box;if(!b){s+=`<text class="tick" x="${padL+6}" y="${y+4}">no data</text>`;return;}
    const bh=rowH*.46,tp=esc(`${r.label}\nmin ${b.min.toFixed(2)}  Q1 ${b.q1.toFixed(2)}  med ${b.med.toFixed(2)}  Q3 ${b.q3.toFixed(2)}  max ${b.max.toFixed(2)}\nn=${b.n} pairs`);
    s+=`<line class="wh" x1="${X(b.min)}" y1="${y}" x2="${X(b.q1)}" y2="${y}"/>`+
       `<line class="wh" x1="${X(b.q3)}" y1="${y}" x2="${X(b.max)}" y2="${y}"/>`+
       `<line class="wh" x1="${X(b.min)}" y1="${y-4}" x2="${X(b.min)}" y2="${y+4}"/>`+
       `<line class="wh" x1="${X(b.max)}" y1="${y-4}" x2="${X(b.max)}" y2="${y+4}"/>`+
       `<rect x="${X(b.q1)}" y="${y-bh/2}" width="${Math.max(1,X(b.q3)-X(b.q1))}" height="${bh}" rx="2" fill="${r.color}" fill-opacity=".28" stroke="${r.color}" data-tip="${tp}"/>`+
       `<line x1="${X(b.med)}" y1="${y-bh/2}" x2="${X(b.med)}" y2="${y+bh/2}" stroke="${r.color}" stroke-width="2.5"/>`;});
  return s+'</svg>';
}

// stacked horizontal bar (each row sums to ~1). rows:[{label,vals:[...]}], cats colors
function hStack(rows,cats,colors,{W=760,rowH=30,padL=120}={}){
  const padR=20,top=30,plotW=W-padL-padR,H=top+rows.length*rowH+12,bottom=H-12;
  const X=v=>padL+v*plotW;let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  [0,.25,.5,.75,1].forEach(t=>{s+=`<line class="grid" x1="${X(t)}" y1="${top}" x2="${X(t)}" y2="${bottom}"/>`+
    `<text class="tick" x="${X(t)}" y="${top-7}" text-anchor="middle">${(t*100).toFixed(0)}%</text>`;});
  rows.forEach((r,i)=>{const y=top+i*rowH+rowH*.2,bh=rowH*.55;
    s+=`<text class="ylab" x="${padL-10}" y="${y+bh/2+4}" text-anchor="end">${esc(r.label)}</text>`;
    let cum=0;r.vals.forEach((v,ci)=>{if(v<=0){return;}const x=X(cum),w=X(cum+v)-x;
      s+=`<rect x="${x}" y="${y}" width="${Math.max(0.5,w)}" height="${bh}" fill="${colors[ci]}" data-tip="${esc(r.label+' · '+cats[ci]+': '+(v*100).toFixed(1)+'%')}"/>`;cum+=v;});});
  return s+'</svg>';
}

function hBars(rows,{W=760,rowH=40,padL=120}={}){
  const padR=54,top=12,plotW=W-padL-padR,H=top+rows.length*rowH+12;
  const max=Math.max(1,...rows.flatMap(r=>r.bars.map(b=>b.v)));const X=v=>(v/max)*plotW;
  let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  rows.forEach((r,i)=>{const y0=top+i*rowH+6,n=r.bars.length,bh=(rowH-10)/n;
    s+=`<text class="ylab" x="${padL-10}" y="${y0+rowH/2-4}" text-anchor="end">${esc(r.label)}</text>`;
    r.bars.forEach((b,j)=>{const y=y0+j*bh,w=X(b.v);
      s+=`<rect x="${padL}" y="${y}" width="${Math.max(0,w)}" height="${bh-2}" rx="2" fill="${b.color}" data-tip="${esc(b.tip)}"/>`+
         `<text class="tick" x="${padL+w+5}" y="${y+bh/2+1}">${b.v.toFixed(1)}</text>`;});});
  return s+'</svg>';
}

function scatter(pts,{W=760,H=520,min=0.5}={}){
  const pad={t:16,r:20,b:48,l:56},plotW=W-pad.l-pad.r,plotH=H-pad.t-pad.b;
  const X=v=>pad.l+((v-min)/(1-min))*plotW,Y=v=>pad.t+plotH-((v-min)/(1-min))*plotH;
  let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  [0,.25,.5,.75,1].forEach(t=>{const v=min+(1-min)*t;
    s+=`<line class="grid" x1="${X(v)}" y1="${pad.t}" x2="${X(v)}" y2="${pad.t+plotH}"/>`+
       `<line class="grid" x1="${pad.l}" y1="${Y(v)}" x2="${pad.l+plotW}" y2="${Y(v)}"/>`+
       `<text class="tick" x="${X(v)}" y="${pad.t+plotH+16}" text-anchor="middle">${v.toFixed(2)}</text>`+
       `<text class="tick" x="${pad.l-8}" y="${Y(v)+3}" text-anchor="end">${v.toFixed(2)}</text>`;});
  s+=`<text class="axt" x="${pad.l+plotW/2}" y="${H-8}" text-anchor="middle">Precision →</text>`+
     `<text class="axt" x="${-(pad.t+plotH/2)}" y="14" text-anchor="middle" transform="rotate(-90)">Recall →</text>`;
  pts.forEach(p=>{if(p.x==null||p.y==null)return;const cx=X(p.x),cy=Y(p.y);
    if(p.ex)s+=`<line class="err" x1="${X(Math.max(min,p.x-p.ex))}" y1="${cy}" x2="${X(Math.min(1,p.x+p.ex))}" y2="${cy}"/>`;
    if(p.ey)s+=`<line class="err" x1="${cx}" y1="${Y(Math.max(min,p.y-p.ey))}" x2="${cx}" y2="${Y(Math.min(1,p.y+p.ey))}"/>`;
    s+=`<circle cx="${cx}" cy="${cy}" r="8" fill="${p.color}" fill-opacity=".85" stroke="${p.color}" data-tip="${esc(p.label+'\nprecision '+f3(p.x)+' · recall '+f3(p.y))}"/>`+
       `<text x="${cx+11}" y="${cy+3}" class="ylab" style="font-size:10px">${esc(p.label)}</text>`;});
  return s+'</svg>';
}

// sequential color: v mapped from [min,max] to cream -> deep hue (green good, red bad).
function ramp(v,min,max,hue){const t=Math.max(0,Math.min(1,(v-min)/(max-min)));const L=(a,b)=>Math.round(a+(b-a)*t);
  const to=hue==='red'?[176,26,69]:[26,94,99];
  return{bg:`rgb(${L(244,to[0])},${L(241,to[1])},${L(234,to[2])})`,tx:t>0.5?'#faf8f2':'#1a1a17'};}

function heatTable(tableId,fields,getCell,colorFn){
  const tbl=el(tableId);
  if(!fields.length){tbl.innerHTML='<tbody><tr><td class="empty">no data</td></tr></tbody>';return;}
  let h=`<thead><tr><th class="l">Field</th>${M.map(m=>`<th><span class="dot" style="width:7px;height:7px;background:${MC[m]};margin-right:4px"></span>${esc(m)}</th>`).join('')}<th>Avg</th></tr></thead><tbody>`;
  fields.forEach(f=>{h+=`<tr><td class="l">${esc(f)}</td>`;const row=[];
    M.forEach(m=>{const d=getCell(f,m),v=d.m;if(v==null){h+=`<td>-</td>`;return;}row.push(v);const c=colorFn(v);
      h+=`<td style="background:${c.bg};color:${c.tx}">${v.toFixed(2)}<s>±${(d.s||0).toFixed(2)}</s></td>`;});
    const a=avg(row),ac=a==null?null:colorFn(a);
    h+=a==null?`<td>-</td></tr>`:`<td style="background:${ac.bg};color:${ac.tx};font-weight:700">${a.toFixed(2)}</td></tr>`;});
  tbl.innerHTML=h+'</tbody>';
}

function legend(id,items){el(id).innerHTML=items.map(([l,c])=>
  `<span><span class="sw" style="background:${c}"></span>${esc(l)}</span>`).join('');}
function toggle(id,opts,active,cb){const h=el(id);
  h.querySelectorAll('button').forEach(b=>b.remove());
  h.insertAdjacentHTML('beforeend',opts.map(o=>`<button data-v="${o}" aria-pressed="${o===active}">${o}</button>`).join(''));
  h.querySelectorAll('button').forEach(b=>b.onclick=()=>{h.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));cb(b.dataset.v);});}
function fillSel(id,opts,onch){const s=el(id);s.innerHTML=opts.map(o=>`<option value="${o}">${o}</option>`).join('');s.onchange=()=>onch(s.value);}

// ---- meta ----
const T=DATA.totals,C=DATA.config;
const fmtDur=s=>{s=Math.round(s);if(s<90)return s+'s';const h=Math.floor(s/3600),m=Math.round((s%3600)/60);return h?`${h}h ${m}m`:`${m}m ${s%60}s`;};
el('meta').innerHTML=[['models',M.length],['reports',TGT.length],['runs',C.runs],
  ['done',`${T.done}/${T.planned}`],['cost',`$${T.cost_usd.toFixed(4)}`],
  ['time',fmtDur(T.active_seconds)]].map(([k,v])=>`<span>${k} <b>${v}</b></span>`).join('');

// ---- verdict ----
const ranked=[...M].filter(m=>orec(m)!=null).sort((a,b)=>orec(b)-orec(a));
if(!ranked.length){el('verdict').innerHTML='<div class="l">no coverage evaluated</div>';}
else if(M.length===1){const m=ranked[0],o=OV[m],c=MC[m];
  el('verdict').innerHTML=`<div><div class="l">Model under test</div>
    <div class="win"><span class="dot" style="background:${c}"></span>${esc(m)}</div></div>
    <div><div class="big" style="color:${c}">${orec(m).toFixed(3)}</div>
    <div class="sub">mean recall · ranking view appears with 2+ models</div></div>`;
  el('vbTitle').textContent='Model summary · mean across reports (±std)';
  const rows=[['recall',pct(o.recall.m),'±'+pct(o.recall.s)],['precision',pct(o.precision.m),'±'+pct(o.precision.s)],
    ['missed / run',(o.missed.m??0).toFixed(1),'±'+(o.missed.s??0).toFixed(1)],
    ['false pos / run',(o.spurious.m??0).toFixed(1),'±'+(o.spurious.s??0).toFixed(1)],
    ['cost / run',o.cost.m!=null?'$'+o.cost.m.toFixed(4):'-',''],
    ['time / run',o.duration.m!=null?fmtDur(o.duration.m):'-','']];
  el('verdictBars').innerHTML='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:.7rem .9rem">'+
    rows.map(([k,v,s])=>`<div><div style="font:600 9px/1 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:.3rem">${k}</div>
      <div style="font:700 .95rem ui-monospace,monospace">${v} <span style="font-weight:400;font-size:.6rem;color:var(--muted)">${s}</span></div></div>`).join('')+'</div>';
}else{const win=ranked[0],c=MC[win],delta=orec(win)-orec(ranked[1]);
  el('verdict').innerHTML=`<div><div class="l">Best model · overall recall</div>
    <div class="win"><span class="dot" style="background:${c}"></span>${esc(win)}</div></div>
    <div><div class="big" style="color:${c}">${orec(win).toFixed(3)}</div>
    <div class="sub">mean recall · +${delta.toFixed(3)} ahead of ${esc(ranked[1])}</div></div>`;
  el('verdictBars').innerHTML=ranked.map(m=>{const v=orec(m),s=OV[m].recall.s||0;
    return `<div class="brow"><span class="nm">${esc(m)}</span>
      <div class="track"><div class="fill" style="width:${(v*100).toFixed(1)}%;background:${MC[m]}"></div></div>
      <span class="vv">${v.toFixed(3)} <s>±${s.toFixed(3)}</s></span></div>`;}).join('');}

// ---- scatter ----
(function(){const vals=M.flatMap(m=>[OV[m].recall.m,OV[m].precision.m]).filter(v=>v!=null);
  const lo=vals.length?Math.max(0,Math.floor((Math.min(...vals)-0.06)*10)/10):0.5;
  el('scatter').innerHTML=scatter(M.map(m=>({x:OV[m].precision.m,y:OV[m].recall.m,
    ex:OV[m].precision.s,ey:OV[m].recall.s,color:MC[m],label:m})),{min:lo});
  legend('scLegend',M.map(m=>[m,MC[m]]));})();

// ---- small multiples ----
el('sm').innerHTML=TGT.map(t=>{
  const rows=[...M].sort((a,b)=>(DATA.by_target[t][b].recall.m??-1)-(DATA.by_target[t][a].recall.m??-1))
    .map(m=>({label:m,points:[{v:DATA.by_target[t][m].recall.m,err:DATA.by_target[t][m].recall.s,color:MC[m],
      tip:`${m} @ ${t}\nrecall ${pct(DATA.by_target[t][m].recall.m)} ±${((DATA.by_target[t][m].recall.s||0)*100).toFixed(1)}`}]}));
  return `<div class="card"><div class="card-t">${esc(t)}</div>${hDot(rows,{W:520,padL:110,rowH:24,ticks:false})}</div>`;
}).join('')||'<div class="empty">no reports evaluated</div>';
legend('smLegend',M.map(m=>[m,MC[m]]));

// ---- field quality: fields × reports, per family ----
const shortT=tg=>{const sc=(DATA.scanners||{})[tg]||'';const pre=/tenable/i.test(sc)?'TN':'OV';
  let n=tg.replace(/^(openvas|tenable(was)?)[_-]/i,'').replace(/[_-]?v?\d+(\.\d+)*$/,'');
  return pre+'·'+n;};
function fieldHeat(tblId,legId,fields,block,metric,model){
  const tbl=el(tblId),cellOf=(f,tg)=>{const c=block[metric]&&block[metric][tg];return (c&&c[f]&&c[f][model])?c[f][model]:{m:null,s:0};};
  const scored=fields.filter(f=>TGT.some(tg=>cellOf(f,tg).m!=null));
  const unscored=fields.filter(f=>!scored.includes(f));
  if(!scored.length){tbl.innerHTML='<tbody><tr><td class="empty">no data</td></tr></tbody>';el(legId).innerHTML='';return;}
  const vals=scored.flatMap(f=>TGT.map(tg=>cellOf(f,tg).m)).filter(v=>v!=null);
  let lo=Math.min(...vals),hi=Math.max(...vals);
  lo=Math.max(0,Math.floor((lo-0.02)*50)/50);hi=Math.min(1,Math.ceil(hi*50)/50);
  if(hi-lo<0.1)lo=Math.max(0,hi-0.1);
  const cf=v=>ramp(v,lo,hi,'green');
  let h='<thead><tr><th class="l">Field</th>'+TGT.map(tg=>`<th title="${esc(tg)}">${esc(shortT(tg))}</th>`).join('')+'<th>Avg</th></tr></thead><tbody>';
  scored.forEach(f=>{h+=`<tr><td class="l">${esc(f)}</td>`;const row=[];
    TGT.forEach(tg=>{const d=cellOf(f,tg),v=d.m;
      if(v==null){h+='<td style="color:var(--muted)" title="not scored: empty in baseline and extraction">·</td>';return;}
      row.push(v);const c=cf(v);
      h+=`<td style="background:${c.bg};color:${c.tx}">${v.toFixed(2)}<s>±${(d.s||0).toFixed(2)}</s></td>`;});
    const a=avg(row),ac=cf(a);
    h+=`<td style="background:${ac.bg};color:${ac.tx};font-weight:700">${a.toFixed(2)}</td></tr>`;});
  if(unscored.length)h+=`<tr><td class="empty" colspan="${TGT.length+2}" style="text-align:left;padding:.5rem .6rem">not scored (empty in baseline and extraction everywhere): ${unscored.map(esc).join(', ')}</td></tr>`;
  tbl.innerHTML=h+'</tbody>';
  el(legId).innerHTML=`<span style="color:var(--muted)">${lo.toFixed(2)}</span>
    <span style="width:150px;height:11px;border-radius:3px;background:linear-gradient(90deg,rgb(244,241,234),rgb(26,94,99));display:inline-block"></span>
    <span style="color:var(--muted)">${hi.toFixed(2)} · darker = better · scale fit to data</span>`;
}
(function(){let model=M[0],txtM=DATA.text_metrics[0],detM=DATA.det_metrics[0];
  const render=()=>{fieldHeat('txtHeat','txtLegend',DATA.sem_fields,DATA.text_fields,txtM,model);
    fieldHeat('detHeat','detLegend',DATA.det_fields,DATA.det_field_block,detM,model);};
  toggle('txtMetric',DATA.text_metrics,txtM,v=>{txtM=v;render();});
  toggle('detMetric',DATA.det_metrics,detM,v=>{detM=v;render();});
  if(M.length>1){el('fldModelWrap').style.display='flex';fillSel('fldModel',M,v=>{model=v;render();});}
  render();})();

// ---- omission heatmap ----
(function(){let target=TGT[0]||null;
  function render(){const cell=target?DATA.omission[target]:null;
    const val=f=>avg(M.map(m=>(cell&&cell[f])?cell[f][m].m:null));
    const nz=DATA.omit_fields.filter(f=>(val(f)||0)>0.005).sort((a,b)=>val(b)-val(a));
    const zn=DATA.omit_fields.length-nz.length;
    if(!nz.length){el('omheat').innerHTML=`<tbody><tr><td class="empty">No omission - all ${DATA.omit_fields.length} fields fully populated for this report.</td></tr></tbody>`;el('omLegend').innerHTML='';return;}
    heatTable('omheat',nz,(f,m)=>(cell&&cell[f])?cell[f][m]:{m:null,s:0},v=>ramp(v,0,0.4,'red'));
    if(zn)el('omheat').insertAdjacentHTML('beforeend',`<tbody><tr><td class="empty" colspan="${M.length+2}" style="padding:.5rem .6rem;text-align:left">+ ${zn} field${zn>1?'s':''} with no omission (hidden)</td></tr></tbody>`);
    el('omLegend').innerHTML=`<span style="color:var(--muted)">0.00</span>
      <span style="width:150px;height:11px;border-radius:3px;background:linear-gradient(90deg,rgb(244,241,234),rgb(176,26,69));display:inline-block"></span>
      <span style="color:var(--muted)">higher · redder = more omitted</span>`;}
  fillSel('omTarget',TGT,v=>{target=v;render();});
  render();})();

// ---- distribution: box + category stack ----
(function(){let metric=DATA.text_metrics[0]||null,target='__all__';
  const CATS=['High','Moderate','Slight','Divergent','Absent'];
  const CC=['#0a6b0a','#7a9a2f','#d9a200','#c81d54','#b8b4a8'];
  const DBT=DATA.dist_by_target||null,CBT=DATA.dist_cat_by_target||null;
  const box=m=>(target!=='__all__'&&DBT&&DBT[metric]&&DBT[metric][target])?DBT[metric][target][m]:DATA.dist[metric][m];
  const cat=m=>(target!=='__all__'&&CBT&&CBT[metric]&&CBT[metric][target])?CBT[metric][target][m]:DATA.dist_cat[metric][m];
  function render(){if(!metric){el('distBox').innerHTML='<div class="empty">no per-pair scores</div>';el('distCat').innerHTML='';return;}
    el('distBox').innerHTML=hBox(M.map(m=>({label:m,box:box(m),color:MC[m]})));
    el('distCat').innerHTML=hStack(M.map(m=>({label:m,vals:cat(m)||[]})),CATS,CC);
    legend('catLegend',CATS.map((c,i)=>[c,CC[i]]));}
  const sel=el('distTarget');
  if(DBT){sel.innerHTML='<option value="__all__">all reports</option>'+TGT.map(t=>`<option value="${t}">${t}</option>`).join('');
    sel.onchange=()=>{target=sel.value;render();};}
  else{sel.outerHTML='<span style="font:.65rem ui-monospace,monospace;color:var(--muted)">all reports pooled - per-report split needs <b>dist_by_target</b> in the JSON export</span>';}
  if(DATA.text_metrics.length)toggle('distMetric',DATA.text_metrics,metric,v=>{metric=v;render();});
  render();})();

// ---- errors + cost ----
if(M.length>1){el('paretoCard').style.display='';
  const cmax=Math.max(...M.map(m=>OV[m].cost.m||0))*1.15||1;
  const recs=M.map(m=>orec(m)).filter(v=>v!=null);
  const rlo=Math.max(0,Math.floor((Math.min(...recs)-0.03)*20)/20);
  const W=760,H=380,pad={t:16,r:20,b:48,l:56},pw=W-pad.l-pad.r,ph=H-pad.t-pad.b;
  const X=v=>pad.l+(v/cmax)*pw,Y=v=>pad.t+ph-((v-rlo)/(1-rlo))*ph;
  let s=`<svg viewBox="0 0 ${W} ${H}" class="chart">`;
  [0,.25,.5,.75,1].forEach(t=>{s+=`<line class="grid" x1="${pad.l+t*pw}" y1="${pad.t}" x2="${pad.l+t*pw}" y2="${pad.t+ph}"/><text class="tick" x="${pad.l+t*pw}" y="${pad.t+ph+16}" text-anchor="middle">$${(t*cmax).toFixed(3)}</text>`;
    const rv=rlo+(1-rlo)*t;s+=`<line class="grid" x1="${pad.l}" y1="${Y(rv)}" x2="${pad.l+pw}" y2="${Y(rv)}"/><text class="tick" x="${pad.l-8}" y="${Y(rv)+3}" text-anchor="end">${rv.toFixed(2)}</text>`;});
  s+=`<text class="axt" x="${pad.l+pw/2}" y="${H-8}" text-anchor="middle">Cost per run →</text><text class="axt" x="${-(pad.t+ph/2)}" y="14" text-anchor="middle" transform="rotate(-90)">Recall →</text>`;
  M.forEach(m=>{const c=OV[m].cost.m,r=orec(m);if(c==null||r==null)return;
    s+=`<circle cx="${X(c)}" cy="${Y(r)}" r="8" fill="${MC[m]}" fill-opacity=".85" stroke="${MC[m]}" data-tip="${esc(m+'\ncost $'+c.toFixed(4)+'/run · recall '+f3(r))}"/><text x="${X(c)+11}" y="${Y(r)+3}" class="ylab" style="font-size:10px">${esc(m)}</text>`;});
  el('pareto').innerHTML=s+'</svg>';legend('paretoLegend',M.map(m=>[m,MC[m]]));}
el('err').innerHTML=hBars(M.map(m=>({label:m,bars:[
  {v:OV[m].missed.m??0,color:'var(--accent)',tip:`${m} · missed ${(OV[m].missed.m??0).toFixed(1)}/run`},
  {v:OV[m].spurious.m??0,color:'var(--muted)',tip:`${m} · false positives ${(OV[m].spurious.m??0).toFixed(1)}/run`}]})));
el('cost').innerHTML=M.map(m=>{const c=OV[m].cost.m,d=OV[m].duration.m;
  return `<div class="card" style="margin:0"><div class="card-t" style="margin:0 0 .4rem">${esc(m)}</div>
    <div style="font:700 1.05rem ui-monospace,monospace;color:${MC[m]}">${c?'$'+c.toFixed(4):'-'}</div>
    <div style="font:.65rem ui-monospace,monospace;color:var(--muted)">${d!=null?Math.round(d)+'s/run':''}</div></div>`;}).join('');
"""

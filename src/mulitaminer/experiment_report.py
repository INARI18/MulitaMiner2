"""Self-contained interactive HTML report for an experiment tree.

Reads experiment.json plus each run's evaluation.json, embeds an aggregated
DATA object, and renders an offline dashboard with inline vanilla JS (no
external assets, no dependencies). Styled after the project's cream/orange
deck; model series use the dataviz reference categorical palette (orange is
reserved for brand chrome, never a series).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Per-field primary metric (first present) used for the field dot summary.
_METRIC_PRIORITY = ("exact", "set_f1", "set_f1_ids", "structural", "token_f1",
                    "rouge_l", "bertscore", "nli")


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _aggregate(experiment_dir: Path) -> dict:
    manifest = json.loads((experiment_dir / "experiment.json").read_text(encoding="utf-8"))
    models = manifest["config"]["models"]

    # cov[(scanner, model)] -> {"recall":[], "precision":[], "missed":[], "spurious":[]}
    cov: dict = defaultdict(lambda: {"recall": [], "precision": [], "missed": [],
                                     "spurious": [], "cost": [], "duration": []})
    # field_scores[(field, model, metric)] -> [measured_mean...]
    field_scores: dict = defaultdict(list)
    # fill gap (omission proxy) per (field, model)
    fill_gap: dict = defaultdict(list)
    metrics_seen: set = set()
    scanners: set = set()

    for r in manifest["runs"]:
        if r["status"] not in ("ok", "cached"):
            continue
        key = (r["scanner"], r["model"])
        scanners.add(r["scanner"])
        c = cov[key]
        cv = r.get("coverage")
        if cv:
            c["recall"].append(cv["recall"])
            c["precision"].append(cv["precision"])
            c["missed"].append(len(cv.get("missed", [])))
            c["spurious"].append(len(cv.get("spurious", [])))
        if "cost_usd" in r:
            c["cost"].append(r["cost_usd"])
        if "duration_s" in r:
            c["duration"].append(r["duration_s"])
        ep = Path(r["run_dir"]) / "evaluation.json"
        if ep.is_file():
            fields = json.loads(ep.read_text(encoding="utf-8")).get("fields", {})
            for field, ms in fields.items():
                for metric, st in ms.items():
                    if st.get("n_measured"):
                        field_scores[(field, r["model"], metric)].append(
                            st.get("measured_mean", st.get("mean")))
                        metrics_seen.add(metric)
                    fb = st.get("fill_rate_baseline")
                    fe = st.get("fill_rate_extraction")
                    if fb is not None and fe is not None:
                        fill_gap[(field, r["model"])].append(max(0.0, fb - fe))

    scanners = sorted(scanners)
    fields_all = sorted({f for (f, _m, _mt) in field_scores} | {f for (f, _m) in fill_gap})

    # KPI: recall, precision, mean field score, cost/run — per model.
    def _kpi(fn):
        return {m: fn(m) for m in models}

    def _cov_mean(m, key):
        vals = [v for (s, mm), c in cov.items() if mm == m for v in c[key]]
        return _mean(vals)

    def _text_mean(m):
        # mean of measured means across text-ish metrics
        vals = [v for (f, mm, mt), lst in field_scores.items()
                if mm == m and mt in ("token_f1", "rouge_l", "bertscore") for v in lst]
        return _mean(vals)

    kpi = [
        {"id": "recall", "label": "Recall", "fmt": "pct", "direction": 1,
         "values": _kpi(lambda m: _cov_mean(m, "recall"))},
        {"id": "precision", "label": "Precision", "fmt": "pct", "direction": 1,
         "values": _kpi(lambda m: _cov_mean(m, "precision"))},
        {"id": "text", "label": "Texto (média)", "fmt": "pct", "direction": 1,
         "values": _kpi(_text_mean)},
        {"id": "cost", "label": "Custo / run", "fmt": "usd", "direction": -1,
         "values": _kpi(lambda m: _cov_mean(m, "cost"))},
    ]

    # Scatter: per (scanner, model) — halluc = 1-precision, omission = 1-recall.
    scatter = []
    for (scanner, model), c in cov.items():
        rec, prec = _mean(c["recall"]), _mean(c["precision"])
        if rec is None or prec is None:
            continue
        scatter.append({
            "scanner": scanner, "model": model,
            "halluc": round(1 - prec, 4), "omission": round(1 - rec, 4),
            "missed": round(_mean(c["missed"]) or 0, 1),
            "spurious": round(_mean(c["spurious"]) or 0, 1),
        })

    # Field table: {metric: {field: {model: mean}}}
    fields_by_metric: dict = defaultdict(lambda: defaultdict(dict))
    for (field, model, metric), lst in field_scores.items():
        fields_by_metric[metric][field][model] = round(_mean(lst), 4)

    # Heatmap: {field: {model: fill_gap mean}}
    heatmap: dict = defaultdict(dict)
    for (field, model), lst in fill_gap.items():
        heatmap[field][model] = round(_mean(lst), 4)

    # Coverage table rows.
    coverage_rows = []
    for model in models:
        coverage_rows.append({
            "model": model,
            "recall": _cov_mean(model, "recall"),
            "precision": _cov_mean(model, "precision"),
            "missed": _cov_mean(model, "missed"),
            "spurious": _cov_mean(model, "spurious"),
        })

    cost_rows = [{"model": m, "cost": _cov_mean(m, "cost"),
                  "duration": _cov_mean(m, "duration")} for m in models]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": manifest["config"], "totals": manifest["totals"],
        "models": models, "scanners": scanners, "fields": fields_all,
        "metrics": [mt for mt in _METRIC_PRIORITY if mt in metrics_seen]
                   + sorted(metrics_seen - set(_METRIC_PRIORITY)),
        "kpi": kpi, "coverage_rows": coverage_rows, "scatter": scatter,
        "fields_by_metric": fields_by_metric, "heatmap": heatmap,
        "cost_rows": cost_rows,
    }


def build_report(experiment_dir: Path, out_path: Path | None = None) -> Path:
    data = _aggregate(experiment_dir)
    out_path = out_path or (experiment_dir / "report.html")
    doc = (f"<!doctype html><html lang=pt-BR><meta charset=utf-8>"
           f"<meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>MulitaMiner — experiment report</title>"
           f"<style>{_CSS}</style>{_BODY}"
           f"<script>const DATA={json.dumps(data, ensure_ascii=False)};{_JS}</script>"
           f"</html>")
    out_path.write_text(doc, encoding="utf-8")
    return out_path


_BODY = """
<main class="viz-root">
<header>
  <div class="kicker">Experiment report</div>
  <h1>MulitaMiner</h1>
  <dl class="meta" id="meta"></dl>
</header>
<nav class="nav">
  <a href="#kpi">KPIs</a><a href="#coverage">Cobertura</a>
  <a href="#tradeoff">Halluc × Omiss</a><a href="#fields">Campos</a>
  <a href="#heatmap">Heatmap</a><a href="#cost">Custo</a>
</nav>
<section id="kpi"><div class="kicker">Headline</div><h2>Por modelo</h2>
  <div class="kpi-grid" id="kpi-grid"></div></section>
<section id="coverage"><div class="kicker">Cobertura</div><h2>Recall, precision, perdas</h2>
  <p class="note">Média entre relatórios e runs. Missed = vulns do baseline não recuperadas; spurious = extraídas sem par.</p>
  <div class="table-wrap"><table id="t-coverage"></table></div></section>
<section id="tradeoff"><div class="kicker">Trade-off</div><h2>Hallucination × Omission</h2>
  <p class="note">Por (modelo, relatório): x = 1−precision, y = 1−recall. Ideal = canto inferior-esquerdo.</p>
  <div class="filters" id="scatter-filters"><span class="filter-label">Scanner</span></div>
  <div class="chart-card"><svg id="scatter" viewBox="0 0 760 460" role="img"></svg></div></section>
<section id="fields"><div class="kicker">Qualidade por campo</div><h2>Média medida por campo × modelo</h2>
  <p class="note">Pares vazio×vazio excluídos. Alterne a métrica; célula vazia = campo não usa aquela métrica.</p>
  <div class="filters" id="field-metric-filters"><span class="filter-label">Métrica</span></div>
  <div class="table-wrap"><table id="t-fields"></table></div></section>
<section id="heatmap"><div class="kicker">Omissão por campo</div><h2>Lacuna de preenchimento</h2>
  <p class="note">Fração média onde o baseline preenche o campo e a extração não (proxy de omissão). Mais vermelho = mais omitido.</p>
  <div class="chart-card"><svg id="heatmap-svg" viewBox="0 0 760 480" role="img"></svg></div></section>
<section id="cost"><div class="kicker">Custo & latência</div><h2>Por run</h2>
  <div class="chart-card"><svg id="cost-svg" viewBox="0 0 760 220" role="img"></svg></div></section>
</main>
<div class="tooltip" id="tooltip" role="tooltip" aria-hidden="true"></div>
"""

_CSS = """
:root{color-scheme:light dark}
.viz-root{--page:#f4f1ea;--card:#faf8f2;--card2:#efece3;--ink:#1a1a17;--ink2:#52514e;
  --muted:#8a887f;--accent:#d9541e;--grid:#e6e3da;--baseline:#cfccc2;--border:#e2ded4;
  --s0:#2a78d6;--s1:#008300;--s2:#e87ba4;--s3:#eda100;--s4:#4a3aa7;--s5:#e34948;--s6:#1baf7a;
  --pos:#0ca30c;--neg:#d03b3b;
  background:var(--page);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  font-variant-numeric:tabular-nums;max-width:1000px;margin:0 auto;padding:32px 24px 64px;}
@media(prefers-color-scheme:dark){:root:where(:not([data-theme=light])) .viz-root{
  --page:#14130f;--card:#1c1b16;--card2:#232219;--ink:#f4f1ea;--ink2:#c3c2b7;--muted:#8a887f;
  --accent:#eb6834;--grid:#2c2c26;--baseline:#3a3932;--border:#2c2b24;
  --s0:#3987e5;--s1:#008300;--s2:#d55181;--s3:#c98500;--s4:#9085e9;--s5:#e66767;--s6:#199e70;}}
:root[data-theme=dark] .viz-root{--page:#14130f;--card:#1c1b16;--card2:#232219;--ink:#f4f1ea;
  --ink2:#c3c2b7;--accent:#eb6834;--grid:#2c2c26;--baseline:#3a3932;--border:#2c2b24;
  --s0:#3987e5;--s1:#008300;--s2:#d55181;--s3:#c98500;--s4:#9085e9;--s5:#e66767;--s6:#199e70;}
.kicker{font:600 11px/1 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px}
h1{font-size:40px;margin:0 0 18px;letter-spacing:-.02em}
h2{font-size:19px;margin:0 0 4px}
header{border-bottom:2px solid var(--accent);padding-bottom:18px;margin-bottom:8px}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:12px 20px;margin:0}
.meta div{margin:0}.meta dt{font:600 10px/1.4 ui-monospace,monospace;text-transform:uppercase;
  letter-spacing:.08em;color:var(--muted)}
.meta dd{margin:2px 0 0;font-weight:600}
.nav{position:sticky;top:0;z-index:5;display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 24px;
  padding:8px 0;background:var(--page);border-bottom:1px solid var(--border)}
.nav a{color:var(--ink2);text-decoration:none;font-size:12px;padding:5px 9px;border-radius:6px}
.nav a:hover{background:var(--card2);color:var(--ink)}
section{margin-bottom:40px;scroll-margin-top:56px}
.note{color:var(--ink2);font-size:13px;margin:2px 0 12px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px}
.kpi-card .label{font:600 11px/1 ui-monospace,monospace;text-transform:uppercase;
  letter-spacing:.08em;color:var(--muted);margin-bottom:12px}
.kpi-row{display:grid;grid-template-columns:70px 1fr auto;gap:6px 10px;align-items:center;margin-bottom:5px}
.kpi-row .m{font-size:12px;font-weight:600;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-row .bar{height:6px;background:var(--card2);border-radius:3px;overflow:hidden}
.kpi-row .bar>span{display:block;height:100%;border-radius:3px}
.kpi-row .v{font-size:13px;font-weight:600;text-align:right;min-width:4ch}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 14px;text-align:left}
thead th{background:var(--card2);color:var(--ink2);font:600 11px/1 ui-monospace,monospace;
  text-transform:uppercase;letter-spacing:.06em;position:sticky;top:0}
td.num{text-align:right}
tbody tr{border-top:1px solid var(--border)}
tbody tr:hover{background:var(--card2)}
.sw{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-1px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.chart-card svg{width:100%;height:auto;display:block}
.grid line{stroke:var(--grid);stroke-width:1}
.axis text{fill:var(--muted);font:10px ui-monospace,monospace}
.axis-label{fill:var(--ink2);font:600 12px system-ui;}
.pt{cursor:pointer;transition:stroke-width .15s}.pt:hover{stroke-width:3}
.bar-rect{cursor:pointer}.bar-rect:hover{opacity:.85}
.hm-cell{stroke:var(--card);stroke-width:1;cursor:pointer}.hm-cell:hover{stroke:var(--ink);stroke-width:2}
.zone{fill:color-mix(in srgb,var(--pos) 8%,transparent);stroke:color-mix(in srgb,var(--pos) 30%,transparent);
  stroke-dasharray:4 4}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.filter-label{font:600 11px/1 ui-monospace,monospace;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);margin-right:6px}
.filters button{background:var(--card2);color:var(--ink2);border:1px solid var(--border);font:inherit;
  font-size:13px;padding:6px 12px;border-radius:999px;cursor:pointer}
.filters button[aria-pressed=true]{background:color-mix(in srgb,var(--accent) 18%,var(--card2));
  border-color:var(--accent);color:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:4px 0 12px;font-size:12px;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center}
.tooltip{position:fixed;pointer-events:none;background:var(--card);color:var(--ink);padding:8px 12px;
  border-radius:8px;border:1px solid var(--baseline);font-size:12px;line-height:1.4;
  box-shadow:0 8px 24px rgba(0,0,0,.25);transform:translate(-50%,-115%);opacity:0;transition:opacity .15s;
  z-index:100;min-width:150px}
.tooltip.on{opacity:1}
.tt-title{font-weight:700;margin-bottom:4px}
.tt-row{display:flex;justify-content:space-between;gap:14px}
.tt-row .k{color:var(--muted)}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

_JS = r"""
const S=["--s0","--s1","--s2","--s3","--s4","--s5","--s6"];
const css=v=>getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(v).trim();
const color=i=>css(S[i%S.length]);
const pct=v=>v==null?"—":(v*100).toFixed(1)+"%";
const usd=v=>v==null?"—":"$"+v.toFixed(4);
const num=v=>v==null?"—":(Math.abs(v)>=10?v.toFixed(1):v.toFixed(2));
const NS="http://www.w3.org/2000/svg";
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const models=DATA.models;
const tip=document.getElementById("tooltip");
function showTip(h,e){tip.innerHTML=h;tip.style.left=e.clientX+"px";tip.style.top=e.clientY+"px";tip.classList.add("on");}
function moveTip(e){tip.style.left=e.clientX+"px";tip.style.top=e.clientY+"px";}
function hideTip(){tip.classList.remove("on");}

/* meta */
const t=DATA.totals,c=DATA.config;
document.getElementById("meta").innerHTML=[
  ["modelos",models.join(", ")],["relatórios",c.reports.length],["runs cada",c.runs],
  ["completos",t.done+"/"+t.planned],["tempo ativo",Math.round(t.active_seconds)+"s"],
  ["custo","$"+t.cost_usd.toFixed(4)],["gerado",DATA.generated_at]
].map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

/* legend helper */
function legend(host){host.innerHTML=models.map((m,i)=>
  `<span><span class="sw" style="background:${color(i)}"></span>${m}</span>`).join("");}

/* KPI cards */
document.getElementById("kpi-grid").innerHTML=DATA.kpi.map(k=>{
  const vals=models.map(m=>k.values[m]).filter(v=>v!=null);
  const mx=k.fmt==="usd"?(vals.length?Math.max(...vals):1):1;
  const rows=models.map((m,i)=>{
    const v=k.values[m];const sc=v==null?0:Math.max(0,Math.min(1,mx?v/mx:0));
    const disp=v==null?"—":k.fmt==="usd"?usd(v):pct(v);
    return `<div class="kpi-row"><span class="m">${m}</span>
      <div class="bar"><span style="width:${(sc*100).toFixed(1)}%;background:${color(i)}"></span></div>
      <span class="v">${disp}</span></div>`;
  }).join("");
  return `<div class="kpi-card"><div class="label">${k.label}</div>${rows}</div>`;
}).join("");

/* Coverage table */
(function(){
  const head=`<thead><tr><th>Modelo</th><th class=num>Recall</th><th class=num>Precision</th>
    <th class=num>Missed</th><th class=num>Spurious</th></tr></thead>`;
  const body="<tbody>"+DATA.coverage_rows.map((r,i)=>
    `<tr><td><span class="sw" style="background:${color(i)}"></span>${r.model}</td>
     <td class=num>${pct(r.recall)}</td><td class=num>${pct(r.precision)}</td>
     <td class=num>${num(r.missed)}</td><td class=num>${num(r.spurious)}</td></tr>`).join("")+"</tbody>";
  document.getElementById("t-coverage").innerHTML=head+body;
})();

/* Scatter: halluc x omission, filter by scanner */
let scScanner="__all__";
(function(){
  const host=document.getElementById("scatter-filters");
  const btns=["__all__",...DATA.scanners].map(s=>
    `<button data-sc="${s}" aria-pressed="${s==="__all__"}">${s==="__all__"?"Todos":s}</button>`).join(" ");
  host.insertAdjacentHTML("beforeend",btns);
  host.querySelectorAll("button[data-sc]").forEach(b=>b.addEventListener("click",()=>{
    host.querySelectorAll("button[data-sc]").forEach(x=>x.setAttribute("aria-pressed",x===b));
    scScanner=b.dataset.sc;renderScatter();}));
})();
function renderScatter(){
  const svg=document.getElementById("scatter");svg.innerHTML="";
  const W=760,H=460,P={t:20,r:24,b:52,l:60};
  const pts=DATA.scatter.filter(p=>scScanner==="__all__"||p.scanner===scScanner);
  if(!pts.length)return;
  const xMax=Math.max(.05,Math.ceil(Math.max(...pts.map(p=>p.halluc))*20)/20);
  const yMax=Math.max(.05,Math.ceil(Math.max(...pts.map(p=>p.omission))*20)/20);
  const pw=W-P.l-P.r,ph=H-P.t-P.b;
  const xs=v=>P.l+(v/xMax)*pw,ys=v=>P.t+ph-(v/yMax)*ph;
  const g=el("g",{class:"grid"});
  const tks=n=>Array.from({length:6},(_,i)=>i*n/5);
  tks(xMax).forEach(v=>g.appendChild(el("line",{x1:xs(v),x2:xs(v),y1:P.t,y2:P.t+ph})));
  tks(yMax).forEach(v=>g.appendChild(el("line",{x1:P.l,x2:P.l+pw,y1:ys(v),y2:ys(v)})));
  svg.appendChild(g);
  svg.appendChild(el("rect",{class:"zone",x:xs(0),y:ys(Math.min(yMax,.05)),
    width:xs(Math.min(xMax,.05))-xs(0),height:ys(0)-ys(Math.min(yMax,.05))}));
  const ax=el("g",{class:"axis"});
  tks(xMax).forEach(v=>{const x=el("text",{x:xs(v),y:P.t+ph+16,"text-anchor":"middle"});x.textContent=(v*100).toFixed(0)+"%";ax.appendChild(x);});
  tks(yMax).forEach(v=>{const y=el("text",{x:P.l-8,y:ys(v)+3,"text-anchor":"end"});y.textContent=(v*100).toFixed(0)+"%";ax.appendChild(y);});
  const xl=el("text",{class:"axis-label",x:P.l+pw/2,y:H-10,"text-anchor":"middle"});xl.textContent="Hallucination →";ax.appendChild(xl);
  const yl=el("text",{class:"axis-label",x:-(P.t+ph/2),y:14,"text-anchor":"middle",transform:"rotate(-90)"});yl.textContent="Omission →";ax.appendChild(yl);
  svg.appendChild(ax);
  pts.forEach(p=>{
    const i=models.indexOf(p.model);
    const cc=el("circle",{class:"pt",cx:xs(p.halluc),cy:ys(p.omission),r:8,
      fill:color(i),"fill-opacity":.72,stroke:color(i),"stroke-width":1.5,tabindex:0});
    const h=`<div class="tt-title">${p.model} · ${p.scanner}</div>
      <div class="tt-row"><span class="k">Halluc</span><span>${pct(p.halluc)}</span></div>
      <div class="tt-row"><span class="k">Omiss</span><span>${pct(p.omission)}</span></div>
      <div class="tt-row"><span class="k">Missed</span><span>${p.missed}</span></div>
      <div class="tt-row"><span class="k">Spurious</span><span>${p.spurious}</span></div>`;
    cc.addEventListener("mouseenter",e=>showTip(h,e));cc.addEventListener("mousemove",moveTip);
    cc.addEventListener("mouseleave",hideTip);
    cc.addEventListener("focus",()=>{const b=cc.getBoundingClientRect();showTip(h,{clientX:b.left+b.width/2,clientY:b.top});});
    cc.addEventListener("blur",hideTip);
    svg.appendChild(cc);
  });
  const lg=el("g",{});const lx=P.l+pw-90;let ly=P.t+6;
  models.forEach((m,i)=>{lg.appendChild(el("circle",{cx:lx,cy:ly,r:5,fill:color(i)}));
    const tx=el("text",{x:lx+12,y:ly+4,"font-size":11,fill:css("--ink2")});tx.textContent=m;lg.appendChild(tx);ly+=16;});
  svg.appendChild(lg);
}

/* Field table with metric toggle */
let fMetric=DATA.metrics[0];
(function(){
  const host=document.getElementById("field-metric-filters");
  host.insertAdjacentHTML("beforeend",DATA.metrics.map((mt,i)=>
    `<button data-fm="${mt}" aria-pressed="${i===0}">${mt}</button>`).join(" "));
  host.querySelectorAll("button[data-fm]").forEach(b=>b.addEventListener("click",()=>{
    host.querySelectorAll("button[data-fm]").forEach(x=>x.setAttribute("aria-pressed",x===b));
    fMetric=b.dataset.fm;renderFields();}));
})();
function renderFields(){
  const by=DATA.fields_by_metric[fMetric]||{};
  const head=`<thead><tr><th>Campo</th>${models.map((m,i)=>
    `<th class=num><span class="sw" style="background:${color(i)}"></span>${m}</th>`).join("")}</tr></thead>`;
  const rows=DATA.fields.filter(f=>by[f]).map(f=>
    `<tr><td>${f}</td>${models.map(m=>`<td class=num>${pct((by[f]||{})[m])}</td>`).join("")}</tr>`).join("");
  document.getElementById("t-fields").innerHTML=head+"<tbody>"+rows+"</tbody>";
}

/* Heatmap: fill gap per field x model */
function hmColor(v){
  if(v==null)return css("--card2");
  const t=Math.max(0,Math.min(1,v/0.5));
  const stops=[[0,[31,102,68]],[.5,[230,184,0]],[1,[154,36,36]]];
  let lo=stops[0],hi=stops[2];
  for(let i=0;i<2;i++)if(t>=stops[i][0]&&t<=stops[i+1][0]){lo=stops[i];hi=stops[i+1];break;}
  const k=(t-lo[0])/((hi[0]-lo[0])||1);
  return "rgb("+lo[1].map((x,i)=>Math.round(x+(hi[1][i]-x)*k)).join(",")+")";
}
function renderHeatmap(){
  const svg=document.getElementById("heatmap-svg");svg.innerHTML="";
  const fields=DATA.fields.filter(f=>DATA.heatmap[f]);
  if(!fields.length){svg.innerHTML='<text x=20 y=30 fill="'+css("--muted")+'">sem dados de preenchimento</text>';return;}
  const W=760,P={t:16,r:70,b:96,l:150};
  const cols=models.length,rows=fields.length;
  const cw=(W-P.l-P.r)/cols,ch=26;
  const H=P.t+rows*ch+P.b;svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  fields.forEach((f,ri)=>{
    const yl=el("text",{x:P.l-8,y:P.t+ri*ch+ch/2+4,"text-anchor":"end","font-size":11,fill:css("--ink2")});
    yl.textContent=f;svg.appendChild(yl);
    models.forEach((m,ci)=>{
      const v=(DATA.heatmap[f]||{})[m];const x=P.l+ci*cw,y=P.t+ri*ch;
      const r=el("rect",{class:"hm-cell",x,y,width:cw,height:ch,fill:hmColor(v),tabindex:0});
      const disp=v==null?"N/A":(v*100).toFixed(1)+"%";
      const h=`<div class="tt-title">${m}</div><div class="tt-row"><span class="k">${f}</span><span>${disp}</span></div>`;
      r.addEventListener("mouseenter",e=>showTip(h,e));r.addEventListener("mousemove",moveTip);
      r.addEventListener("mouseleave",hideTip);
      r.addEventListener("focus",()=>{const b=r.getBoundingClientRect();showTip(h,{clientX:b.left+b.width/2,clientY:b.top});});
      r.addEventListener("blur",hideTip);svg.appendChild(r);
      if(cw>=48&&v!=null){const tx=el("text",{x:x+cw/2,y:y+ch/2+3,"text-anchor":"middle","font-size":9,
        fill:v>.25?"#fff":"#111","pointer-events":"none"});tx.textContent=(v*100).toFixed(0);svg.appendChild(tx);}
    });
  });
  models.forEach((m,ci)=>{const x=P.l+ci*cw+cw/2,y=P.t+rows*ch+14;
    const tx=el("text",{x,y,"text-anchor":"end","font-size":11,fill:css("--ink2"),transform:`rotate(-40 ${x} ${y})`});
    tx.textContent=m;svg.appendChild(tx);});
}

/* Cost + latency bars */
function renderCost(){
  const svg=document.getElementById("cost-svg");svg.innerHTML="";
  const W=760,H=220,P={t:16,r:24,b:40,l:150};
  const rows=DATA.cost_rows.filter(r=>r.cost!=null||r.duration!=null);
  if(!rows.length)return;
  const cMax=Math.max(...rows.map(r=>r.cost||0))||1;
  const half=(H-P.t-P.b)/rows.length;
  rows.forEach((r,i)=>{
    const y=P.t+i*half+half*.2,bh=half*.55;const i2=models.indexOf(r.model);
    const lbl=el("text",{x:P.l-8,y:y+bh/2+4,"text-anchor":"end","font-size":12,fill:css("--ink2")});
    lbl.textContent=r.model;svg.appendChild(lbl);
    const w=(W-P.l-P.r)*((r.cost||0)/cMax);
    const rect=el("rect",{class:"bar-rect",x:P.l,y,width:w,height:bh,rx:4,fill:color(i2)});
    const h=`<div class="tt-title">${r.model}</div>
      <div class="tt-row"><span class="k">Custo</span><span>${usd(r.cost)}</span></div>
      <div class="tt-row"><span class="k">Tempo</span><span>${r.duration!=null?Math.round(r.duration)+"s":"—"}</span></div>`;
    rect.addEventListener("mouseenter",e=>showTip(h,e));rect.addEventListener("mousemove",moveTip);
    rect.addEventListener("mouseleave",hideTip);svg.appendChild(rect);
    const vt=el("text",{x:P.l+w+6,y:y+bh/2+4,"font-size":11,fill:css("--ink2")});
    vt.textContent=usd(r.cost)+(r.duration!=null?" · "+Math.round(r.duration)+"s":"");svg.appendChild(vt);
  });
}

renderScatter();renderFields();renderHeatmap();renderCost();
let rt;addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(()=>{renderScatter();renderHeatmap();renderCost();},150);});
"""

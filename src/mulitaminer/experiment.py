"""Run X extractions per (scanner, model, report), grouped for parallelism.

Layout: <out>/<scanner>/<model>/run_<n>/<report_stem>/, plus evaluation.json/.md
when a baseline XLSX sits by the PDF. Parallelism is by capacity bucket (a
model's api_key_env or, if local, its base_url): buckets run concurrently, runs
within a bucket sequentially. Complete run dirs are skipped and re-read from
disk, so a resumed or cross-host-merged batch yields one complete manifest with
no API calls. Duration sums each run's active duration_s, never wall clock.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from mulitaminer.llm import FatalLLMError, LLMClient, get_model
from mulitaminer.pipeline import RunConfig, run
from mulitaminer.scanner_engine import detect_scanner
from mulitaminer.pdf_reader import extract_pdf
from mulitaminer.ui import Unit, experiment_view, quiet_logging

log = logging.getLogger(__name__)


def bucket_key(model_key: str) -> str:
    """The rate-limit boundary: the API key env, or the local server URL."""
    profile = get_model(model_key)
    return profile.api_key_env or profile.base_url or model_key


@dataclass
class ExperimentConfig:
    reports: list[Path]                 # PDF files
    models: list[str]                   # model profile keys
    runs: int = 3
    scanner: str | None = None          # None = auto-detect per report
    metrics: str = "all"                # passed to evaluation
    output_dir: Path = Path("output_experiments")
    model_names: dict[str, str] = field(default_factory=dict)  # generic profile overrides
    verbose: bool = False               # keep the full per-chunk log on the console


@dataclass
class _Task:
    scanner: str
    model: str
    run_index: int
    report: Path
    run_dir: Path


def _plan(config: ExperimentConfig) -> tuple[list[_Task], list[dict], dict]:
    """Extract each report once (pdfium is not thread-safe and re-extraction is
    waste), resolve its scanner, then expand the model x run x report grid."""
    tasks: list[_Task] = []
    skipped: list[dict] = []
    docs: dict[Path, object] = {}
    resolved: list[tuple[Path, str]] = []
    for report in config.reports:
        doc = extract_pdf(report)
        scanner = config.scanner
        if scanner is None:
            scanner, counts = detect_scanner(doc.text)
            if scanner is None:
                skipped.append({"report": report.name, "reason": f"scanner undetected {counts}"})
                continue
        docs[report] = doc
        resolved.append((report, scanner))

    for model in config.models:
        for run_index in range(1, config.runs + 1):
            for report, scanner in resolved:
                run_dir = (config.output_dir / scanner / model /
                           f"run_{run_index}" / report.stem)
                tasks.append(_Task(scanner, model, run_index, report, run_dir))
    return tasks, skipped, docs


def _is_complete(run_dir: Path) -> bool:
    return (run_dir / "results.json").is_file() and (run_dir / "run.json").is_file()


def _evaluate(run_dir: Path, report: Path, metrics: str) -> dict | None:
    """Evaluate a finished run when a baseline XLSX sits next to the report."""
    baseline = report.with_suffix(".xlsx")
    if not baseline.is_file():
        return None
    from mulitaminer.evaluation import evaluate_run
    from mulitaminer.evaluation.report import write_reports

    result = evaluate_run(run_dir, baseline=baseline, metrics=metrics)
    write_reports(result, run_dir)
    return result.coverage


def _cached_outcome(run_dir: Path, report: Path, metrics: str) -> dict:
    """Rebuild a complete manifest entry for an already-finished run from its own
    files. Without this, a resumed (or cross-host-merged) experiment would list
    cached runs with no coverage/cost, so the report would drop them."""
    outcome: dict = {"status": "cached"}
    try:
        rj = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        outcome["duration_s"] = rj.get("duration_s", 0.0)
        outcome["cost_usd"] = rj.get("usage", {}).get("cost_usd", 0.0)
        outcome["records"] = rj.get("final_record_count")
        outcome["block_count"] = rj.get("block_count")
        outcome["warnings"] = len(rj.get("warnings", []))
    except (OSError, json.JSONDecodeError):
        pass
    eval_path = run_dir / "evaluation.json"
    if eval_path.is_file():
        try:
            outcome["coverage"] = json.loads(eval_path.read_text(encoding="utf-8")).get("coverage")
        except json.JSONDecodeError:
            pass
    else:
        outcome["coverage"] = _evaluate(run_dir, report, metrics)
    return outcome


def _run_bucket(tasks: list[_Task], config: ExperimentConfig, docs: dict,
                on_start, on_done, cancel: threading.Event) -> None:
    """Run one bucket's tasks sequentially (shared rate limit / local server)."""
    clients: dict[str, LLMClient] = {}
    for task in tasks:
        if cancel.is_set():
            return
        on_start(task)
        if _is_complete(task.run_dir):
            on_done(task, _cached_outcome(task.run_dir, task.report, config.metrics))
            continue
        client = clients.get(task.model)
        if client is None:
            client = LLMClient(get_model(task.model),
                               model_name=config.model_names.get(task.model))
            clients[task.model] = client
        rc = RunConfig(input_path=task.report, scanner=task.scanner,
                       model=task.model, model_name=config.model_names.get(task.model))
        try:
            result, _ = run(rc, client=client, run_dir=task.run_dir,
                            doc=docs.get(task.report))
        except FatalLLMError as exc:
            on_done(task, {"status": "fatal", "detail": str(exc)})
            return  # this bucket's credential is dead; stop it, spare the rest
        except Exception as exc:  # noqa: BLE001 - one bad report must not sink the bucket
            on_done(task, {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"})
            continue
        coverage = _evaluate(task.run_dir, task.report, config.metrics)
        on_done(task, {"status": "ok", "duration_s": result.duration_s,
                       "cost_usd": result.usage.cost_usd,
                       "records": len(result.records), "block_count": result.block_count,
                       "warnings": len(result.warnings), "coverage": coverage})


def run_experiment(config: ExperimentConfig) -> dict:
    with quiet_logging(config.verbose):  # keep PDF-read logs off the live view
        tasks, skipped, docs = _plan(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.output_dir / "experiment.json"

    buckets: dict[str, list[_Task]] = {}
    for task in tasks:
        buckets.setdefault(bucket_key(task.model), []).append(task)

    records: list[dict] = []
    lock = threading.Lock()

    units = [Unit(model=t.model, run=t.run_index, report=t.report.stem) for t in tasks]
    header = (f"mulitaminer · experiment · {len(config.models)} model(s) · "
              f"runs {config.runs} · reports {len({t.report for t in tasks})} · "
              f"detailed log -> per-run *.log")
    view = experiment_view(header, units)

    def on_start(task: _Task) -> None:
        view.start(task.model, task.run_index, task.report.stem)

    def on_done(task: _Task, outcome: dict) -> None:
        entry = {"scanner": task.scanner, "model": task.model,
                 "run": task.run_index, "report": task.report.name,
                 "run_dir": str(task.run_dir), **outcome}
        with lock:
            records.append(entry)
            _write_manifest(manifest_path, config, records, skipped, complete=False)
        view.finish(task.model, task.run_index, task.report.stem,
                    status=outcome.get("status", "failed"),
                    blocks=outcome.get("records") or 0,
                    total=outcome.get("block_count") or (outcome.get("records") or 0),
                    warnings=outcome.get("warnings") or 0,
                    duration=outcome.get("duration_s") or 0.0,
                    cost=outcome.get("cost_usd") or 0.0)
        log.info("%s %s run_%d %s -> %s", task.scanner, task.model,
                 task.run_index, task.report.stem, outcome.get("status"))

    cancel = threading.Event()
    pool = ThreadPoolExecutor(max_workers=len(buckets))
    futures = [pool.submit(_run_bucket, bucket_tasks, config, docs, on_start, on_done, cancel)
               for bucket_tasks in buckets.values()]
    interrupted = False
    with quiet_logging(config.verbose), view:
        try:
            for f in futures:
                f.result()
        except KeyboardInterrupt:
            # Buckets stop before their next report; the in-flight LLM call cannot
            # be interrupted, so exit hard once the view is restored. Finished runs
            # are already checkpointed on disk (on_done), so nothing is lost.
            interrupted = True
            cancel.set()
            for f in futures:
                f.cancel()
    pool.shutdown(wait=False, cancel_futures=True)
    if interrupted:
        from mulitaminer.ui import console
        console.print("\nInterrupted. Finished runs are checkpointed; re-run to resume.",
                      style="yellow")
        os._exit(130)

    _write_manifest(manifest_path, config, records, skipped, complete=True)
    report = None
    try:
        from mulitaminer.experiment_report import build_report
        report = str(build_report(config.output_dir))
    except Exception as exc:  # noqa: BLE001 - a report failure must not fail the batch
        log.warning("report generation failed: %s", exc)
    return {"manifest": str(manifest_path), "records": records,
            "skipped": skipped, "report": report}


def _write_manifest(path: Path, config: ExperimentConfig, records: list[dict],
                    skipped: list[dict], complete: bool) -> None:
    ok = [r for r in records if r["status"] in ("ok", "cached")]
    active_seconds = round(sum(r.get("duration_s", 0.0) for r in records), 2)
    total_cost = round(sum(r.get("cost_usd", 0.0) for r in records), 4)
    payload = {
        "config": {
            "reports": [p.name for p in config.reports],
            "models": config.models,
            "runs": config.runs,
            "scanner": config.scanner,
            "metrics": config.metrics,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": complete,
        "totals": {
            "planned": len(config.reports) * len(config.models) * config.runs,
            "done": len(ok),
            "failed": sum(r["status"] in ("failed", "fatal") for r in records),
            "skipped_reports": len(skipped),
            "active_seconds": active_seconds,   # sum of run durations (the honest total)
            "cost_usd": total_cost,
        },
        "runs": records,
        "skipped": skipped,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

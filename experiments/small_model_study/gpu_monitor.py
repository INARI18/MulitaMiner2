"""Sample GPU metrics (nvidia-smi) during a run and record them to one JSON.
No extra deps, Linux/Windows, single or multi GPU.

Two modes:

  # wrap a command: sample only while it runs, then summarize
  python gpu_monitor.py --out gpu_bbwa_qwen15.json -- \
      uv run mulitaminer experiment resources/openvas/OpenVAS_bWAPP.pdf \
          --models qwen2.5-1.5b --runs 1

  # free-running: sample until Ctrl-C
  python gpu_monitor.py --out gpu_session.json --interval 0.5

The JSON holds `meta` (command, interval, start, duration), `summary`
(peak/mean VRAM, util, power, integrated energy per gpu) and the full
`samples` time series.

Attribution note: `mulitaminer experiment` runs models in parallel, so to read
a *per-model* GPU footprint, wrap one `--models <single>` invocation at a time.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

# nvidia-smi --query-gpu fields, in CSV order.
_FIELDS = [
    "index", "name", "utilization.gpu", "utilization.memory",
    "memory.used", "memory.total", "temperature.gpu", "power.draw",
    "clocks.sm", "clocks.mem",
]
_NUMERIC = {
    "utilization.gpu", "utilization.memory", "memory.used", "memory.total",
    "temperature.gpu", "power.draw", "clocks.sm", "clocks.mem",
}


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # nvidia-smi emits "[N/A]" for unsupported metrics


def sample() -> list[dict]:
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={','.join(_FIELDS)}",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        row = dict(zip(_FIELDS, parts))
        rows.append({k: (_num(v) if k in _NUMERIC else v) for k, v in row.items()})
    return rows


def summarize(samples: list[dict]) -> dict:
    by_gpu: dict[str, list[dict]] = {}
    for s in samples:
        by_gpu.setdefault(str(s["index"]), []).append(s)

    def stats(rows: list[dict], key: str) -> dict:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return {"mean": round(sum(vals) / len(vals), 2), "max": max(vals)} if vals else {}

    gpus = {}
    for idx, rows in by_gpu.items():
        # Energy: integrate power over the sample interval (trapezoid on t).
        energy_ws = 0.0
        for a, b in zip(rows, rows[1:]):
            pa, pb = a.get("power.draw"), b.get("power.draw")
            if pa is not None and pb is not None:
                energy_ws += (pa + pb) / 2 * (b["t"] - a["t"])
        gpus[idx] = {
            "name": rows[0]["name"],
            "samples": len(rows),
            "util_gpu_pct": stats(rows, "utilization.gpu"),
            "mem_used_mb": stats(rows, "memory.used"),
            "mem_total_mb": rows[0].get("memory.total"),
            "power_w": stats(rows, "power.draw"),
            "temp_c": stats(rows, "temperature.gpu"),
            "energy_wh": round(energy_ws / 3600, 4),
        }
    return gpus


def run(out: str, interval: float, command: list[str] | None) -> int:
    out_path = Path(out)
    if out_path.suffix != ".json":
        out_path = out_path.with_suffix(".json")
    samples: list[dict] = []
    proc = subprocess.Popen(command) if command else None

    stop = {"flag": False}
    if proc is None:
        signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
        print(f"sampling every {interval}s; Ctrl-C to stop -> {out_path}", file=sys.stderr)

    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    start = time.monotonic()
    try:
        while not stop["flag"]:
            t = time.monotonic() - start
            wall = time.strftime("%Y-%m-%dT%H:%M:%S")
            for row in sample():
                row["t"] = round(t, 3)
                row["wallclock"] = wall
                samples.append(row)
            if proc is not None and proc.poll() is not None:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass

    duration = time.monotonic() - start
    result = {
        "meta": {
            "command": command,
            "interval_s": interval,
            "started": started,
            "duration_s": round(duration, 2),
            "n_samples": len(samples),
        },
        "summary": summarize(samples),
        "samples": samples,
    }
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps({"meta": result["meta"], "summary": result["summary"]}, indent=2))
    return proc.wait() if proc is not None else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output JSON path")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="optional: -- <command> to sample only while it runs")
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    sys.exit(run(args.out, args.interval, command or None))


if __name__ == "__main__":
    main()

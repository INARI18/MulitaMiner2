"""Terminal UI: a thin event layer the experiment (and later the pipeline) feed.

`rich` when the console is a real terminal, a plain line-per-unit fallback
otherwise (pipe, CI, redirect). The detailed per-chunk logging is unchanged and
is routed to a file by the pipeline; this layer never parses logs, it is fed
lifecycle events. State is a fixed symbol + color, recoverable warnings are
counters (not text), and long runs keep a live totals footer.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

console = Console()


def _encodable(s: str) -> bool:
    """Whether the live console can render these glyphs (a legacy Windows cp1252
    console cannot, and rich would raise rather than substitute)."""
    try:
        s.encode(console.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# state -> (symbol, style). Fancy glyphs on UTF-8 terminals, ASCII fallback on a
# legacy codepage console so the tool never crashes on output. Never emoji.
_FANCY = _encodable("○▶✔✖…")
_SYM = ({"queued": ("○", "dim"), "running": ("▶", "blue"),
         "ok": ("✔", "green"), "failed": ("✖", "red")} if _FANCY else
        {"queued": (".", "dim"), "running": (">", "blue"),
         "ok": ("+", "green"), "failed": ("x", "red")})
_ELL = "…" if _FANCY else "..."


def fmt_dur(seconds: float) -> str:
    """Readable duration: '9s', '6m40s', '1h 04m'."""
    s = int(round(seconds))
    if s < 90:
        return f"{s}s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {sec:02d}s"


def fmt_cost(cost: float) -> str:
    return f"${cost:.3f}"


def _short(name: str, width: int) -> str:
    return name if len(name) <= width else name[: width - 1] + _ELL


@dataclass
class Unit:
    """One (model, run, report) work unit."""
    model: str
    run: int
    report: str
    state: str = "queued"
    blocks: int = 0          # records kept
    total: int = 0           # segmented blocks
    warnings: int = 0
    duration: float = 0.0
    cost: float = 0.0

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.model, self.run, self.report)


class ExperimentView:
    """Live multi-line status for a batch: one line per (model, run, report), a
    totals footer, and a final summary table. Thread-safe: buckets run in
    parallel, so state changes and the live update are locked."""

    def __init__(self, header: str, units: list[Unit]):
        self.header = header
        self.units = {u.key: u for u in units}
        self.order = [u.key for u in units]
        self.planned = len(units)
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._live = None
        self._name_w = min(26, max((len(u.report) for u in units), default=12))
        self._model_w = max((len(u.model) for u in units), default=6)

    def start(self, model: str, run: int, report: str) -> None:
        with self._lock:
            u = self.units.get((model, run, report))
            if u:
                u.state = "running"
            self._refresh()

    def finish(self, model: str, run: int, report: str, *, status: str, blocks: int,
               total: int, warnings: int, duration: float, cost: float) -> None:
        with self._lock:
            u = self.units.get((model, run, report))
            if not u:
                return
            u.state = "ok" if status in ("ok", "cached") else "failed"
            u.blocks, u.total, u.warnings = blocks, total, warnings
            u.duration, u.cost = duration, cost
            self._refresh()

    def _line(self, u: Unit) -> Text:
        sym, style = _SYM[u.state]
        t = Text()
        t.append(f"{sym} ", style=style)
        t.append(f"{u.model:<{self._model_w}} ", style="cyan")
        t.append(f"run_{u.run} ", style="dim")
        t.append(f"{_short(u.report, self._name_w):<{self._name_w}} ")
        if u.state == "queued":
            t.append("queued", style="dim")
        elif u.state == "running":
            t.append("extracting", style="blue")
        else:
            t.append(f"{u.blocks}/{u.total} blocks")
            note = "clean" if u.warnings == 0 else f"{u.warnings} warnings"
            t.append("  · ")
            t.append(note, style="dim" if u.warnings == 0 else "yellow")
            t.append(f"  · {fmt_dur(u.duration)}", style="dim")
            if u.cost:
                t.append(f"  · {fmt_cost(u.cost)}", style="dim")
        return t

    def _totals_line(self) -> Text:
        done = sum(u.state in ("ok", "failed") for u in self.units.values())
        failed = sum(u.state == "failed" for u in self.units.values())
        cost = sum(u.cost for u in self.units.values())
        el = time.monotonic() - self.started
        t = Text("totals  ", style="bold")
        t.append(f"{done}/{self.planned} done")
        t.append(f" · {failed} failed", style="red" if failed else "dim")
        t.append(f" · {fmt_cost(cost)} · elapsed {fmt_dur(el)}", style="dim")
        return t

    def _render(self) -> Group:
        rows = [Text(self.header, style="dim"), Text("")]
        rows += [self._line(self.units[k]) for k in self.order]
        rows += [Text(""), self._totals_line()]
        return Group(*rows)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def __enter__(self):
        from rich.live import Live
        self._live = Live(self._render(), console=console, refresh_per_second=6)
        self._live.__enter__()
        return self

    def __exit__(self, *exc):
        self._refresh()
        self._live.__exit__(*exc)
        self._live = None
        self.summary()

    def summary(self) -> None:
        done = [self.units[k] for k in self.order if self.units[k].state in ("ok", "failed")]
        ok = sum(u.state == "ok" for u in done)
        failed = sum(u.state == "failed" for u in done)
        el = time.monotonic() - self.started
        cost = sum(u.cost for u in self.units.values())
        sym, style = _SYM["ok" if not failed else "failed"]
        head = Text()
        head.append(f"{sym} ", style=style)
        head.append("experiment complete" if not failed
                    else f"experiment finished with {failed} failure(s)", style="bold")
        head.append(f"  · {ok}/{self.planned} ok · {failed} failed"
                    f" · {fmt_dur(el)} · {fmt_cost(cost)}", style="dim")
        console.print()
        console.print(head)
        table = Table(show_edge=False, box=None, pad_edge=False, padding=(0, 2, 0, 0))
        for col, just in (("model", "left"), ("run", "left"), ("report", "left"),
                          ("blocks", "right"), ("warnings", "right"),
                          ("time", "right"), ("cost", "right")):
            table.add_column(col, justify=just, style="dim" if col in ("model", "run") else None)
        for u in done:
            table.add_row(u.model, f"run_{u.run}", u.report, f"{u.blocks}/{u.total}",
                          "-" if u.warnings == 0 else str(u.warnings),
                          fmt_dur(u.duration), fmt_cost(u.cost) if u.cost else "-",
                          style="red" if u.state == "failed" else None)
        console.print(table)


class NullView:
    """No-TTY / verbose fallback: header once, one line per finished unit, same
    final summary. No ANSI, no live updates."""

    def __init__(self, header: str, units: list[Unit]):
        self._inner = ExperimentView(header, units)
        console.print(header, highlight=False)

    def start(self, model: str, run: int, report: str) -> None:
        pass

    def finish(self, model: str, run: int, report: str, *, status: str, blocks: int,
               total: int, warnings: int, duration: float, cost: float) -> None:
        self._inner.finish(model, run, report, status=status, blocks=blocks, total=total,
                            warnings=warnings, duration=duration, cost=cost)
        sym = _SYM["ok" if status in ("ok", "cached") else "failed"][0]
        note = "clean" if warnings == 0 else f"{warnings} warnings"
        console.print(f"{sym} {model} run_{run} {report}: {blocks}/{total} blocks "
                      f"· {note} · {fmt_dur(duration)} · {fmt_cost(cost)}", highlight=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.summary()


def experiment_view(header: str, units: list[Unit]):
    """rich Live in a terminal, plain line-per-unit fallback otherwise."""
    return ExperimentView(header, units) if console.is_terminal else NullView(header, units)

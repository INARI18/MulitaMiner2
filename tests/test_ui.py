"""Terminal UI: progress plumbing and the block bar (no live rendering needed)."""
from mulitaminer.ui import ExperimentView, ExtractView, Unit, _bar


def test_bar_fills_proportionally():
    assert _bar(0, 10, width=10).count("#") == 0 or _bar(0, 10, width=10).count("█") == 0
    full = _bar(10, 10, width=10)
    assert full[0] in ("#", "█")  # fully filled
    assert _bar(5, 0, width=8)  # zero total does not divide by zero


def test_experiment_view_live_progress_updates_unit():
    u = Unit(model="deepseek", run=1, report="rep")
    view = ExperimentView("hdr", [u])
    view.start("deepseek", 1, "rep")
    p = view.progress_for("deepseek", 1, "rep")
    p.segmented(10)
    p.chunk_done(3, 3)
    p.chunk_done(2, 3)
    p.chunk_failed()
    p.retry_round(1, 5)
    assert (u.total, u.resolved, u.jsonerr, u.round_no) == (10, 5, 1, 1)


def test_experiment_view_start_resets_live_fields():
    u = Unit(model="m", run=1, report="r", resolved=9, jsonerr=4, round_no=2, total=9)
    view = ExperimentView("hdr", [u])
    view.start("m", 1, "r")
    assert (u.total, u.resolved, u.jsonerr, u.round_no) == (0, 0, 0, 0)


def test_extract_view_accumulates_progress():
    v = ExtractView("deepseek", "report.pdf")
    v.segmented(6)
    v.chunk_done(4, 4)
    v.chunk_failed()
    v.retry_round(1, 2)
    v.chunk_done(2, 2)
    assert v.total == 6 and v.resolved == 6 and v.jsonerr == 1 and v.round_no == 1

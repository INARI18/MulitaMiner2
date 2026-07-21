"""Scorer registry.

Every scorer is a pure ``(value_a, value_b) -> float in [0, 1]`` over raw
field values (lists are rendered to text or item sets as each scorer needs).
``pair_score`` wraps a scorer with the presence rules kept from v1:
empty x empty = 1.0 (vacuous match, flagged so reports can count it apart),
present x absent = 0.0.

Kinds: "text" scorers are CLI-selectable (--metrics); "structural" scorers
(exact, set_f1) are the only meaningful metric for their fields and always
run.
"""
from __future__ import annotations

import importlib.util
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

_WORD_RE = re.compile(r"[a-z0-9]+")

BERTSCORE_HINT = "install the optional eval dependency group: uv sync --group eval"


def render_text(value: Any) -> str:
    """Canonical text form of a field value; '' means absent."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(t for t in (render_text(v) for v in value) if t)
    if isinstance(value, dict):
        return "\n".join(
            f"{k}: {t}" for k, t in ((k, render_text(v)) for k, v in value.items()) if t
        )
    return str(value).strip()


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _exact(a: Any, b: Any) -> float:
    """Normalized equality; numeric values compare numerically (8019.0 == 8019)."""
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        return 1.0 if na == nb else 0.0
    return 1.0 if render_text(a).lower() == render_text(b).lower() else 0.0


def _items(value: Any) -> set[str]:
    """Normalized item set: list elements, or lines of a scalar's text."""
    raw = value if isinstance(value, (list, tuple, set)) else render_text(value).splitlines()
    return {" ".join(_tokens(render_text(i))) for i in raw if render_text(i)}


def _set_f1(a: Any, b: Any) -> float:
    sa, sb = _items(a), _items(b)
    if not sa or not sb:
        return 0.0
    common = len(sa & sb)
    if common == 0:
        return 0.0
    p, r = common / len(sa), common / len(sb)
    return 2 * p * r / (p + r)


def _token_f1(a: Any, b: Any) -> float:
    ta, tb = _tokens(render_text(a)), _tokens(render_text(b))
    if not ta or not tb:
        return 0.0
    common = sum((Counter(ta) & Counter(tb)).values())
    if common == 0:
        return 0.0
    p, r = common / len(ta), common / len(tb)
    return 2 * p * r / (p + r)


def _lcs_len(xs: list[str], ys: list[str]) -> int:
    # Classic DP over one rolling row; O(len(xs) * len(ys)).
    prev = [0] * (len(ys) + 1)
    for x in xs:
        curr = [0]
        for j, y in enumerate(ys, 1):
            curr.append(prev[j - 1] + 1 if x == y else max(prev[j], curr[j - 1]))
        prev = curr
    return prev[-1]


def _rouge_l(a: Any, b: Any) -> float:
    ta, tb = _tokens(render_text(a)), _tokens(render_text(b))
    if not ta or not tb:
        return 0.0
    lcs = _lcs_len(ta, tb)
    if lcs == 0:
        return 0.0
    p, r = lcs / len(ta), lcs / len(tb)
    return 2 * p * r / (p + r)


_bert_model = None  # loaded once per process; the model load dominates cost


def _bertscore(a: Any, b: Any) -> float:
    global _bert_model
    if _bert_model is None:
        from bert_score import BERTScorer

        _bert_model = BERTScorer(lang="en")
    _, _, f1 = _bert_model.score([render_text(a)], [render_text(b)])
    return float(f1[0])


def _bertscore_missing(a: Any, b: Any) -> float:
    raise RuntimeError(f"bertscore is unavailable — {BERTSCORE_HINT}")


@dataclass(frozen=True)
class Scorer:
    name: str
    kind: str  # "text" | "structural"
    fn: Callable[[Any, Any], float] = field(repr=False)
    available: bool = True
    hint: str = ""


_BERT_AVAILABLE = importlib.util.find_spec("bert_score") is not None

SCORERS: dict[str, Scorer] = {
    "exact": Scorer("exact", "structural", _exact),
    "set_f1": Scorer("set_f1", "structural", _set_f1),
    "token_f1": Scorer("token_f1", "text", _token_f1),
    "rouge_l": Scorer("rouge_l", "text", _rouge_l),
    "bertscore": Scorer(
        "bertscore",
        "text",
        _bertscore if _BERT_AVAILABLE else _bertscore_missing,
        available=_BERT_AVAILABLE,
        hint="" if _BERT_AVAILABLE else BERTSCORE_HINT,
    ),
}


def text_scorers() -> list[Scorer]:
    return [s for s in SCORERS.values() if s.kind == "text"]


def pair_score(scorer: Scorer, ext_value: Any, base_value: Any) -> tuple[float, bool]:
    """Score one field pair. Returns (score, vacuous)."""
    e, b = render_text(ext_value), render_text(base_value)
    if not e and not b:
        return 1.0, True
    if not e or not b:
        return 0.0, False
    return float(scorer.fn(ext_value, base_value)), False

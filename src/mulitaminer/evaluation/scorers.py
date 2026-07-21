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

EVAL_GROUP_HINT = "install the optional eval dependency group: uv sync --group eval"
BERTSCORE_HINT = EVAL_GROUP_HINT

# Reference-identifier canonicalization for set_f1_ids: label/format jitter
# ("CVE CVE-2022-1" vs "CVE-2022-1", comma-joined multi-id items) collapses to
# the same ids, so the score measures content, not prompt formatting.
_ID_RES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"cve[-\s:]*(\d{4})[-\s](\d{3,7})"), r"cve-\1-\2"),
    (re.compile(r"cwe[-\s:]*(\d+)"), r"cwe-\1"),
    (re.compile(r"bid[-\s:]*(\d+)"), r"bid-\1"),
    (re.compile(r"\b(\d{4})-(a\d{1,2}|api\d{1,2})\b"), r"owasp-\1-\2"),
    (re.compile(r"https?://[^\s,'\"]+"), None),  # None -> normalized URL itself
]


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


def _canonical_ids(item: Any) -> set[str]:
    """One reference item -> canonical id set (or its normalized text)."""
    text = render_text(item).lower()
    ids: set[str] = set()
    for pattern, repl in _ID_RES:
        for m in pattern.finditer(text):
            ids.add(m.expand(repl) if repl else m.group(0).rstrip("/.").lower())
    # Bare numbers in a comma list inherit the item's leading label ("BID:32668, 32669").
    lead = re.match(r"\s*(cve|cwe|bid)\b", text)
    if lead:
        for frag in text.split(","):
            frag = frag.strip()
            if re.fullmatch(r"\d{1,7}", frag):
                ids.add(f"{lead.group(1)}-{frag}")
    if ids:
        return ids
    # No recognizable ids (e.g. WASC category names): fall back to normalized
    # text, exploding comma lists with the leading label word replicated so
    # granularity jitter does not zero the comparison.
    frags = [f.strip() for f in text.split(",") if f.strip()]
    if len(frags) > 1:
        label_word = frags[0].split()[0] if frags[0].split() else ""
        expanded = [frags[0]] + [
            f if f.startswith(label_word) else f"{label_word} {f}" for f in frags[1:]
        ]
    else:
        expanded = frags
    return {norm for f in expanded if (norm := " ".join(_WORD_RE.findall(f)))}


def _set_f1_ids(a: Any, b: Any) -> float:
    """set_f1 over canonicalized reference identifiers (content, not format)."""

    def ids(v: Any) -> set[str]:
        raw = v if isinstance(v, (list, tuple, set)) else render_text(v).splitlines()
        return {i for item in raw for i in _canonical_ids(item)}

    sa, sb = ids(a), ids(b)
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


# NLI: sentence-level contradiction check. Chosen model is trained on
# MNLI+FEVER+ANLI — ANLI stresses exactly the one-word negation flips that
# lexical metrics and BERTScore barely penalize ("no auth" vs "auth").
NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_nli_pipeline = None  # loaded once per process


def _nli(a: Any, b: Any) -> float:
    """1 - max P(contradiction) over ground-truth sentences.

    Premise = the extraction text, hypothesis = each baseline sentence: a
    dropped/flipped negation makes the pair a contradiction. Splitting the
    baseline side keeps hypotheses inside the model's 512-token window and
    localizes which sentence flipped.
    """
    global _nli_pipeline
    if _nli_pipeline is None:
        from transformers import pipeline

        _nli_pipeline = pipeline("text-classification", model=NLI_MODEL, top_k=None)
    premise = render_text(a)
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(render_text(b)) if s.strip()]
    if not premise or not sentences:
        return 0.0
    inputs = [{"text": premise, "text_pair": s} for s in sentences]
    results = _nli_pipeline(inputs, truncation=True, max_length=512)
    worst = max(
        next(r["score"] for r in res if r["label"].lower() == "contradiction")
        for res in results
    )
    return 1.0 - float(worst)


def _nli_missing(a: Any, b: Any) -> float:
    raise RuntimeError(f"nli is unavailable — {EVAL_GROUP_HINT}")


@dataclass(frozen=True)
class Scorer:
    name: str
    kind: str  # "text" | "structural"
    fn: Callable[[Any, Any], float] = field(repr=False)
    available: bool = True
    hint: str = ""
    # Whether --metrics all includes this scorer. nli opts out: ~seconds per
    # pair on CPU, so it must be requested explicitly (--metrics nli).
    in_all: bool = True


_BERT_AVAILABLE = importlib.util.find_spec("bert_score") is not None
_NLI_AVAILABLE = importlib.util.find_spec("transformers") is not None

SCORERS: dict[str, Scorer] = {
    "exact": Scorer("exact", "structural", _exact),
    "set_f1": Scorer("set_f1", "structural", _set_f1),
    "set_f1_ids": Scorer("set_f1_ids", "structural", _set_f1_ids),
    "token_f1": Scorer("token_f1", "text", _token_f1),
    "rouge_l": Scorer("rouge_l", "text", _rouge_l),
    "bertscore": Scorer(
        "bertscore",
        "text",
        _bertscore if _BERT_AVAILABLE else _bertscore_missing,
        available=_BERT_AVAILABLE,
        hint="" if _BERT_AVAILABLE else BERTSCORE_HINT,
    ),
    "nli": Scorer(
        "nli",
        "text",
        _nli if _NLI_AVAILABLE else _nli_missing,
        available=_NLI_AVAILABLE,
        hint="" if _NLI_AVAILABLE else EVAL_GROUP_HINT,
        in_all=False,
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

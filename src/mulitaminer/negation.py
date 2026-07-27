"""Negation gate: flag extracted text whose negation cues disagree with the
source block (flip candidates). Flag-only: nothing is modified or retried."""
from __future__ import annotations

import logging
import re
from typing import Any

from mulitaminer.models import Block, VulnRecord

log = logging.getLogger(__name__)

# Cue lexicon: function-word negations plus the lexical forms scanners use.
# Multi-word cues ("fails to") are matched by the regex; their words are also
# in _CUE_WORDS so they do not count as content when aligning sentences.
_CUE_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|won't|doesn't|isn't|don't|aren't|wasn't|"
    r"weren't|couldn't|shouldn't|wouldn't|without|unable|denie[sd]|"
    r"disabled|lacks?|fails? to)\b",
    re.IGNORECASE,
)
_CUE_WORDS = frozenset(
    "not no never cannot can't won't doesn't isn't don't aren't wasn't weren't "
    "couldn't shouldn't wouldn't without unable denies denied disabled lack "
    "lacks fail fails to".split()
)
# Same boundaries as the nli scorer: sentence enders and blank lines; single \n
# is hard-wrap, "e.g."-style dots are abbreviations.
_SENT_RE = re.compile(
    r"(?<=[.!?])(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)\s+|\n{2,}"
)
_WORD_RE = re.compile(r"[a-z0-9']+")

# Aligned-sentence content overlap (Jaccard) required before claiming the pair
# describes the same statement.
_MIN_OVERLAP = 0.5


def _text_fields(record_type: type[VulnRecord], overrides: dict[str, str]) -> set[str]:
    """Fields worth gating: the same type + field_metrics classification the
    evaluator uses, so prose fields are gated and exact/set fields are not.
    Lazy import keeps the extraction path free of evaluation imports."""
    from mulitaminer.evaluation.fields import field_plans

    return {p.name for p in field_plans(record_type, overrides) if p.metric == "text"}


def _render(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return ""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def _content_words(sentence: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(sentence.lower())) - _CUE_WORDS


def _flag_field(field: str, extracted: str, source_sents: list[tuple[str, frozenset[str], bool]]) -> list[dict]:
    flags = []
    for ext_sent in _sentences(extracted):
        ext_words = _content_words(ext_sent)
        if not ext_words:
            continue
        ext_has_cue = bool(_CUE_RE.search(ext_sent))
        best, best_j = None, 0.0
        for src_sent, src_words, src_has_cue in source_sents:
            if not src_words:
                continue
            j = len(ext_words & src_words) / len(ext_words | src_words)
            if j > best_j:
                best, best_j = (src_sent, src_has_cue), j
        if best is None or best_j < _MIN_OVERLAP:
            continue
        src_sent, src_has_cue = best
        if ext_has_cue == src_has_cue:
            continue
        flags.append({
            "field": field,
            "kind": "invented" if ext_has_cue else "dropped",
            "overlap": round(best_j, 3),
            "extracted_sentence": ext_sent,
            "source_sentence": src_sent,
            "nli_score": None,
        })
    return flags


def gate_records(
    records: dict[int, VulnRecord],
    blocks_by_id: dict[int, Block],
    field_overrides: dict[str, str] | None = None,
    confirm: bool = True,
) -> list[dict]:
    """Lexical cue-asymmetry check of each record's prose against its source
    block; sentences are aligned by content-word overlap. Which fields count as
    prose comes from the evaluator's field classification (type inference plus
    the scanner's field_metrics overrides). With confirm=True, flagged pairs are
    scored by the nli scorer when its deps are installed (nli_score close to 0 =
    contradiction confirmed; None = not scored)."""
    if not records:
        return []
    record_type = type(next(iter(records.values())))
    gated = _text_fields(record_type, field_overrides or {})
    flags: list[dict] = []
    for bid, record in records.items():
        block = blocks_by_id.get(bid)
        if block is None:
            continue
        source_text = block.text
        source_sents = [
            (s, _content_words(s), bool(_CUE_RE.search(s)))
            for s in _sentences(source_text)
        ]
        for field, value in record.model_dump().items():
            if field not in gated:
                continue
            text = _render(value)
            # cheap pre-check: no cue on either side of this field = no flip
            if not text or (
                not _CUE_RE.search(text) and not _CUE_RE.search(source_text)
            ):
                continue
            for flag in _flag_field(field, text, source_sents):
                flags.append({"block_id": bid, **flag})
    if confirm and flags:
        _confirm(flags)
    return flags


def _confirm(flags: list[dict]) -> None:
    """Attach nli scores in place. The gate is optional by design: missing eval
    deps skip silently, and any model failure (download on an offline box, load
    error) logs a warning instead of killing an extraction that already paid
    for its LLM calls."""
    try:
        from mulitaminer.evaluation.scorers import nli_scores

        scores = nli_scores(
            [(f["extracted_sentence"], f["source_sentence"]) for f in flags]
        )
    except ImportError:
        return
    except Exception as exc:  # noqa: BLE001 - degrade to unscored flags
        log.warning("negation gate: nli confirm unavailable (%s); "
                    "flags left unscored", exc)
        return
    for f, s in zip(flags, scores):
        f["nli_score"] = round(float(s), 4)

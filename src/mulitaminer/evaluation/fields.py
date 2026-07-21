"""Schema-driven field -> metric mapping.

The evaluator never hardcodes field names: it walks the record model's
LLM-produced fields and infers the metric kind from each type annotation
(design spec §5). Per-field overrides come from the scanner config JSON
("evaluation": {"field_metrics": {...}}) — a scorer name, or "skip".

FieldPlan.metric values:
    "text"        — scored by every selected text scorer (token_f1, ...)
    "structural"  — nested model / dict / list[Model]: recurse per sub-field
    "skip"        — excluded from evaluation
    a scorer name — scored by exactly that scorer (overrides, and inferred
                    "exact" for Literal/numeric fields)
"""
from __future__ import annotations

import types
import typing
from dataclasses import dataclass

from pydantic import BaseModel

from mulitaminer.evaluation.scorers import SCORERS
from mulitaminer.models import VulnRecord, _is_llm_produced


@dataclass(frozen=True)
class FieldPlan:
    name: str
    metric: str
    # For structural fields: the nested model to recurse into (None for plain
    # dicts — sub-fields are then compared as text over the union of keys).
    sub_model: type[BaseModel] | None = None
    # True when the structural field is a list of items (e.g. instances);
    # items are sub-aligned before recursion.
    is_list: bool = False


def _non_none_args(annotation) -> list:
    return [a for a in typing.get_args(annotation) if a is not type(None)]


def _plan_for(name: str, annotation) -> FieldPlan:
    origin = typing.get_origin(annotation)

    # Unions (Optional[X], int | str, ...): unwrap; all-numeric or numeric/str
    # mixes (port) compare exactly — `exact` is numeric-aware.
    if origin in (typing.Union, types.UnionType):
        args = _non_none_args(annotation)
        if len(args) == 1:
            return _plan_for(name, args[0])
        if all(a in (int, float, str) for a in args):
            return FieldPlan(name, "exact")
        return FieldPlan(name, "text")

    if origin is typing.Literal:
        return FieldPlan(name, "exact")

    if origin in (list, tuple, set):
        args = typing.get_args(annotation)
        item = args[0] if args else None
        if isinstance(item, type) and issubclass(item, BaseModel):
            return FieldPlan(name, "structural", sub_model=item, is_list=True)
        return FieldPlan(name, "text")

    if origin is dict or annotation is dict:
        return FieldPlan(name, "structural")

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return FieldPlan(name, "structural", sub_model=annotation)
        if annotation is bool or annotation in (int, float):
            return FieldPlan(name, "exact")
        if annotation is str:
            return FieldPlan(name, "text")

    # list without parameters, Any, exotic annotations: text is the safe default.
    return FieldPlan(name, "text")


def field_plans(
    record_type: type[VulnRecord],
    overrides: dict[str, str] | None = None,
) -> list[FieldPlan]:
    """One FieldPlan per LLM-produced field of ``record_type``."""
    overrides = overrides or {}
    valid = set(SCORERS) | {"skip"}
    unknown = {v for v in overrides.values() if v not in valid}
    if unknown:
        raise ValueError(
            f"Unknown field_metrics override(s) {sorted(unknown)}; "
            f"valid values: {sorted(valid)}"
        )

    plans: list[FieldPlan] = []
    for name, f in record_type.model_fields.items():
        if not _is_llm_produced(f):
            continue
        if name in overrides:
            plans.append(FieldPlan(name, overrides[name]))
        else:
            plans.append(_plan_for(name, f.annotation))
    return [p for p in plans if p.metric != "skip"]

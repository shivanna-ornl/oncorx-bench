#!/usr/bin/env python3
"""Strict, standard-library-only validation for an OncoRx-Bench release.

This validator treats the generated JSONL and the projected UOTD knowledge
tables as release artifacts.  A release passes only when all schema, quota,
identifier, grounding, evidence, consistency, and duplicate checks pass.

Usage:
    python validate_dataset.py
    python validate_dataset.py --input output/oncorx_bench.jsonl
    python validate_dataset.py --report output/validation_report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dataset_config import (
    CATEGORY_DISTRIBUTION,
    DIFFICULTY_LEVELS,
    DRUG_TABLE_PATH,
    NOTE_TYPES,
    NOTE_TYPES_BY_SUBCATEGORY,
    OUTPUT_DIR,
    REGIMEN_TABLE_PATH,
)
from schema import DrugStatus, Intent, Route


EXPECTED_TOP_LEVEL_FIELDS = {
    "sample_id",
    "clinical_text",
    "category",
    "subcategory",
    "difficulty",
    "drug_mentions",
    "regimen_mentions",
    "num_drugs",
    "note_type",
}
REQUIRED_DRUG_FIELDS = {
    "drug_surface",
    "drug_normalized",
    "start_char",
    "end_char",
    "evidence_type",
    "status",
    "negated",
    "allergy",
    "uncertain",
}
ALLOWED_DRUG_FIELDS = REQUIRED_DRUG_FIELDS | {"reason", "adverse_event", "sig"}
REQUIRED_REGIMEN_FIELDS = {
    "regimen_surface",
    "regimen_normalized",
    "components_normalized",
    "start_char",
    "end_char",
}
ALLOWED_REGIMEN_FIELDS = REQUIRED_REGIMEN_FIELDS | {"cycle_info", "intent"}
ALLOWED_SIG_FIELDS = {
    "dose_value",
    "dose_unit",
    "route",
    "frequency",
    "duration",
    "form",
    "prn",
    "taper",
    "cycle_day",
    "infusion_time",
}
STRING_SIG_FIELDS = ALLOWED_SIG_FIELDS - {"prn"}

DRUG_STATUSES = {member.value for member in DrugStatus}
ROUTES = {member.value for member in Route}
INTENTS = {member.value for member in Intent}
EVIDENCE_TYPES = {"explicit_surface", "regimen_inference"}
EXPLICIT_NOTE_PREFIXES = {
    "Telephone encounter:": "telephone_encounter",
    "Discharge summary:": "discharge_summary",
    "Oncology consult:": "oncology_consult",
    "Infusion center note:": "nursing_note",
    "Med reconciliation:": "medication_reconciliation",
    "Progress note:": "progress_note",
}
PLACEHOLDER_PATTERN = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
SAMPLE_ID_PATTERN = re.compile(r"ONCORX-(\d{4})\Z")

ERROR_GROUPS = (
    "input_errors",
    "knowledge_errors",
    "json_errors",
    "schema_errors",
    "distribution_errors",
    "drug_grounding_errors",
    "regimen_grounding_errors",
    "text_evidence_errors",
    "sig_errors",
    "template_placeholder_errors",
    "duplicate_errors",
)


class ErrorCollector:
    """Count every error while retaining a bounded set of concrete examples."""

    def __init__(self, detail_limit: int = 100) -> None:
        self.detail_limit = max(0, detail_limit)
        self.counts: Counter[str] = Counter()
        self.details: dict[str, list[str]] = defaultdict(list)

    def add(self, group: str, message: str) -> None:
        self.counts[group] += 1
        if len(self.details[group]) < self.detail_limit:
            self.details[group].append(message)

    def count(self, group: str) -> int:
        return self.counts[group]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _is_int(value: Any) -> bool:
    """Return true only for integers, excluding bool (a subclass of int)."""
    return type(value) is int


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _display_case_hint(value: str, canonical_by_casefold: dict[str, str]) -> str:
    canonical = canonical_by_casefold.get(value.casefold())
    return f"; canonical spelling is {canonical!r}" if canonical else ""


def _parse_json_string_list(
    raw_value: str,
    context: str,
    collector: ErrorCollector,
    *,
    allow_empty: bool,
) -> list[str]:
    """Parse a JSON-array CSV cell without ambiguous comma splitting."""
    try:
        value = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError) as exc:
        collector.add("knowledge_errors", f"{context}: invalid JSON array ({exc})")
        return []
    if not isinstance(value, list):
        collector.add("knowledge_errors", f"{context}: expected a JSON array")
        return []
    if not allow_empty and not value:
        collector.add("knowledge_errors", f"{context}: array must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        if not _nonempty_string(item):
            collector.add(
                "knowledge_errors",
                f"{context}[{index}]: expected a non-empty string",
            )
            continue
        result.append(item.strip())
    folded = [item.casefold() for item in result]
    if len(folded) != len(set(folded)):
        collector.add("knowledge_errors", f"{context}: duplicate array values")
    return result


def _load_knowledge(
    drug_path: Path,
    regimen_path: Path,
    collector: ErrorCollector,
) -> tuple[set[str], dict[str, tuple[str, ...]]]:
    """Load and validate canonical drugs and regimen component projections."""
    canonical_drugs: set[str] = set()
    drug_casefold: dict[str, str] = {}
    anchor_ids: dict[str, str] = {}

    try:
        with drug_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"drug_name", "synonyms_json", "anchor_drug_id"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                collector.add(
                    "knowledge_errors",
                    f"{drug_path.name}: missing columns {sorted(missing)}",
                )
            for row_number, row in enumerate(reader, 2):
                name = (row.get("drug_name") or "").strip()
                context = f"{drug_path.name}:{row_number}"
                if not name:
                    collector.add("knowledge_errors", f"{context}: empty drug_name")
                    continue
                if name in canonical_drugs:
                    collector.add("knowledge_errors", f"{context}: duplicate drug_name {name!r}")
                prior_case = drug_casefold.get(name.casefold())
                if prior_case is not None and prior_case != name:
                    collector.add(
                        "knowledge_errors",
                        f"{context}: case-insensitive canonical collision {prior_case!r}/{name!r}",
                    )
                canonical_drugs.add(name)
                drug_casefold.setdefault(name.casefold(), name)

                anchor_id = (row.get("anchor_drug_id") or "").strip()
                if not anchor_id:
                    collector.add("knowledge_errors", f"{context}: empty anchor_drug_id")
                elif anchor_id in anchor_ids and anchor_ids[anchor_id] != name:
                    collector.add(
                        "knowledge_errors",
                        f"{context}: anchor_drug_id {anchor_id!r} also maps to "
                        f"{anchor_ids[anchor_id]!r}",
                    )
                else:
                    anchor_ids[anchor_id] = name
                _parse_json_string_list(
                    row.get("synonyms_json") or "",
                    f"{context}:synonyms_json",
                    collector,
                    allow_empty=True,
                )
    except OSError as exc:
        collector.add("knowledge_errors", f"cannot read {drug_path}: {exc}")

    regimens: dict[str, tuple[str, ...]] = {}
    regimen_casefold: dict[str, str] = {}
    try:
        with regimen_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"regimen_name", "components_json", "regimen_id"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                collector.add(
                    "knowledge_errors",
                    f"{regimen_path.name}: missing columns {sorted(missing)}",
                )
            for row_number, row in enumerate(reader, 2):
                name = (row.get("regimen_name") or "").strip()
                context = f"{regimen_path.name}:{row_number}"
                if not name:
                    collector.add("knowledge_errors", f"{context}: empty regimen_name")
                    continue
                if name in regimens:
                    collector.add("knowledge_errors", f"{context}: duplicate regimen_name {name!r}")
                prior_case = regimen_casefold.get(name.casefold())
                if prior_case is not None and prior_case != name:
                    collector.add(
                        "knowledge_errors",
                        f"{context}: case-insensitive regimen collision {prior_case!r}/{name!r}",
                    )
                components = _parse_json_string_list(
                    row.get("components_json") or "",
                    f"{context}:components_json",
                    collector,
                    allow_empty=False,
                )
                for component in components:
                    if component not in canonical_drugs:
                        hint = _display_case_hint(component, drug_casefold)
                        collector.add(
                            "knowledge_errors",
                            f"{context}: noncanonical component {component!r}{hint}",
                        )
                regimen_id = (row.get("regimen_id") or "").strip()
                if not regimen_id:
                    collector.add("knowledge_errors", f"{context}: empty regimen_id")
                regimens[name] = tuple(components)
                regimen_casefold.setdefault(name.casefold(), name)
    except OSError as exc:
        collector.add("knowledge_errors", f"cannot read {regimen_path}: {exc}")

    return canonical_drugs, regimens


def _find_placeholders(value: Any, path: str = "sample") -> list[str]:
    findings: list[str] = []
    if isinstance(value, str):
        matches = PLACEHOLDER_PATTERN.findall(value)
        if matches:
            findings.append(f"{path}: {matches}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_find_placeholders(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            findings.extend(_find_placeholders(item, f"{path}.{key}"))
    return findings


def _normalize_space(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_literal(text: str, value: str) -> bool:
    return _normalize_space(value) in _normalize_space(text)


def _contains_token(text: str, token: str) -> bool:
    return bool(
        re.search(
            r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _validate_span(
    *,
    sid: str,
    object_label: str,
    text: str,
    surface: Any,
    start: Any,
    end: Any,
    collector: ErrorCollector,
) -> bool:
    if not _nonempty_string(surface):
        collector.add("schema_errors", f"{sid}: {object_label}.surface must be a non-empty string")
        return False
    if not _is_int(start) or not _is_int(end):
        collector.add(
            "schema_errors",
            f"{sid}: {object_label} offsets must both be integers",
        )
        return False
    if not (0 <= start < end <= len(text)):
        collector.add(
            "text_evidence_errors",
            f"{sid}: {object_label} invalid span [{start},{end}) for text length {len(text)}",
        )
        return False
    actual = text[start:end]
    if actual != surface:
        collector.add(
            "text_evidence_errors",
            f"{sid}: {object_label} surface/offset mismatch: "
            f"annotation={surface!r}, text[{start}:{end}]={actual!r}",
        )
        return False
    return True


def _intent_is_visible(text: str, intent: str) -> bool:
    variants = {
        "first_line": ("first-line", "first line"),
        "second_line": ("second-line", "second line"),
        "third_line_plus": ("third-line", "third line"),
        "neoadjuvant": ("neoadjuvant", "neo-adjuvant"),
    }.get(intent, (intent.replace("_", "-"), intent.replace("_", " ")))
    return any(_contains_token(text, variant) for variant in variants)


def _cycle_part_is_visible(text: str, part: str) -> bool:
    """Check mechanically verifiable cycle metadata against rendered prose."""
    cycle_fraction = re.fullmatch(r"cycle\s+(\d+)\s*/\s*(\d+)", part, re.I)
    if cycle_fraction:
        current, total = map(re.escape, cycle_fraction.groups())
        patterns = (
            rf"\bcycle\s*:?\s*{current}\s*/\s*{total}\b",
            rf"\bcycle\s+{current}\s+of\s+{total}\b",
        )
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            return True
        # Some templates state the current and planned-total cycle counts in
        # separate clauses ("cycle 4 ... Plan 6 total cycles").
        current_visible = bool(re.search(rf"\bcycle\s*:?\s*{current}\b", text, re.I))
        total_visible = bool(
            re.search(
                rf"(?:\bx\s*{total}\s+cycles\b|\b{total}\s+(?:total\s+)?cycles\b)",
                text,
                re.I,
            )
        )
        return current_visible and total_visible

    cycle_number = re.fullmatch(r"cycle\s+(\d+)", part, re.I)
    if cycle_number:
        number = re.escape(cycle_number.group(1))
        patterns = (
            rf"\bcycle\s*:?\s*{number}\b",
            rf"\bC0*{number}(?:D\d+)?\b",
            rf"\b{number}\s+cycles\b",
        )
        return any(re.search(pattern, text, re.I) for pattern in patterns)

    cycle_total = re.fullmatch(r"(\d+)\s+cycles", part, re.I)
    if cycle_total:
        number = re.escape(cycle_total.group(1))
        return bool(
            re.search(
                rf"(?:\bx\s*{number}\s+cycles\b|\b{number}\s+cycles\b)",
                text,
                re.I,
            )
        )

    cadence = re.fullmatch(r"q(\d+)w", part, re.I)
    if cadence:
        number = re.escape(cadence.group(1))
        patterns = (
            rf"\bq\s*{number}\s*w\b",
            rf"\bevery\s+{number}\s+weeks?\b",
            rf"\bin\s+{number}\s+weeks?\b",
        )
        return any(re.search(pattern, text, re.I) for pattern in patterns)
    return False


def _validate_sig(
    sig: Any,
    *,
    sid: str,
    label: str,
    text: str,
    collector: ErrorCollector,
) -> None:
    if not isinstance(sig, dict):
        collector.add("schema_errors", f"{sid}: {label}.sig must be an object")
        return
    if not sig:
        collector.add("schema_errors", f"{sid}: {label}.sig must not be empty")
        return
    extras = set(sig) - ALLOWED_SIG_FIELDS
    if extras:
        collector.add("schema_errors", f"{sid}: {label}.sig has unknown fields {sorted(extras)}")

    for field in sorted(STRING_SIG_FIELDS & set(sig)):
        if not _nonempty_string(sig[field]):
            collector.add(
                "schema_errors",
                f"{sid}: {label}.sig.{field} must be a non-empty string",
            )
    if "prn" in sig and type(sig["prn"]) is not bool:
        collector.add("schema_errors", f"{sid}: {label}.sig.prn must be boolean")
    if "route" in sig and isinstance(sig["route"], str) and sig["route"] not in ROUTES:
        collector.add(
            "schema_errors",
            f"{sid}: {label}.sig.route has invalid enum value {sig['route']!r}",
        )

    has_value = "dose_value" in sig
    has_unit = "dose_unit" in sig
    if has_value != has_unit:
        collector.add(
            "sig_errors",
            f"{sid}: {label}.sig dose_value and dose_unit must appear together",
        )
    if has_value and _nonempty_string(sig.get("dose_value")) and _nonempty_string(sig.get("dose_unit")):
        value = sig["dose_value"]
        unit = sig["dose_unit"]
        if unit.casefold() == "auc":
            visible = bool(re.search(rf"\bAUC\s*{re.escape(value)}\b", text, re.I))
        else:
            visible = bool(
                re.search(
                    rf"(?<![A-Za-z0-9]){re.escape(value)}\s*{re.escape(unit)}(?![A-Za-z0-9])",
                    text,
                    re.I,
                )
            )
        if not visible:
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig dose {value!r} {unit!r} lacks matching text evidence",
            )

    if _nonempty_string(sig.get("route")):
        route = sig["route"]
        route_aliases = {
            "PO": ("PO", "oral", "by mouth"),
            "IV": ("IV", "intravenous", "infusion", "infused"),
            "SC": ("SC", "subcutaneous"),
            "IM": ("IM", "intramuscular"),
            "IT": ("IT", "intrathecal"),
            "PR": ("PR", "rectal", "per rectum"),
            "SL": ("SL", "sublingual"),
        }.get(route, (route,))
        if not any(_contains_token(text, alias) for alias in route_aliases):
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig.route {route!r} lacks text evidence",
            )

    for field in ("frequency", "form", "cycle_day", "infusion_time"):
        value = sig.get(field)
        if _nonempty_string(value) and not _contains_literal(text, value):
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig.{field}={value!r} lacks text evidence",
            )

    duration = sig.get("duration")
    if _nonempty_string(duration):
        # Normalized durations can add words such as "until"; all numbers and
        # substantive words still must be supported by the rendered text.
        ignored = {"a", "an", "and", "for", "of", "or", "the", "to", "until", "x"}
        tokens = [
            token for token in re.findall(r"[A-Za-z0-9]+", duration.casefold())
            if token not in ignored
        ]
        if tokens and not all(_contains_token(text, token) for token in set(tokens)):
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig.duration={duration!r} lacks text evidence",
            )

    taper = sig.get("taper")
    if _nonempty_string(taper):
        numeric_steps = set(re.findall(r"\d+(?:\.\d+)?", taper))
        if numeric_steps and not all(_contains_token(text, value) for value in numeric_steps):
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig.taper={taper!r} lacks all dose-step evidence",
            )

    if sig.get("prn") is True:
        prn_patterns = (
            r"\bPRN\b",
            r"\bas needed\b",
            r"\bif\b",
            r"\bonly if\b",
            r"\brescue\b",
            r"\bsliding scale\b",
            r"\bfor\s+(?:mild|moderate|severe)\b",
        )
        if not any(re.search(pattern, text, re.I) for pattern in prn_patterns):
            collector.add("sig_errors", f"{sid}: {label}.sig.prn=true lacks conditional text evidence")


def _validate_drug_mention(
    mention: Any,
    *,
    sid: str,
    index: int,
    text: str,
    canonical_drugs: set[str],
    drug_casefold: dict[str, str],
    collector: ErrorCollector,
) -> tuple[str, tuple[Any, ...]] | None:
    label = f"drug_mentions[{index}]"
    if not isinstance(mention, dict):
        collector.add("schema_errors", f"{sid}: {label} must be an object")
        return None
    missing = REQUIRED_DRUG_FIELDS - set(mention)
    extras = set(mention) - ALLOWED_DRUG_FIELDS
    if missing:
        collector.add("schema_errors", f"{sid}: {label} missing fields {sorted(missing)}")
    if extras:
        collector.add("schema_errors", f"{sid}: {label} has unknown fields {sorted(extras)}")

    surface = mention.get("drug_surface")
    normalized = mention.get("drug_normalized")
    _validate_span(
        sid=sid,
        object_label=label,
        text=text,
        surface=surface,
        start=mention.get("start_char"),
        end=mention.get("end_char"),
        collector=collector,
    )
    if not _nonempty_string(normalized):
        collector.add("schema_errors", f"{sid}: {label}.drug_normalized must be a non-empty string")
    elif normalized not in canonical_drugs:
        hint = _display_case_hint(normalized, drug_casefold)
        collector.add(
            "drug_grounding_errors",
            f"{sid}: {label} uses noncanonical drug {normalized!r}{hint}",
        )

    status = mention.get("status")
    if not isinstance(status, str) or status not in DRUG_STATUSES:
        collector.add("schema_errors", f"{sid}: {label}.status has invalid enum value {status!r}")
    for field in ("negated", "allergy", "uncertain"):
        if type(mention.get(field)) is not bool:
            collector.add("schema_errors", f"{sid}: {label}.{field} must be boolean")
    evidence_type = mention.get("evidence_type")
    if not isinstance(evidence_type, str) or evidence_type not in EVIDENCE_TYPES:
        collector.add(
            "schema_errors",
            f"{sid}: {label}.evidence_type has invalid enum value {evidence_type!r}",
        )
    for field in ("reason", "adverse_event"):
        if field in mention and not _nonempty_string(mention[field]):
            collector.add("schema_errors", f"{sid}: {label}.{field} must be a non-empty string")
        elif field in mention and not _contains_literal(text, mention[field]):
            collector.add(
                "text_evidence_errors",
                f"{sid}: {label}.{field}={mention[field]!r} lacks text evidence",
            )
    if "sig" in mention:
        _validate_sig(mention["sig"], sid=sid, label=label, text=text, collector=collector)
        if evidence_type == "regimen_inference":
            collector.add(
                "sig_errors",
                f"{sid}: {label}.sig is component-specific but evidence is only a regimen surface",
            )

    if not _nonempty_string(normalized):
        return None
    identity = (
        surface.casefold() if isinstance(surface, str) else surface,
        normalized.casefold(),
        mention.get("start_char"),
        mention.get("end_char"),
    )
    return normalized, identity


def _validate_regimen_mention(
    mention: Any,
    *,
    sid: str,
    index: int,
    text: str,
    subcategory: Any,
    canonical_drugs: set[str],
    regimens: dict[str, tuple[str, ...]],
    drug_casefold: dict[str, str],
    regimen_casefold: dict[str, str],
    collector: ErrorCollector,
) -> tuple[str, tuple[Any, ...], set[str]] | None:
    label = f"regimen_mentions[{index}]"
    if not isinstance(mention, dict):
        collector.add("schema_errors", f"{sid}: {label} must be an object")
        return None
    missing = REQUIRED_REGIMEN_FIELDS - set(mention)
    extras = set(mention) - ALLOWED_REGIMEN_FIELDS
    if missing:
        collector.add("schema_errors", f"{sid}: {label} missing fields {sorted(missing)}")
    if extras:
        collector.add("schema_errors", f"{sid}: {label} has unknown fields {sorted(extras)}")

    surface = mention.get("regimen_surface")
    normalized = mention.get("regimen_normalized")
    _validate_span(
        sid=sid,
        object_label=label,
        text=text,
        surface=surface,
        start=mention.get("start_char"),
        end=mention.get("end_char"),
        collector=collector,
    )
    if not _nonempty_string(normalized):
        collector.add("schema_errors", f"{sid}: {label}.regimen_normalized must be a non-empty string")
        normalized = ""
    elif normalized not in regimens:
        hint = _display_case_hint(normalized, regimen_casefold)
        collector.add(
            "regimen_grounding_errors",
            f"{sid}: {label} uses noncanonical regimen {normalized!r}{hint}",
        )

    components_value = mention.get("components_normalized")
    components: list[str] = []
    if not isinstance(components_value, list):
        collector.add("schema_errors", f"{sid}: {label}.components_normalized must be an array")
    elif not components_value:
        collector.add("schema_errors", f"{sid}: {label}.components_normalized must not be empty")
    else:
        for component_index, component in enumerate(components_value):
            if not _nonempty_string(component):
                collector.add(
                    "schema_errors",
                    f"{sid}: {label}.components_normalized[{component_index}] "
                    "must be a non-empty string",
                )
                continue
            components.append(component)
            if component not in canonical_drugs:
                hint = _display_case_hint(component, drug_casefold)
                collector.add(
                    "drug_grounding_errors",
                    f"{sid}: {label} uses noncanonical component {component!r}{hint}",
                )
        if len({component.casefold() for component in components}) != len(components):
            collector.add("duplicate_errors", f"{sid}: {label} contains duplicate components")

    if normalized in regimens:
        expected = regimens[normalized]
        emitted_set = set(components)
        expected_set = set(expected)
        unknown = emitted_set - expected_set
        if unknown:
            collector.add(
                "regimen_grounding_errors",
                f"{sid}: {label} components not in {normalized!r}: {sorted(unknown)}",
            )
        if subcategory == "C3.1_multi_drug_explicit":
            # This task intentionally labels only explicitly visible components.
            if not emitted_set.issubset(expected_set):
                collector.add(
                    "regimen_grounding_errors",
                    f"{sid}: {label} explicit components are not a regimen subset",
                )
        elif tuple(components) != expected:
            collector.add(
                "regimen_grounding_errors",
                f"{sid}: {label} component sequence {components!r} does not equal "
                f"knowledge sequence {list(expected)!r}",
            )

    if "intent" in mention:
        intent = mention["intent"]
        if not isinstance(intent, str) or intent not in INTENTS:
            collector.add("schema_errors", f"{sid}: {label}.intent has invalid enum value {intent!r}")
        elif not _intent_is_visible(text, intent):
            collector.add(
                "text_evidence_errors",
                f"{sid}: {label}.intent={intent!r} lacks visible intent evidence",
            )

    if "cycle_info" in mention:
        cycle_info = mention["cycle_info"]
        if not _nonempty_string(cycle_info):
            collector.add("schema_errors", f"{sid}: {label}.cycle_info must be a non-empty string")
        else:
            parts = [part.strip() for part in cycle_info.split(",")]
            if any(not part for part in parts):
                collector.add("schema_errors", f"{sid}: {label}.cycle_info has an empty component")
            for part in filter(None, parts):
                if not _cycle_part_is_visible(text, part):
                    collector.add(
                        "text_evidence_errors",
                        f"{sid}: {label}.cycle_info component {part!r} lacks matching text evidence",
                    )

    if not normalized:
        return None
    identity = (
        surface.casefold() if isinstance(surface, str) else surface,
        normalized.casefold(),
        mention.get("start_char"),
        mention.get("end_char"),
    )
    return normalized, identity, set(components)


def _expected_distribution() -> tuple[int, dict[str, dict[str, int]], dict[str, str]]:
    quotas: dict[str, dict[str, int]] = {}
    difficulties: dict[str, str] = {}
    expected_total = 0
    for category, category_info in CATEGORY_DISTRIBUTION.items():
        quotas[category] = {}
        expected_total += category_info["total"]
        for subcategory, subcategory_info in category_info["subcategories"].items():
            quotas[category][subcategory] = subcategory_info["count"]
            difficulties[subcategory] = subcategory_info["difficulty"]
    return expected_total, quotas, difficulties


def validate_dataset(
    input_path: Path,
    report_path: Path | None = None,
    *,
    detail_limit: int = 100,
) -> dict[str, Any]:
    """Validate a JSONL release and write a deterministic JSON report."""
    input_path = Path(input_path)
    report_path = Path(report_path) if report_path is not None else input_path.parent / "validation_report.json"
    collector = ErrorCollector(detail_limit=detail_limit)
    expected_total, quotas, expected_difficulties = _expected_distribution()
    canonical_drugs, regimens = _load_knowledge(DRUG_TABLE_PATH, REGIMEN_TABLE_PATH, collector)
    drug_casefold = {name.casefold(): name for name in canonical_drugs}
    regimen_casefold = {name.casefold(): name for name in regimens}

    records: list[tuple[int, dict[str, Any]]] = []
    physical_lines = 0
    try:
        with input_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                physical_lines = line_number
                if not raw_line.strip():
                    collector.add("json_errors", f"line {line_number}: blank lines are not allowed")
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    collector.add(
                        "json_errors",
                        f"line {line_number}: invalid JSON at column {exc.colno}: {exc.msg}",
                    )
                    continue
                if not isinstance(value, dict):
                    collector.add("json_errors", f"line {line_number}: top-level JSON value must be an object")
                    continue
                records.append((line_number, value))
    except OSError as exc:
        collector.add("input_errors", f"cannot read {input_path}: {exc}")

    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    difficulty_counts: Counter[str] = Counter()
    seen_ids: dict[str, int] = {}
    valid_ids: set[str] = set()
    seen_texts: dict[str, str] = {}
    duplicate_text_count = 0

    for line_number, sample in records:
        raw_sid = sample.get("sample_id")
        sid = raw_sid if _nonempty_string(raw_sid) else f"line:{line_number}"

        missing_top = EXPECTED_TOP_LEVEL_FIELDS - set(sample)
        extra_top = set(sample) - EXPECTED_TOP_LEVEL_FIELDS
        if missing_top:
            collector.add("schema_errors", f"{sid}: missing top-level fields {sorted(missing_top)}")
        if extra_top:
            collector.add("schema_errors", f"{sid}: unknown top-level fields {sorted(extra_top)}")

        if not _nonempty_string(raw_sid):
            collector.add("schema_errors", f"line {line_number}: sample_id must be a non-empty string")
        else:
            match = SAMPLE_ID_PATTERN.fullmatch(raw_sid)
            if not match:
                collector.add("schema_errors", f"line {line_number}: malformed sample_id {raw_sid!r}")
            else:
                valid_ids.add(raw_sid)
                expected_id = f"ONCORX-{line_number:04d}"
                if raw_sid != expected_id:
                    collector.add(
                        "distribution_errors",
                        f"line {line_number}: expected ordered sample_id {expected_id!r}, got {raw_sid!r}",
                    )
            if raw_sid in seen_ids:
                collector.add(
                    "duplicate_errors",
                    f"{raw_sid}: duplicate sample_id (first seen on line {seen_ids[raw_sid]})",
                )
            else:
                seen_ids[raw_sid] = line_number

        text = sample.get("clinical_text")
        if not _nonempty_string(text):
            collector.add("schema_errors", f"{sid}: clinical_text must be a non-empty string")
            text = ""
        else:
            normalized_text = _normalize_space(text)
            prior_sid = seen_texts.get(normalized_text)
            if prior_sid is not None:
                collector.add("duplicate_errors", f"{sid}: clinical_text duplicates {prior_sid}")
                duplicate_text_count += 1
            else:
                seen_texts[normalized_text] = sid

        for finding in _find_placeholders(sample):
            collector.add("template_placeholder_errors", f"{sid}: unfilled placeholder at {finding}")

        category = sample.get("category")
        subcategory = sample.get("subcategory")
        if not _nonempty_string(category):
            collector.add("schema_errors", f"{sid}: category must be a non-empty string")
        elif category not in quotas:
            collector.add("distribution_errors", f"{sid}: unknown category {category!r}")
        if not _nonempty_string(subcategory):
            collector.add("schema_errors", f"{sid}: subcategory must be a non-empty string")
        elif category in quotas and subcategory not in quotas[category]:
            collector.add(
                "distribution_errors",
                f"{sid}: subcategory {subcategory!r} does not belong to {category!r}",
            )
        if isinstance(category, str) and isinstance(subcategory, str):
            category_counts[category][subcategory] += 1

        difficulty = sample.get("difficulty")
        if not isinstance(difficulty, str) or difficulty not in DIFFICULTY_LEVELS:
            collector.add("schema_errors", f"{sid}: invalid difficulty {difficulty!r}")
        else:
            difficulty_counts[difficulty] += 1
            expected_difficulty = expected_difficulties.get(subcategory)
            if expected_difficulty is not None and difficulty != expected_difficulty:
                collector.add(
                    "distribution_errors",
                    f"{sid}: difficulty {difficulty!r} != {expected_difficulty!r} for {subcategory}",
                )

        note_type = sample.get("note_type")
        if not isinstance(note_type, str) or note_type not in NOTE_TYPES:
            collector.add("schema_errors", f"{sid}: invalid note_type {note_type!r}")
        elif isinstance(text, str):
            prefix_type = next(
                (
                    expected_type
                    for prefix, expected_type in EXPLICIT_NOTE_PREFIXES.items()
                    if text.startswith(prefix)
                ),
                None,
            )
            if prefix_type is not None and note_type != prefix_type:
                collector.add(
                    "text_evidence_errors",
                    f"{sid}: note_type {note_type!r} contradicts explicit prefix "
                    f"for {prefix_type!r}",
                )
            elif (
                prefix_type is None
                and subcategory in NOTE_TYPES_BY_SUBCATEGORY
                and note_type not in NOTE_TYPES_BY_SUBCATEGORY[subcategory]
            ):
                collector.add(
                    "distribution_errors",
                    f"{sid}: note_type {note_type!r} is not allowed for {subcategory}",
                )

        drug_mentions = sample.get("drug_mentions")
        valid_drug_names: list[str] = []
        drug_identities: set[tuple[Any, ...]] = set()
        if not isinstance(drug_mentions, list):
            collector.add("schema_errors", f"{sid}: drug_mentions must be an array")
        elif not drug_mentions:
            collector.add("schema_errors", f"{sid}: drug_mentions must not be empty")
        else:
            for index, mention in enumerate(drug_mentions):
                result = _validate_drug_mention(
                    mention,
                    sid=sid,
                    index=index,
                    text=text,
                    canonical_drugs=canonical_drugs,
                    drug_casefold=drug_casefold,
                    collector=collector,
                )
                if result is None:
                    continue
                normalized, identity = result
                valid_drug_names.append(normalized)
                if identity in drug_identities:
                    collector.add(
                        "duplicate_errors",
                        f"{sid}: duplicate drug annotation at {identity[2]}:{identity[3]} "
                        f"for {normalized!r}",
                    )
                else:
                    drug_identities.add(identity)

        num_drugs = sample.get("num_drugs")
        unique_drug_count = len({name.casefold() for name in valid_drug_names})
        if not _is_int(num_drugs) or num_drugs < 0:
            collector.add("schema_errors", f"{sid}: num_drugs must be a non-negative integer")
        elif num_drugs != unique_drug_count:
            collector.add(
                "schema_errors",
                f"{sid}: num_drugs={num_drugs}, expected {unique_drug_count} unique normalized drugs",
            )

        regimen_mentions = sample.get("regimen_mentions")
        regimen_identities: set[tuple[Any, ...]] = set()
        if not isinstance(regimen_mentions, list):
            collector.add("schema_errors", f"{sid}: regimen_mentions must be an array")
        else:
            for index, mention in enumerate(regimen_mentions):
                result = _validate_regimen_mention(
                    mention,
                    sid=sid,
                    index=index,
                    text=text,
                    subcategory=subcategory,
                    canonical_drugs=canonical_drugs,
                    regimens=regimens,
                    drug_casefold=drug_casefold,
                    regimen_casefold=regimen_casefold,
                    collector=collector,
                )
                if result is None:
                    continue
                normalized, identity, _ = result
                if identity in regimen_identities:
                    collector.add(
                        "duplicate_errors",
                        f"{sid}: duplicate regimen annotation at {identity[2]}:{identity[3]} "
                        f"for {normalized!r}",
                    )
                else:
                    regimen_identities.add(identity)

        # If a drug annotation uses a regimen label as its surface, its target
        # must be one of that exact regimen row's canonical components.
        if isinstance(drug_mentions, list):
            regimen_surface_components: dict[str, set[str]] = defaultdict(set)
            if isinstance(regimen_mentions, list):
                for regimen_mention in regimen_mentions:
                    if not isinstance(regimen_mention, dict):
                        continue
                    regimen_surface = regimen_mention.get("regimen_surface")
                    regimen_components = regimen_mention.get("components_normalized")
                    if isinstance(regimen_surface, str) and isinstance(regimen_components, list):
                        regimen_surface_components[regimen_surface.casefold()].update(
                            component
                            for component in regimen_components
                            if isinstance(component, str)
                        )
            for index, mention in enumerate(drug_mentions):
                if not isinstance(mention, dict):
                    continue
                surface = mention.get("drug_surface")
                normalized = mention.get("drug_normalized")
                evidence_type = mention.get("evidence_type")
                regimen_components = (
                    regimen_surface_components.get(surface.casefold(), set())
                    if isinstance(surface, str)
                    else set()
                )
                should_be_inferred = bool(
                    regimen_components
                    and isinstance(normalized, str)
                    and surface.casefold() != normalized.casefold()
                )
                if evidence_type == "regimen_inference" and not should_be_inferred:
                    collector.add(
                        "text_evidence_errors",
                        f"{sid}: drug_mentions[{index}] is marked regimen_inference "
                        "without a matching regimen surface/component",
                    )
                elif evidence_type == "explicit_surface" and should_be_inferred:
                    collector.add(
                        "text_evidence_errors",
                        f"{sid}: drug_mentions[{index}] uses regimen evidence but is "
                        "marked explicit_surface",
                    )
                if evidence_type == "regimen_inference" and normalized not in regimen_components:
                    collector.add(
                        "regimen_grounding_errors",
                        f"{sid}: drug_mentions[{index}] inferred target {normalized!r} is not "
                        "in the matching regimen annotation",
                    )
                if surface in regimens and normalized not in regimens[surface]:
                    collector.add(
                        "regimen_grounding_errors",
                        f"{sid}: drug_mentions[{index}] maps regimen surface {surface!r} "
                        f"to noncomponent {normalized!r}",
                    )

    if len(records) != expected_total:
        collector.add(
            "distribution_errors",
            f"parsed sample count {len(records)} != required {expected_total}",
        )
    if physical_lines != expected_total:
        collector.add(
            "distribution_errors",
            f"physical JSONL line count {physical_lines} != required {expected_total}",
        )

    expected_ids = {f"ONCORX-{number:04d}" for number in range(1, expected_total + 1)}
    missing_ids = sorted(expected_ids - valid_ids)
    extra_ids = sorted(valid_ids - expected_ids)
    if missing_ids:
        preview = missing_ids[:10]
        suffix = f" (+{len(missing_ids) - len(preview)} more)" if len(missing_ids) > len(preview) else ""
        collector.add("distribution_errors", f"missing required sample IDs {preview}{suffix}")
    if extra_ids:
        preview = extra_ids[:10]
        suffix = f" (+{len(extra_ids) - len(preview)} more)" if len(extra_ids) > len(preview) else ""
        collector.add("distribution_errors", f"unexpected sample IDs {preview}{suffix}")

    for category, expected_subcategories in quotas.items():
        actual_category_total = sum(category_counts.get(category, Counter()).values())
        expected_category_total = CATEGORY_DISTRIBUTION[category]["total"]
        if actual_category_total != expected_category_total:
            collector.add(
                "distribution_errors",
                f"{category}: count {actual_category_total} != quota {expected_category_total}",
            )
        for subcategory, target in expected_subcategories.items():
            actual = category_counts.get(category, Counter()).get(subcategory, 0)
            if actual != target:
                collector.add(
                    "distribution_errors",
                    f"{subcategory}: count {actual} != quota {target}",
                )

    distribution_report = {
        category: {
            subcategory: category_counts.get(category, Counter()).get(subcategory, 0)
            for subcategory in subcategories
        }
        for category, subcategories in quotas.items()
    }
    for category in sorted(set(category_counts) - set(quotas)):
        distribution_report[category] = dict(sorted(category_counts[category].items()))

    error_counts = {group: collector.count(group) for group in ERROR_GROUPS}
    error_details = {
        group: collector.details.get(group, [])
        for group in ERROR_GROUPS
        if collector.count(group)
    }
    truncated = {
        group: collector.count(group) - len(collector.details.get(group, []))
        for group in ERROR_GROUPS
        if collector.count(group) > len(collector.details.get(group, []))
    }
    report: dict[str, Any] = {
        "passed": collector.total == 0,
        "total_errors": collector.total,
        "total_samples": len(records),
        "expected_samples": expected_total,
        "physical_lines": physical_lines,
        "knowledge_base": {
            "canonical_drugs": len(canonical_drugs),
            "canonical_regimen_rows": len(regimens),
            "drug_table": DRUG_TABLE_PATH.name,
            "regimen_table": REGIMEN_TABLE_PATH.name,
        },
        "error_counts": error_counts,
        "errors": error_details,
        "error_details_truncated": truncated,
        "category_distribution": distribution_report,
        "difficulty_distribution": dict(sorted(difficulty_counts.items())),
        # Backward-compatible scalar names retained for downstream scripts.
        "schema_errors": collector.count("schema_errors") + collector.count("json_errors"),
        "drug_grounding_errors": collector.count("drug_grounding_errors"),
        "regimen_grounding_errors": collector.count("regimen_grounding_errors"),
        "template_placeholder_errors": collector.count("template_placeholder_errors"),
        "duplicate_texts": duplicate_text_count,
    }

    try:
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except OSError as exc:
        # Writing the requested validation evidence is itself a release gate.
        report["passed"] = False
        report["total_errors"] += 1
        report["error_counts"]["input_errors"] += 1
        report.setdefault("errors", {}).setdefault("input_errors", []).append(
            f"cannot write report {report_path}: {exc}"
        )

    print(f"Validating: {input_path}")
    print(f"Samples: {len(records)}/{expected_total}")
    print(f"Knowledge: {len(canonical_drugs)} canonical drugs, {len(regimens)} regimen rows")
    print("Error summary:")
    for group in ERROR_GROUPS:
        print(f"  {group}: {report['error_counts'][group]}")
    print("PASS" if report["passed"] else f"FAIL ({report['total_errors']} errors)")
    print(f"Report: {report_path}")
    if not report["passed"]:
        for group in ERROR_GROUPS:
            details = report.get("errors", {}).get(group, [])
            for detail in details[:3]:
                print(f"  [{group}] {detail}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly validate an OncoRx-Bench release")
    parser.add_argument(
        "--input",
        type=Path,
        default=OUTPUT_DIR / "oncorx_bench.jsonl",
        help="JSONL artifact to validate",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON report path (default: validation_report.json beside input)",
    )
    parser.add_argument(
        "--max-error-details",
        type=int,
        default=100,
        help="maximum concrete examples retained per error group",
    )
    args = parser.parse_args()
    report = validate_dataset(
        args.input,
        report_path=args.report,
        detail_limit=args.max_error_details,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

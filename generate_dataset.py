#!/usr/bin/env python3
"""
OncoRx-Bench: Dataset generation pipeline.

Reads drug_table.csv and regimen_table.csv, fills clinical text templates
with grounded drug/regimen data, and produces annotated benchmark samples.

Usage:
    python generate_dataset.py              # generates to output/oncorx_bench.jsonl
    python generate_dataset.py --dry-run    # prints stats, writes nothing
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import string
from pathlib import Path
from typing import Optional

from schema import (
    BenchmarkSample,
    DrugMention,
    DrugStatus,
    Intent,
    RegimenMention,
    SigFields,
)
from dataset_config import (
    CATEGORY_DISTRIBUTION,
    DRUG_TABLE_PATH,
    REGIMEN_TABLE_PATH,
    CONDITIONS_PATH,
    OUTPUT_DIR,
    RANDOM_SEED,
    NOTE_TYPES,
    NOTE_TYPES_BY_SUBCATEGORY,
    SUPPORTIVE_CARE_DRUGS,
    DRUG_ABBREVIATIONS,
    MISSPELLING_PATTERNS,
    COMMON_DRUG_DOSES,
    ADVERSE_REACTIONS,
    ONCOLOGY_DRUGS,
    BRAND_NAME_MAP,
    PRN_DRUG_CONDITIONS,
    SUSPICIOUS_DRUG_BLOCKLIST,
    PREMEDICATION_APPROPRIATE,
    IV_ONLY_DRUGS,
    CUMULATIVE_DOSE_DRUGS,
    CUMULATIVE_DOSE_LIMITS,
    HIGH_NOISE_DRUGS,
    HIGH_NOISE_ALIASES,
)
from templates import TEMPLATES_BY_SUBCATEGORY


# ══════════════════════════════════════════════════════════════════════
# Knowledge-base loaders
# ══════════════════════════════════════════════════════════════════════

def _parse_list_cell(value: str) -> list[str]:
    """Parse current JSON-array cells and legacy comma-separated cells."""
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("Expected a JSON array of strings")
        return [item.strip() for item in parsed if item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def load_drug_table(path: Path) -> dict[str, list[str]]:
    """Load drug_table.csv → {generic_name: [synonym1, synonym2, ...]}"""
    drugs: dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            synonyms = _parse_list_cell(row[1])
            if name:
                drugs[name] = synonyms
    return drugs


def load_regimen_table(path: Path) -> dict[str, list[str]]:
    """Load regimen_table.csv → {regimen_name: [drug1, drug2, ...]}"""
    regimens: dict[str, list[str]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            components = _parse_list_cell(row[1])
            if name and components:
                regimens[name] = components
    return regimens


def load_regimen_ids(path: Path) -> dict[str, str]:
    """Load the optional UOTD regimen identifier for each published name."""
    result: dict[str, str] = {}
    with open(path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if "regimen_name" not in (reader.fieldnames or []):
            return result
        for row in reader:
            name = (row.get("regimen_name") or "").strip()
            regimen_id = (row.get("regimen_id") or "").strip()
            if name and regimen_id:
                result[name] = regimen_id
    return result


def load_conditions_by_regimen(
    condition_path: Path, regimen_path: Path
) -> dict[str, list[str]]:
    """Load UOTD-supported condition names for canonical names and aliases."""
    names_by_id: dict[str, list[str]] = {}
    for name, regimen_id in load_regimen_ids(regimen_path).items():
        names_by_id.setdefault(regimen_id, []).append(name)
    result: dict[str, set[str]] = {}
    with open(condition_path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            condition = (row.get("condition_name") or "").strip()
            regimen_id = (row.get("regimen_id") or "").strip()
            for name in names_by_id.get(regimen_id, []):
                if condition:
                    result.setdefault(name, set()).add(condition)
    return {
        name: sorted(values, key=str.casefold)
        for name, values in result.items()
    }


def load_conditions(path: Path) -> list[str]:
    """Load unique condition names from Conditions_And_Regimens.csv."""
    conditions = set()
    if not path.exists():
        raise FileNotFoundError(f"Required condition table is missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        name_idx = 1  # condition_name
        for row in reader:
            if len(row) > name_idx and row[name_idx].strip():
                conditions.add(row[name_idx].strip())
    if not conditions:
        raise ValueError(f"No condition names found in {path}")
    return sorted(conditions, key=str.casefold)


# ══════════════════════════════════════════════════════════════════════
# Random sampling helpers
# ══════════════════════════════════════════════════════════════════════

class DrugSampler:
    """Pulls diverse drugs from the knowledge base with dose information."""

    def __init__(self, drug_table: dict[str, list[str]], rng: random.Random):
        self.drug_table = drug_table
        self.all_drugs = list(drug_table.keys())
        self.by_casefold = {name.casefold(): name for name in self.all_drugs}
        self.rng = rng

        def resolve(values):
            return [self.by_casefold[value.casefold()] for value in values
                    if value.casefold() in self.by_casefold]

        # Curated oncology drugs that exist in the knowledge base
        self.oncology_drugs = resolve(ONCOLOGY_DRUGS)
        if not self.oncology_drugs:
            # Fallback to dosed drugs
            self.oncology_drugs = resolve(COMMON_DRUG_DOSES)

        self.dose_profiles: dict[str, dict[str, list[str]]] = {}
        for configured_name, profile in COMMON_DRUG_DOSES.items():
            canonical = self.by_casefold.get(configured_name.casefold())
            if canonical:
                self.dose_profiles[canonical] = {
                    "doses": list(profile["doses"]),
                    "routes": list(profile["routes"]),
                    "freq": list(profile["freq"]),
                }
        for configured_name, profile in PRN_DRUG_CONDITIONS.items():
            canonical = self.by_casefold.get(configured_name.casefold())
            if canonical and canonical not in self.dose_profiles:
                self.dose_profiles[canonical] = {
                    "doses": list(profile["doses"]),
                    "routes": list(profile["routes"]),
                    "freq": [profile["freq"]],
                }

        # Build reverse map: synonym → generic
        self.synonym_to_generic: dict[str, str] = {}
        self.generic_to_brands: dict[str, list[str]] = {}
        for generic, syns in drug_table.items():
            for syn in syns:
                self.synonym_to_generic[syn.lower()] = generic

        # Use explicit brand name map for reliable brand lookups
        # Build reverse: generic → [brand1, brand2, ...]
        _brand_reverse: dict[str, list[str]] = {}
        for brand, generic in BRAND_NAME_MAP.items():
            _brand_reverse.setdefault(generic, []).append(brand)
        self.generic_to_brands = _brand_reverse

        # Drugs that have dose info
        self.dosed_drugs = sorted(self.dose_profiles, key=str.casefold)
        # Drugs that have adverse reaction info
        self.adr_drugs = resolve(ADVERSE_REACTIONS)

    def random_drug(self) -> str:
        return self.rng.choice(self.all_drugs)

    def random_oncology_drug(self) -> str:
        """Return a curated oncology-relevant drug."""
        return self.rng.choice(self.oncology_drugs)

    def random_dosed_drug(self) -> str:
        return self.rng.choice(self.dosed_drugs) if self.dosed_drugs else self.random_oncology_drug()

    def random_dose(self, drug: str, required_route: str | None = None) -> dict:
        """Return {dose, route, freq} for a drug."""
        if drug not in self.dose_profiles:
            raise ValueError(f"No curated dose profile for {drug!r}")
        info = self.dose_profiles[drug]
        if required_route and required_route not in info["routes"]:
            raise ValueError(
                f"Dose profile for {drug!r} does not support {required_route}"
            )
        return {
            "dose": self.rng.choice(info["doses"]),
            "route": required_route or self.rng.choice(info["routes"]),
            "freq": self.rng.choice(info["freq"]),
        }

    def random_brand(self, drug: str) -> Optional[str]:
        brands = self.generic_to_brands.get(drug, [])
        return self.rng.choice(brands) if brands else None

    def random_supportive(self) -> str:
        candidates = [
            self.by_casefold[d.casefold()]
            for d in SUPPORTIVE_CARE_DRUGS
            if d.casefold() in self.by_casefold
            and self.by_casefold[d.casefold()] in self.dose_profiles
        ]
        if not candidates:
            candidates = SUPPORTIVE_CARE_DRUGS
        return self.rng.choice(candidates)

    def random_adr_drug(self) -> str:
        return self.rng.choice(self.adr_drugs) if self.adr_drugs else self.random_drug()


class RegimenSampler:
    """Pulls diverse regimens from the knowledge base."""

    def __init__(self, regimen_table: dict[str, list[str]], rng: random.Random,
                 drug_names_set: set[str] | None = None,
                 dose_profiles: dict[str, dict] | None = None,
                 conditions_by_regimen: dict[str, list[str]] | None = None):
        self.regimen_table = regimen_table
        self.rng = rng

        # Filter out regimens with suspicious/non-drug components
        blocked = {value.casefold() for value in SUSPICIOUS_DRUG_BLOCKLIST}
        known = {value.casefold() for value in (drug_names_set or set())}
        self.clean_table = {
            name: drugs for name, drugs in regimen_table.items()
            if drugs
            and not any(d.casefold() in blocked for d in drugs)
            and (not known or all(d.casefold() in known for d in drugs))
        }
        self.dose_profiles = dose_profiles or {}
        self.conditions_by_regimen = conditions_by_regimen or {}
        self.all_regimens = list(self.clean_table.keys())

        # Filter regimens with ≥2 components (for multi-drug scenarios)
        self.multi_drug_regimens = [r for r, drugs in self.clean_table.items() if len(drugs) >= 2]
        # Filter regimens with ≥3 components
        self.large_regimens = [r for r, drugs in self.clean_table.items() if len(drugs) >= 3]

        # Acronym-only regimens: name doesn't contain spelled-out drug names
        check_names = drug_names_set or set()
        self.acronym_regimens = [
            r for r in self.multi_drug_regimens
            if _is_acronym_name(r, check_names)
        ]

    def random_regimen(
        self,
        min_drugs: int = 1,
        max_drugs: int | None = None,
        require_dose_profiles: bool = False,
        require_iv: bool = False,
        require_oral: bool = False,
        require_condition: bool = False,
    ) -> tuple[str, list[str]]:
        candidates = [
            name for name, drugs in self.clean_table.items()
            if len(drugs) >= min_drugs
            and (max_drugs is None or len(drugs) <= max_drugs)
            and (not require_dose_profiles or all(d in self.dose_profiles for d in drugs))
            and (not require_iv or all(
                d in self.dose_profiles and "IV" in self.dose_profiles[d]["routes"]
                for d in drugs
            ))
            and (not require_oral or any(
                d in self.dose_profiles and "PO" in self.dose_profiles[d]["routes"]
                for d in drugs
            ))
            and (not require_condition or bool(self.conditions_by_regimen.get(name)))
        ]
        if not candidates:
            raise ValueError("No regimen satisfies the requested benchmark constraints")
        name = self.rng.choice(candidates)
        return name, self.clean_table[name]

    def random_acronym_regimen(
        self, min_drugs: int = 2, require_condition: bool = True
    ) -> tuple[str, list[str]]:
        """Return a regimen identified purely by its acronym."""
        candidates = [
            name for name in self.acronym_regimens
            if len(self.clean_table[name]) >= min_drugs
            and (not require_condition or bool(self.conditions_by_regimen.get(name)))
        ]
        if candidates:
            name = self.rng.choice(candidates)
            return name, self.clean_table[name]
        return self.random_regimen(
            min_drugs=min_drugs, require_condition=require_condition
        )

    def condition_for(self, regimen_name: str) -> str:
        conditions = self.conditions_by_regimen.get(regimen_name, [])
        if not conditions:
            raise ValueError(f"No UOTD condition association for {regimen_name!r}")
        return self.rng.choice(conditions)


# ══════════════════════════════════════════════════════════════════════
# Per-subcategory generators
# ══════════════════════════════════════════════════════════════════════

_LAST_TEMPLATE_TEXT: Optional[str] = None


def _pick_template(templates: list[str], rng: random.Random) -> str:
    """Select a template and retain its identity for the split manifest.

    The template identifier is release metadata only; it is deliberately not
    added to benchmark rows.  Recording it here lets the exporter construct a
    genuinely template-disjoint test split without trying to reverse-engineer
    a template from rendered clinical text.
    """
    global _LAST_TEMPLATE_TEXT
    selected = rng.choice(templates)
    _LAST_TEMPLATE_TEXT = selected
    return selected


def _note_type(
    rng: random.Random, subcategory: str, clinical_text: str | None = None
) -> str:
    if clinical_text:
        explicit_prefixes = {
            "Telephone encounter:": "telephone_encounter",
            "Discharge summary:": "discharge_summary",
            "Oncology consult:": "oncology_consult",
            "Infusion center note:": "nursing_note",
            "Med reconciliation:": "medication_reconciliation",
            "Progress note:": "progress_note",
        }
        for prefix, note_type in explicit_prefixes.items():
            if clinical_text.startswith(prefix):
                return note_type
    return rng.choice(NOTE_TYPES_BY_SUBCATEGORY.get(subcategory, NOTE_TYPES))


def _parse_dose_sig(dose_str: str) -> tuple[str, Optional[str]]:
    """Parse a dose string into (dose_value, dose_unit).
    Handles standard doses ('75 mg/m2') and AUC ('AUC 5').
    """
    if not dose_str:
        return (dose_str, None)
    if dose_str.upper().startswith("AUC"):
        parts = dose_str.split()
        return (parts[-1], "AUC") if len(parts) >= 2 else (dose_str, None)
    compact = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*"
        r"(mg/m2/day|mg/m2|g/m2|mg/kg|mcg/kg|units/m2|mg|mcg|units)",
        dose_str,
        flags=re.IGNORECASE,
    )
    if compact:
        return compact.group(1), compact.group(2)
    if " " not in dose_str:
        return (dose_str, None)
    parts = dose_str.split(maxsplit=1)
    return (parts[0], parts[1])


def _is_acronym_name(regimen_name: str, drug_names_lower: set[str]) -> bool:
    """Check if a regimen name is a pure acronym without spelled-out drug names."""
    name_lower = regimen_name.lower()
    for drug in drug_names_lower:
        if len(drug) >= 4 and drug in name_lower:
            return False
    return True


def _has_infusion_language(template: str) -> bool:
    """Check if a template implies IV infusion administration."""
    lower = template.lower()
    return ("infuse " in lower or "infusion" in lower
            or "over {infusion_time}" in lower
            or "administer over" in lower)


def _sample_intent(template: str, rng: random.Random) -> tuple[str, str | None]:
    """Return rendered intent text and a schema-valid, visible label."""
    values = [
        Intent.NEOADJUVANT.value,
        Intent.ADJUVANT.value,
        Intent.FIRST_LINE.value,
        Intent.SECOND_LINE.value,
        Intent.PALLIATIVE.value,
        Intent.CURATIVE.value,
        Intent.MAINTENANCE.value,
        Intent.INDUCTION.value,
        Intent.CONSOLIDATION.value,
        Intent.SALVAGE.value,
    ]
    lower = template.casefold()
    if "{intent}" in template:
        normalized_intent = rng.choice(values)
        return normalized_intent.replace("_", "-"), normalized_intent
    literal_map = [
        ("second-line", Intent.SECOND_LINE.value),
        ("third-line", Intent.THIRD_LINE_PLUS.value),
        ("maintenance", Intent.MAINTENANCE.value),
        ("consolidation", Intent.CONSOLIDATION.value),
        ("salvage", Intent.SALVAGE.value),
    ]
    for surface, normalized_intent in literal_map:
        if surface in lower:
            return surface, normalized_intent
    return "", None


def _visible_cycle_info(
    template: str,
    cycle_num: int,
    num_cycles: int,
    cycle_length: str,
) -> str | None:
    """Serialize only cycle values whose placeholders are visible in text."""
    parts = []
    if "{cycle_num}" in template and "{num_cycles}" in template:
        parts.append(f"cycle {cycle_num}/{num_cycles}")
    elif "{cycle_num}" in template:
        parts.append(f"cycle {cycle_num}")
    elif "{num_cycles}" in template:
        parts.append(f"{num_cycles} cycles")
    if "{cycle_length}" in template:
        parts.append(f"q{cycle_length}w")
    return ", ".join(parts) or None


def _literal_spans(text: str, surface: str) -> list[tuple[int, int]]:
    boundary_pattern = (
        r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])"
    )
    exact = [
        (match.start(), match.end())
        for match in re.finditer(boundary_pattern, text)
    ]
    if exact:
        return exact
    return [
        (match.start(), match.end())
        for match in re.finditer(boundary_pattern, text, flags=re.IGNORECASE)
    ]


def _ensure_explicit_coverage(sample: BenchmarkSample) -> None:
    """Add high-confidence explicit drugs omitted by scenario construction."""
    existing = {
        (mention["drug_surface"].casefold(), mention["drug_normalized"].casefold())
        for mention in sample.drug_mentions
    }
    candidates: dict[str, str] = {}
    for regimen in sample.regimen_mentions:
        for component in regimen.get("components_normalized", []):
            candidates[component] = component
    if sample.subcategory == "C5.4_high_noise":
        for drug in HIGH_NOISE_DRUGS:
            candidates[drug] = drug
        candidates.update(HIGH_NOISE_ALIASES)

    for surface, normalized_name in sorted(
        candidates.items(), key=lambda item: (-len(item[0]), item[0].casefold())
    ):
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        match = pattern.search(sample.clinical_text)
        key = (surface.casefold(), normalized_name.casefold())
        if match and key not in existing:
            actual_surface = sample.clinical_text[match.start():match.end()]
            status = (
                DrugStatus.HOLD.value
                if re.search(r"\bheld\s+" + re.escape(actual_surface), sample.clinical_text, re.I)
                else DrugStatus.CURRENT.value
            )
            sample.drug_mentions.append(
                DrugMention(
                    drug_surface=actual_surface,
                    drug_normalized=normalized_name,
                    status=status,
                ).to_dict()
            )
            existing.add((actual_surface.casefold(), normalized_name.casefold()))

    # When a regimen is the only textual evidence for a component, retain the
    # component normalization as an explicit regimen inference.  The shared
    # evidence span is distinguishable from a literal drug mention through
    # evidence_type and is therefore safe for regimen-resolution evaluation.
    existing_normalized = {
        mention["drug_normalized"].casefold()
        for mention in sample.drug_mentions
    }
    for regimen in sample.regimen_mentions:
        regimen_surface = regimen.get("regimen_surface", "")
        for component in regimen.get("components_normalized", []):
            if component.casefold() not in existing_normalized:
                sample.drug_mentions.append(
                    DrugMention(
                        drug_surface=regimen_surface,
                        drug_normalized=component,
                        evidence_type="regimen_inference",
                    ).to_dict()
                )
                existing_normalized.add(component.casefold())


def _assign_offsets(sample: BenchmarkSample) -> None:
    """Attach deterministic [start_char,end_char) evidence spans."""
    regimen_surfaces = {
        regimen["regimen_surface"].casefold()
        for regimen in sample.regimen_mentions
    }
    for objects, surface_key, normalized_key in (
        (sample.drug_mentions, "drug_surface", "drug_normalized"),
        (sample.regimen_mentions, "regimen_surface", "regimen_normalized"),
    ):
        occurrence_by_key: dict[tuple[str, str], int] = {}
        span_cache: dict[str, list[tuple[int, int]]] = {}
        for obj in objects:
            surface = obj.get(surface_key, "")
            spans = span_cache.setdefault(
                surface.casefold(), _literal_spans(sample.clinical_text, surface)
            )
            if not spans:
                raise ValueError(
                    f"{sample.sample_id}: surface {surface!r} is absent from clinical_text"
                )
            normalized_name = str(obj.get(normalized_key, "")).casefold()
            group = (surface.casefold(), normalized_name)
            occurrence = occurrence_by_key.get(group, 0)
            start, end = spans[min(occurrence, len(spans) - 1)]
            occurrence_by_key[group] = occurrence + 1
            obj["start_char"] = start
            obj["end_char"] = end
            # Preserve the exact evidence string, including source casing.
            obj[surface_key] = sample.clinical_text[start:end]
            if surface_key == "drug_surface":
                obj["evidence_type"] = (
                    "regimen_inference"
                    if surface.casefold() in regimen_surfaces
                    and surface.casefold() != normalized_name
                    else "explicit_surface"
                )


def _enrich_visible_sigs(sample: BenchmarkSample) -> None:
    """Backfill only dose/unit/route values visible next to a drug surface."""
    drug_starts = sorted(
        mention["start_char"] for mention in sample.drug_mentions
        if "start_char" in mention
    )
    regimen_surfaces = {
        regimen["regimen_surface"].casefold() for regimen in sample.regimen_mentions
    }
    dose_pattern = re.compile(
        r"\b(?:AUC\s+\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*"
        r"(?:mg/m2/day|mg/m2|g/m2|mg/kg|mcg/kg|units/m2|mg|mcg|units))\b",
        re.IGNORECASE,
    )
    # Generated route abbreviations are uppercase.  Case-sensitive matching is
    # intentional: otherwise ordinary prose such as "patient opted against it"
    # is mislabeled as the intrathecal route (IT).
    route_pattern = re.compile(r"\b(PO|IV|SC|IM|IT|PR|SL)\b")
    for mention in sample.drug_mentions:
        # Component labels inferred from a regimen acronym share the regimen
        # evidence span and should not receive a fabricated per-drug sig.
        if mention.get("evidence_type") == "regimen_inference":
            continue
        start = mention["end_char"]
        following = [value for value in drug_starts if value > start]
        stop = min(following) if following else len(sample.clinical_text)
        sentence_stop = sample.clinical_text.find(".", start, stop)
        if sentence_stop >= 0:
            stop = sentence_stop
        window = sample.clinical_text[start:min(stop, start + 100)]
        sig = dict(mention.get("sig") or {})
        dose_match = dose_pattern.search(window)
        if dose_match and "dose_value" not in sig:
            dose_value, dose_unit = _parse_dose_sig(dose_match.group(0))
            sig["dose_value"] = dose_value
            if dose_unit:
                sig["dose_unit"] = dose_unit
        route_match = route_pattern.search(window)
        if route_match and "route" not in sig:
            sig["route"] = route_match.group(1).upper()
        if sig:
            mention["sig"] = sig


def _deduplicate_drug_mentions(sample: BenchmarkSample) -> None:
    """Merge exact duplicate annotations and fail on conflicting duplicates."""
    unique: dict[tuple[int, int, str], dict] = {}
    for mention in sample.drug_mentions:
        key = (
            mention["start_char"],
            mention["end_char"],
            mention["drug_normalized"].casefold(),
        )
        previous = unique.get(key)
        if previous is None:
            unique[key] = mention
            continue
        if previous["status"] != mention["status"]:
            raise ValueError(
                f"{sample.sample_id}: conflicting statuses for duplicate {key}"
            )
        for flag in ("negated", "allergy", "uncertain"):
            previous[flag] = bool(previous.get(flag) or mention.get(flag))
        for optional in ("reason", "adverse_event", "sig"):
            incoming = mention.get(optional)
            if not incoming:
                continue
            if previous.get(optional) not in (None, incoming):
                raise ValueError(
                    f"{sample.sample_id}: conflicting {optional} for duplicate {key}"
                )
            previous[optional] = incoming
        if mention.get("evidence_type") == "explicit_surface":
            previous["evidence_type"] = "explicit_surface"
    sample.drug_mentions = list(unique.values())


def _finalize_sample(sample: BenchmarkSample) -> BenchmarkSample:
    _ensure_explicit_coverage(sample)
    _assign_offsets(sample)
    _enrich_visible_sigs(sample)
    _deduplicate_drug_mentions(sample)
    sample.num_drugs = len({
        mention["drug_normalized"].casefold()
        for mention in sample.drug_mentions
    })
    return sample


def generate_c1_1(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C1.1 — Single drug, simple mention."""
    templates = TEMPLATES_BY_SUBCATEGORY["C1.1_single_drug_simple"]
    drug = sampler.random_oncology_drug()
    tpl = _pick_template(templates, rng)
    text = tpl.format(drug1=drug)

    dm = DrugMention(drug_surface=drug, drug_normalized=drug)
    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C1_CORE_MED_EXTRACTION",
        subcategory="C1.1_single_drug_simple",
        difficulty="Easy",
        drug_mentions=[dm.to_dict()],
        num_drugs=1,
        note_type=_note_type(rng, "C1.1_single_drug_simple"),
    )


def generate_c1_2(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C1.2 — Single drug with dose/route."""
    templates = TEMPLATES_BY_SUBCATEGORY["C1.2_single_drug_dose"]
    drug = sampler.random_dosed_drug()
    dose_info = sampler.random_dose(drug)
    tpl = _pick_template(templates, rng)

    # Avoid infusion language for non-IV drugs
    if _has_infusion_language(tpl) and dose_info["route"] != "IV":
        non_infusion = [t for t in templates if not _has_infusion_language(t)]
        tpl = _pick_template(non_infusion, rng)

    text = tpl.format(
        drug1=drug, dose1=dose_info["dose"],
        route1=dose_info["route"], freq1=dose_info["freq"],
    )

    dv, du = _parse_dose_sig(dose_info["dose"])
    sig_kwargs = {"dose_value": dv, "dose_unit": du, "route": dose_info["route"]}
    if "{freq1}" in tpl:
        sig_kwargs["frequency"] = dose_info["freq"]
    sig = SigFields(**sig_kwargs)
    dm = DrugMention(drug_surface=drug, drug_normalized=drug, sig=sig.to_dict())
    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C1_CORE_MED_EXTRACTION",
        subcategory="C1.2_single_drug_dose",
        difficulty="Easy",
        drug_mentions=[dm.to_dict()],
        num_drugs=1,
        note_type=_note_type(rng, "C1.2_single_drug_dose"),
    )


def generate_c1_3(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C1.3 — Two drugs mentioned together."""
    templates = TEMPLATES_BY_SUBCATEGORY["C1.3_two_drugs"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()

    d1_info = sampler.random_dose(drug1)
    d2_info = sampler.random_dose(drug2)
    tpl = _pick_template(templates, rng)

    text = tpl.format(
        drug1=drug1, drug2=drug2,
        dose1=d1_info["dose"], route1=d1_info["route"],
        dose2=d2_info["dose"], route2=d2_info["route"],
    )

    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1)
    dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2)
    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C1_CORE_MED_EXTRACTION",
        subcategory="C1.3_two_drugs",
        difficulty="Medium",
        drug_mentions=[dm1.to_dict(), dm2.to_dict()],
        num_drugs=2,
        note_type=_note_type(rng, "C1.3_two_drugs"),
    )


def generate_c1_4(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C1.4 — Supportive care medications."""
    templates = TEMPLATES_BY_SUBCATEGORY["C1.4_supportive_care"]
    tpl = _pick_template(templates, rng)

    # Use PRN_DRUG_CONDITIONS for clinically grounded drug-dose-indication pairings
    prn_drugs = [d for d in PRN_DRUG_CONDITIONS if d in sampler.all_drugs]
    if not prn_drugs:
        prn_drugs = list(PRN_DRUG_CONDITIONS.keys())

    # For premedication/prophylaxis templates, restrict to appropriate drugs
    tpl_lower = tpl.lower()
    if "premedication" in tpl_lower or "prophylaxis" in tpl_lower:
        drug_pool = [d for d in prn_drugs if d in PREMEDICATION_APPROPRIATE]
        if not drug_pool:
            drug_pool = prn_drugs
    else:
        drug_pool = prn_drugs

    drug1_name = rng.choice(drug_pool)
    drug2_name = rng.choice(drug_pool)
    while drug2_name == drug1_name:
        drug2_name = rng.choice(drug_pool)
    drug3 = sampler.random_dosed_drug()  # the chemo drug

    d1_info = PRN_DRUG_CONDITIONS[drug1_name]
    d2_info = PRN_DRUG_CONDITIONS[drug2_name]
    d3_dose = sampler.random_dose(drug3)

    d1_dose = rng.choice(d1_info["doses"])
    d1_route = rng.choice(d1_info["routes"])
    d2_dose = rng.choice(d2_info["doses"])
    d2_route = rng.choice(d2_info["routes"])

    text = tpl.format(
        drug1=drug1_name, drug2=drug2_name, drug3=drug3,
        dose1=d1_dose, route1=d1_route,
        dose2=d2_dose, route2=d2_route,
        dose3=d3_dose["dose"], route3=d3_dose["route"],
    )

    mentions = []
    # Extract drugs that actually appear in the rendered text
    for d in [drug1_name, drug2_name, drug3]:
        if d in text:
            mentions.append(DrugMention(drug_surface=d, drug_normalized=d).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C1_CORE_MED_EXTRACTION",
        subcategory="C1.4_supportive_care",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C1.4_supportive_care"),
    )


# ── C2 generators ─────────────────────────────────────────────────────

def generate_c2_1(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C2.1 — Full dose + route + frequency."""
    templates = TEMPLATES_BY_SUBCATEGORY["C2.1_dose_route_freq"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()

    d1 = sampler.random_dose(drug1)
    d2 = sampler.random_dose(drug2)
    tpl = _pick_template(templates, rng)
    if tpl.startswith("Dexamethasone taper") and "Dexamethasone" in taper_drugs:
        drug1 = "Dexamethasone"
        schedule = rng.choice(taper_schedules[drug1])
        dose_high, dose_med, dose_low, increment = schedule

    # Avoid infusion templates for non-IV drugs
    if _has_infusion_language(tpl) and d1["route"] != "IV":
        non_infusion = [t for t in templates if not _has_infusion_language(t)]
        tpl = _pick_template(non_infusion, rng)

    cycle_num = rng.randint(1, 8)
    cycle_day = rng.choice(["1", "1,8", "1,8,15", "1-3", "1-5"])
    infusion_time = rng.choice(["30 minutes", "1 hour", "2 hours", "3 hours", "90 minutes"])
    num_doses = rng.randint(1, 4)

    text = tpl.format(
        drug1=drug1, drug2=drug2,
        dose1=d1["dose"], route1=d1["route"], freq1=d1["freq"],
        dose2=d2["dose"], route2=d2["route"], freq2=d2["freq"],
        cycle_num=cycle_num, cycle_day=cycle_day,
        infusion_time=infusion_time, num_doses=num_doses,
    )

    dv1, du1 = _parse_dose_sig(d1["dose"])
    sig1 = SigFields(
        dose_value=dv1, dose_unit=du1,
        route=d1["route"], frequency=d1["freq"],
    )
    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, sig=sig1.to_dict())

    mentions = [dm1.to_dict()]
    if drug2 in text:
        dv2, du2 = _parse_dose_sig(d2["dose"])
        sig2 = SigFields(
            dose_value=dv2, dose_unit=du2,
            route=d2["route"],
        )
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2, sig=sig2.to_dict())
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C2_ATTRIBUTES_SIG",
        subcategory="C2.1_dose_route_freq",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C2.1_dose_route_freq"),
    )


def generate_c2_2(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C2.2 — Titration / taper instructions."""
    templates = TEMPLATES_BY_SUBCATEGORY["C2.2_titration_taper"]
    # Taper drugs with clinically appropriate dose schedules
    taper_schedules = {
        "Dexamethasone": [
            ("40 mg", "20 mg", "10 mg", "10 mg"),
            ("20 mg", "10 mg", "4 mg", "4 mg"),
            ("12 mg", "8 mg", "4 mg", "4 mg"),
        ],
        "Prednisone": [
            ("60 mg", "40 mg", "20 mg", "10 mg"),
            ("40 mg", "20 mg", "10 mg", "10 mg"),
            ("80 mg", "60 mg", "40 mg", "20 mg"),
        ],
        "Methylprednisolone": [
            ("32 mg", "16 mg", "8 mg", "8 mg"),
            ("24 mg", "16 mg", "8 mg", "8 mg"),
        ],
        "Hydrocortisone": [
            ("40 mg", "30 mg", "20 mg", "10 mg"),
            ("60 mg", "40 mg", "20 mg", "10 mg"),
        ],
    }
    taper_drugs = [d for d in taper_schedules if d in sampler.all_drugs]
    if not taper_drugs:
        taper_drugs = list(taper_schedules.keys())

    drug1 = rng.choice(taper_drugs)
    drug2 = sampler.random_dosed_drug()
    while drug2.casefold() == drug1.casefold():
        drug2 = sampler.random_dosed_drug()

    schedule = rng.choice(taper_schedules[drug1])
    dose_high, dose_med, dose_low, increment = schedule

    d2 = sampler.random_dose(drug2)
    tpl = _pick_template(templates, rng)

    text = tpl.format(
        drug1=drug1, drug2=drug2,
        dose1_high=dose_high, dose1_med=dose_med, dose1_low=dose_low,
        dose1_increment=increment,
        route1="PO",
        dose2=d2["dose"], dose2_increment="varies",
    )

    sig_kwargs = {}
    visible_doses = sorted(
        (
            (tpl.find(placeholder), value)
            for placeholder, value in (
                ("{dose1_low}", dose_low),
                ("{dose1_med}", dose_med),
                ("{dose1_high}", dose_high),
            )
            if placeholder in tpl
        ),
        key=lambda item: item[0],
    )
    ordered_values = list(dict.fromkeys(value for _, value in visible_doses))
    if ordered_values:
        starting_dose = ordered_values[0]
        if len(ordered_values) >= 2:
            sig_kwargs["taper"] = " → ".join(ordered_values)
        dose_value, dose_unit = _parse_dose_sig(starting_dose)
        sig_kwargs["dose_value"] = dose_value
        sig_kwargs["dose_unit"] = dose_unit
    elif tpl.startswith("Dexamethasone taper"):
        sig_kwargs.update({
            "dose_value": "40",
            "dose_unit": "mg",
            "route": "PO",
            "taper": "40 mg → 20 mg → 10 mg",
        })
    if "{route1}" in tpl:
        sig_kwargs["route"] = "PO"
    sig = SigFields(**sig_kwargs)
    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, sig=sig.to_dict())
    mentions = [dm1.to_dict()]
    if "{drug2}" in tpl:
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C2_ATTRIBUTES_SIG",
        subcategory="C2.2_titration_taper",
        difficulty="Hard",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C2.2_titration_taper"),
    )


def generate_c2_3(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C2.3 — PRN / conditional dosing."""
    templates = TEMPLATES_BY_SUBCATEGORY["C2.3_prn_conditional"]

    # Use clinically appropriate drug-condition pairings
    prn_drug_names = [d for d in PRN_DRUG_CONDITIONS if d in sampler.all_drugs]
    if not prn_drug_names:
        prn_drug_names = list(PRN_DRUG_CONDITIONS.keys())

    drug1_name = rng.choice(prn_drug_names)
    d1_info = PRN_DRUG_CONDITIONS[drug1_name]
    d1_dose = rng.choice(d1_info["doses"])
    d1_route = rng.choice(d1_info["routes"])
    d1_freq = d1_info["freq"]
    d1_condition = rng.choice(d1_info["conditions"])

    tpl = _pick_template(templates, rng)

    # For escalation templates (mild/severe, standing/PRN) ensure drug2 treats same condition
    tpl_lower = tpl.lower()

    # Strip severity prefix from condition when template already specifies severity
    if "for mild" in tpl_lower or "for severe" in tpl_lower:
        d1_condition = re.sub(r'^(mild|moderate|severe)\s+', '', d1_condition)

    if "for mild" in tpl_lower or "for severe" in tpl_lower or ("standing:" in tpl_lower and "prn:" in tpl_lower):
        compatible = [d for d in prn_drug_names
                      if d != drug1_name and d1_condition in PRN_DRUG_CONDITIONS[d]["conditions"]]
        drug2_name = rng.choice(compatible) if compatible else drug1_name
        while drug2_name == drug1_name and len(prn_drug_names) > 1:
            drug2_name = rng.choice(prn_drug_names)
    else:
        drug2_name = rng.choice(prn_drug_names)
        while drug2_name == drug1_name:
            drug2_name = rng.choice(prn_drug_names)

    d2_info = PRN_DRUG_CONDITIONS[drug2_name]
    d2_dose = rng.choice(d2_info["doses"])
    d2_route = rng.choice(d2_info["routes"])
    d2_condition = rng.choice(d2_info["conditions"])

    text = tpl.format(
        drug1=drug1_name, drug2=drug2_name,
        dose1=d1_dose, route1=d1_route, freq1=d1_freq,
        dose2=d2_dose, route2=d2_route,
        dose1_low=d1_info["doses"][0],
        dose1_med=d1_info["doses"][len(d1_info["doses"])//2] if len(d1_info["doses"]) > 1 else d1_info["doses"][0],
        dose1_high=d1_info["doses"][-1],
        prn_reason=d1_condition,
        prn_reason2=d2_condition,
        prn_interval=d1_freq.replace("q", ""),
        max_daily=rng.choice(["3 doses", "4 doses"]),
        max_doses=rng.choice(["3", "4", "6"]),
    )

    drug1_is_standing = "standing:" in tpl_lower and "prn:" in tpl_lower
    sig1_kwargs = {"prn": not drug1_is_standing}
    if "{dose1}" in tpl:
        dose_value, dose_unit = _parse_dose_sig(d1_dose)
        sig1_kwargs["dose_value"] = dose_value
        sig1_kwargs["dose_unit"] = dose_unit
    if "{route1}" in tpl:
        sig1_kwargs["route"] = d1_route
    sig1 = SigFields(**sig1_kwargs)
    dm1 = DrugMention(drug_surface=drug1_name, drug_normalized=drug1_name, sig=sig1.to_dict())
    mentions = [dm1.to_dict()]
    if drug2_name in text:
        sig2_kwargs = {"prn": True}
        if "{dose2}" in tpl:
            dose_value, dose_unit = _parse_dose_sig(d2_dose)
            sig2_kwargs["dose_value"] = dose_value
            sig2_kwargs["dose_unit"] = dose_unit
        if "{route2}" in tpl:
            sig2_kwargs["route"] = d2_route
        sig2 = SigFields(**sig2_kwargs)
        dm2 = DrugMention(drug_surface=drug2_name, drug_normalized=drug2_name, sig=sig2.to_dict())
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C2_ATTRIBUTES_SIG",
        subcategory="C2.3_prn_conditional",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C2.3_prn_conditional"),
    )


def generate_c2_4(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C2.4 — Duration and stop instructions."""
    templates = TEMPLATES_BY_SUBCATEGORY["C2.4_duration_stop"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()
    d1 = sampler.random_dose(drug1)

    durations = ["7 days", "14 days", "21 days", "28 days", "3 months",
                 "6 months", "1 year", "2 years", "5 years"]
    stop_conditions = ["ANC < 500", "severe mucositis", "grade 3+ toxicity",
                       "disease progression", "patient request", "intolerable side effects"]
    stop_dates = ["03/15/2024", "06/01/2024", "the end of cycle 6"]
    cycle_lengths = ["21", "28", "14"]

    # Pick values once so annotations match what appears in the text
    chosen_duration = rng.choice(durations)
    num_cycles_val = rng.randint(2, 8)
    chosen_stop_date = rng.choice(stop_dates)
    chosen_cycle_length = rng.choice(cycle_lengths)

    tpl = _pick_template(templates, rng)
    text = tpl.format(
        drug1=drug1, drug2=drug2,
        dose1=d1["dose"], route1=d1["route"], freq1=" " + d1["freq"],
        duration=chosen_duration,
        num_cycles=num_cycles_val,
        stop_condition=rng.choice(stop_conditions),
        stop_date=chosen_stop_date,
        last_day=rng.choice(["5", "14", "21"]),
        cycle_length=chosen_cycle_length,
    )

    # Derive sig duration from what actually appears in the rendered text
    if "{num_cycles}" in tpl and "{duration}" not in tpl:
        sig_duration = f"{num_cycles_val} cycles"
    elif "2 years" in tpl:
        sig_duration = "2 years"
    elif "until disease progression" in tpl:
        sig_duration = "until disease progression or unacceptable toxicity"
    elif "{stop_date}" in tpl and "{duration}" not in tpl:
        sig_duration = f"until {chosen_stop_date}"
    else:
        sig_duration = chosen_duration

    sig_kwargs = {"duration": sig_duration}
    if "{dose1}" in tpl:
        dv, du = _parse_dose_sig(d1["dose"])
        sig_kwargs["dose_value"] = dv
        sig_kwargs["dose_unit"] = du
    if "{route1}" in tpl:
        sig_kwargs["route"] = d1["route"]
    if "{freq1}" in tpl:
        sig_kwargs["frequency"] = d1["freq"]
    sig = SigFields(**sig_kwargs)
    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, sig=sig.to_dict())
    mentions = [dm1.to_dict()]
    if drug2 in text:
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C2_ATTRIBUTES_SIG",
        subcategory="C2.4_duration_stop",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C2.4_duration_stop"),
    )


# ── C3 generators ─────────────────────────────────────────────────────

def generate_c3_1(sampler: DrugSampler, reg_sampler: RegimenSampler,
                   conditions: list[str], rng: random.Random, idx: int) -> BenchmarkSample:
    """C3.1 — Multi-drug regimen, explicit drugs."""
    templates = TEMPLATES_BY_SUBCATEGORY["C3.1_multi_drug_explicit"]
    tpl = _pick_template(templates, rng)
    required_slots = max(
        [int(value) for value in re.findall(r"\{drug([1-4])\}", tpl)] or [2]
    )
    regimen_name, components = reg_sampler.random_regimen(
        min_drugs=required_slots,
        max_drugs=required_slots,
        require_dose_profiles=True,
        require_iv=_has_infusion_language(tpl) or " IV" in tpl,
    )
    drugs = list(components)
    force_iv = _has_infusion_language(tpl) or " IV" in tpl
    dose_infos = [
        sampler.random_dose(drug, required_route="IV" if force_iv else None)
        for drug in drugs
    ]

    cycle_length = rng.choice(["2", "3", "4"])
    num_cycles = rng.randint(3, 8)
    cycle_num = rng.randint(1, num_cycles)

    # Ensure fallback values are DIFFERENT drugs, not drug[0] duplicated
    fmt_kwargs = {
        "drug1": drugs[0], "dose1": dose_infos[0]["dose"], "route1": dose_infos[0]["route"],
        "drug2": drugs[1],
        "dose2": dose_infos[1]["dose"],
        "route2": dose_infos[1]["route"],
        "drug3": drugs[2] if len(drugs) > 2 else "",
        "dose3": dose_infos[2]["dose"] if len(dose_infos) > 2 else "",
        "route3": dose_infos[2]["route"] if len(dose_infos) > 2 else "",
        "drug4": drugs[3] if len(drugs) > 3 else "",
        "regimen_name": regimen_name,
        "cycle_length": cycle_length,
        "num_cycles": num_cycles,
        "cycle_num": cycle_num,
    }

    text = tpl.format(**fmt_kwargs)

    drug_mentions = []
    seen_drugs_in_text = set()
    for d in drugs:
        if d in text and d not in seen_drugs_in_text:
            drug_mentions.append(
                DrugMention(drug_surface=d, drug_normalized=d).to_dict()
            )
            seen_drugs_in_text.add(d)

    regimen_mentions = []
    if regimen_name in text:
        # Only include components that are explicitly visible in the text
        visible_components = [c for c in dict.fromkeys(components) if c in text]
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name,
            regimen_normalized=regimen_name,
            components_normalized=visible_components,
            cycle_info=_visible_cycle_info(
                tpl, cycle_num, num_cycles, cycle_length
            ),
        ).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C3_REGIMEN_ONCOLOGY",
        subcategory="C3.1_multi_drug_explicit",
        difficulty="Hard",
        drug_mentions=drug_mentions,
        regimen_mentions=regimen_mentions,
        num_drugs=len(drug_mentions),
        note_type=_note_type(rng, "C3.1_multi_drug_explicit"),
    )


def generate_c3_2(reg_sampler: RegimenSampler, conditions: list[str],
                   rng: random.Random, idx: int) -> BenchmarkSample:
    """C3.2 — Regimen acronym only."""
    templates = TEMPLATES_BY_SUBCATEGORY["C3.2_regimen_acronym_only"]
    regimen_name, components = reg_sampler.random_acronym_regimen()
    regimen_name_prev, _ = reg_sampler.random_acronym_regimen()
    while regimen_name_prev == regimen_name:
        regimen_name_prev, _ = reg_sampler.random_acronym_regimen()

    regimen_name_prev, components_prev = regimen_name_prev, reg_sampler.clean_table[regimen_name_prev]
    condition = reg_sampler.condition_for(regimen_name)

    cycle_length = rng.choice(["2", "3", "4"])
    num_cycles = rng.randint(3, 8)
    cycle_num = rng.randint(1, num_cycles)
    tpl = _pick_template(templates, rng)
    intent_surface, intent_normalized = _sample_intent(tpl, rng)
    text = tpl.format(
        regimen_name=regimen_name,
        regimen_name_prev=regimen_name_prev,
        condition=condition, intent=intent_surface,
        cycle_length=cycle_length, num_cycles=num_cycles,
        cycle_num=cycle_num,
    )

    # Drug mentions: each component of the regimen is an expected extraction
    drug_mentions = [
        DrugMention(drug_surface=regimen_name, drug_normalized=c).to_dict()
        for c in components
    ]
    if regimen_name_prev in text:
        drug_mentions.extend(
            DrugMention(
                drug_surface=regimen_name_prev,
                drug_normalized=component,
                status=DrugStatus.HISTORICAL.value,
            ).to_dict()
            for component in components_prev
        )

    regimen_mention = RegimenMention(
        regimen_surface=regimen_name,
        regimen_normalized=regimen_name,
        components_normalized=components,
        cycle_info=_visible_cycle_info(tpl, cycle_num, num_cycles, cycle_length),
        intent=intent_normalized,
    ).to_dict()
    regimen_mentions = [regimen_mention]
    if regimen_name_prev in text:
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name_prev,
            regimen_normalized=regimen_name_prev,
            components_normalized=components_prev,
        ).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C3_REGIMEN_ONCOLOGY",
        subcategory="C3.2_regimen_acronym_only",
        difficulty="Hard",
        drug_mentions=drug_mentions,
        regimen_mentions=regimen_mentions,
        num_drugs=len({mention["drug_normalized"] for mention in drug_mentions}),
        note_type=_note_type(rng, "C3.2_regimen_acronym_only"),
    )


def generate_c3_3(sampler: DrugSampler, reg_sampler: RegimenSampler,
                   rng: random.Random, idx: int) -> BenchmarkSample:
    """C3.3 — Regimen with partial drug listing."""
    templates = TEMPLATES_BY_SUBCATEGORY["C3.3_regimen_partial"]
    tpl = _pick_template(templates, rng)
    regimen_name, components = reg_sampler.random_regimen(
        min_drugs=3,
        require_dose_profiles=("{oral_drug}" in tpl or _has_infusion_language(tpl) or " IV" in tpl),
        require_iv=(_has_infusion_language(tpl) or " IV" in tpl),
        require_oral="{oral_drug}" in tpl,
    )

    # Show subset of drugs
    n_shown = max(1, len(components) // 2)
    shown_drugs = rng.sample(components, min(n_shown, len(components)))
    partial_drugs = " and ".join(shown_drugs)
    oral_candidates = [
        component for component in components
        if component in sampler.dose_profiles
        and "PO" in sampler.dose_profiles[component]["routes"]
    ]
    oral_drug = rng.choice(oral_candidates) if oral_candidates else shown_drugs[0]
    text = tpl.format(
        regimen_name=regimen_name,
        partial_drugs=partial_drugs,
        oral_drug=oral_drug,
        cycle_num=rng.randint(1, 6),
        cycle_day=rng.choice(["1", "8", "15"]),
        next_day=rng.choice(["8", "15", "22"]),
    )

    # All components are expected even though only some are named
    drug_mentions = []
    for d in shown_drugs:
        drug_mentions.append(DrugMention(drug_surface=d, drug_normalized=d).to_dict())

    regimen_mention = RegimenMention(
        regimen_surface=regimen_name,
        regimen_normalized=regimen_name,
        components_normalized=components,
    ).to_dict()

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C3_REGIMEN_ONCOLOGY",
        subcategory="C3.3_regimen_partial",
        difficulty="Very Hard",
        drug_mentions=drug_mentions,
        regimen_mentions=[regimen_mention],
        num_drugs=len(drug_mentions),
        note_type=_note_type(rng, "C3.3_regimen_partial"),
    )


def generate_c3_4(reg_sampler: RegimenSampler, conditions: list[str],
                   rng: random.Random, idx: int) -> BenchmarkSample:
    """C3.4 — Cycles, lines, intent metadata."""
    templates = TEMPLATES_BY_SUBCATEGORY["C3.4_cycles_lines_intent"]
    regimen_name, components = reg_sampler.random_regimen(
        min_drugs=2, require_condition=True
    )
    regimen_name_prev, comp_prev = reg_sampler.random_regimen(
        min_drugs=2, require_condition=True
    )
    while regimen_name_prev == regimen_name:
        regimen_name_prev, comp_prev = reg_sampler.random_regimen(
            min_drugs=2, require_condition=True
        )

    condition = reg_sampler.condition_for(regimen_name)
    stages = ["I", "II", "IIA", "IIB", "III", "IIIA", "IIIB", "IV"]

    num_cycles = rng.randint(4, 8)
    cycle_num = rng.randint(1, num_cycles)
    cycle_length = rng.choice(["2", "3", "4"])
    tpl = _pick_template(templates, rng)
    intent_surface, intent_normalized = _sample_intent(tpl, rng)

    text = tpl.format(
        regimen_name=regimen_name,
        regimen_name_prev=regimen_name_prev,
        condition=condition, intent=intent_surface,
        cycle_length=cycle_length, num_cycles=num_cycles,
        num_cycles_2=rng.randint(2, 4),
        num_cycles_prev=rng.randint(4, 6),
        cycle_num=cycle_num,
        stage=rng.choice(stages),
    )

    drug_mentions = [
        DrugMention(drug_surface=regimen_name, drug_normalized=c).to_dict()
        for c in components
    ]
    if regimen_name_prev in text:
        drug_mentions.extend(
            DrugMention(
                drug_surface=regimen_name_prev,
                drug_normalized=component,
                status=DrugStatus.HISTORICAL.value,
            ).to_dict()
            for component in comp_prev
        )

    regimen_mention = RegimenMention(
        regimen_surface=regimen_name,
        regimen_normalized=regimen_name,
        components_normalized=components,
        cycle_info=_visible_cycle_info(tpl, cycle_num, num_cycles, cycle_length),
        intent=intent_normalized,
    ).to_dict()
    regimen_mentions = [regimen_mention]
    if regimen_name_prev in text:
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name_prev,
            regimen_normalized=regimen_name_prev,
            components_normalized=comp_prev,
        ).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C3_REGIMEN_ONCOLOGY",
        subcategory="C3.4_cycles_lines_intent",
        difficulty="Very Hard",
        drug_mentions=drug_mentions,
        regimen_mentions=regimen_mentions,
        num_drugs=len({mention["drug_normalized"] for mention in drug_mentions}),
        note_type=_note_type(rng, "C3.4_cycles_lines_intent"),
    )


# ── C4 generators ─────────────────────────────────────────────────────

def generate_c4_1(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C4.1 — Discontinued / on hold."""
    templates = TEMPLATES_BY_SUBCATEGORY["C4.1_discontinued_hold"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()

    d1 = sampler.random_dose(drug1)
    reasons = [
        "neutropenia", "thrombocytopenia", "nausea/vomiting", "peripheral neuropathy",
        "hepatotoxicity", "nephrotoxicity", "mucositis", "infection",
        "patient intolerance", "disease progression", "elevated LFTs",
        "grade 3 diarrhea", "pancytopenia", "cardiac toxicity",
    ]
    regimen_name = rng.choice(["FOLFOX", "R-CHOP", "AC-T", "ABVD", "FOLFIRI"])

    tpl = _pick_template(templates, rng)

    d2_info = sampler.random_dose(drug2)
    text = tpl.format(
        drug1=drug1, drug2=drug2,
        dose1_low=d1["dose"], dose2=d2_info["dose"],
        route2=d2_info["route"],
        reason=rng.choice(reasons),
        stop_date=f"0{rng.randint(1,9)}/{rng.randint(10,28)}/2024",
        cycle_num=rng.randint(1, 6),
        regimen_name=regimen_name,
    )

    # Derive status from template semantics instead of random assignment
    tpl_lower = tpl.lower()
    hold_keywords = ["hold", "held", "holding", "withheld", "temporarily"]
    if "re-initiated" in tpl_lower:
        status = DrugStatus.CURRENT.value
    elif any(kw in tpl_lower for kw in hold_keywords):
        status = DrugStatus.HOLD.value
    else:
        status = DrugStatus.DISCONTINUED.value
    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, status=status)
    mentions = [dm1.to_dict()]
    if drug2 in text:
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C4_CONTEXT_SAFETY",
        subcategory="C4.1_discontinued_hold",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C4.1_discontinued_hold"),
    )


def generate_c4_2(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C4.2 — Allergy / adverse drug reaction."""
    templates = TEMPLATES_BY_SUBCATEGORY["C4.2_allergy_adr"]
    drug1 = sampler.random_adr_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()

    if drug1 in ADVERSE_REACTIONS:
        reaction = rng.choice(ADVERSE_REACTIONS[drug1])
    else:
        reaction = rng.choice(["rash", "anaphylaxis", "hives", "nausea/vomiting",
                                "angioedema", "bronchospasm"])

    reaction2 = rng.choice(["rash", "nausea", "hives", "itching"])
    severity = rng.choice(["mild", "moderate", "severe"])
    grade = rng.choice(["1", "2", "3", "4"])
    drug_related = "similar agents"

    tpl = _pick_template(templates, rng)
    text = tpl.format(
        drug1=drug1, drug2=drug2,
        reaction=reaction, reaction2=reaction2,
        severity=severity, grade=grade,
        cycle_num=rng.randint(1, 6),
        drug_related=drug_related,
    )

    # Separate explicit allergy language from broader adverse-event language.
    drug2_is_allergy = "{reaction2}" in tpl
    allergy_cues = [
        "allergy", "allergic", "hypersensitivity", "anaphylactic", "nkda"
    ]
    drug1_is_allergy = any(cue in tpl.casefold() for cue in allergy_cues)
    discontinued_cues = ["discontinued", "avoid", "contraindicated", "switched"]
    drug1_status = (
        DrugStatus.DISCONTINUED.value
        if any(cue in text.casefold() for cue in discontinued_cues)
        else DrugStatus.UNKNOWN.value
    )

    if "{reaction}" in tpl:
        adverse_event = reaction
    elif "anaphylactic reaction" in tpl.casefold():
        adverse_event = "anaphylactic reaction"
    elif "hypersensitivity" in tpl.casefold():
        adverse_event = "hypersensitivity"
    else:
        adverse_event = None

    dm1 = DrugMention(
        drug_surface=drug1,
        drug_normalized=drug1,
        allergy=drug1_is_allergy,
        adverse_event=adverse_event,
        status=drug1_status,
    )
    mentions = [dm1.to_dict()]
    if drug2 in text and drug2 != drug1:
        if drug2_is_allergy:
            dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2,
                              allergy=True, adverse_event=reaction2,
                              status=DrugStatus.UNKNOWN.value)
        else:
            dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C4_CONTEXT_SAFETY",
        subcategory="C4.2_allergy_adr",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C4.2_allergy_adr"),
    )


def generate_c4_3(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C4.3 — Negated drug mentions."""
    templates = TEMPLATES_BY_SUBCATEGORY["C4.3_negated"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()

    reasons = [
        "renal insufficiency", "cardiac history", "prior hypersensitivity",
        "poor performance status", "patient preference", "drug interaction",
        "age > 80", "comorbidities", "insurance denial",
    ]

    tpl = _pick_template(templates, rng)
    text = tpl.format(
        drug1=drug1, drug2=drug2,
        reason=rng.choice(reasons),
    )

    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, negated=True,
                       status=DrugStatus.UNKNOWN.value)
    mentions = [dm1.to_dict()]
    if drug2 in text:
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2, negated=False)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C4_CONTEXT_SAFETY",
        subcategory="C4.3_negated",
        difficulty="Hard",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C4.3_negated"),
    )


def generate_c4_4(sampler: DrugSampler, reg_sampler: RegimenSampler,
                   conditions: list[str], rng: random.Random, idx: int) -> BenchmarkSample:
    """C4.4 — Medication history / conflicts."""
    templates = TEMPLATES_BY_SUBCATEGORY["C4.4_med_history_conflict"]
    drug1 = sampler.random_dosed_drug()
    drug2 = sampler.random_dosed_drug()
    drug3 = sampler.random_dosed_drug()
    while drug2 == drug1:
        drug2 = sampler.random_dosed_drug()
    while drug3 in (drug1, drug2):
        drug3 = sampler.random_dosed_drug()

    regimen_name, reg_components = reg_sampler.random_regimen(
        min_drugs=2, require_condition=True
    )
    regimen_name_prev, reg_prev_components = reg_sampler.random_regimen(
        min_drugs=2, require_condition=True
    )
    condition = reg_sampler.condition_for(regimen_name)
    condition_prev = reg_sampler.condition_for(regimen_name_prev)

    reasons = ["disease progression", "toxicity", "incomplete response", "relapse"]
    interaction_effects = ["QT prolongation", "increased myelosuppression",
                          "hepatotoxicity", "renal toxicity",
                          "increased risk of bleeding", "enhanced cytotoxicity"]

    tpl = _pick_template(templates, rng)
    tpl_lower = tpl.lower()

    # For cumulative-dose templates, restrict drug1 to drugs with known limits
    if "cumulative" in tpl_lower or "lifetime" in tpl_lower:
        cum_drugs = [d for d in CUMULATIVE_DOSE_DRUGS if d in sampler.dosed_drugs]
        if cum_drugs:
            drug1 = rng.choice(cum_drugs)

    max_dose = CUMULATIVE_DOSE_LIMITS.get(drug1, "450 mg/m2")
    max_value = int(max_dose.split()[0])
    cumulative_value = rng.randint(max(1, max_value // 2), max(2, (max_value * 9) // 10))

    text = tpl.format(
        drug1=drug1, drug2=drug2, drug3=drug3,
        regimen_name=regimen_name, regimen_name_prev=regimen_name_prev,
        condition=condition, condition_prev=condition_prev,
        reason=rng.choice(reasons), reason1=rng.choice(["cancer", "malignancy", "ongoing treatment"]),
        date_range_prev="2022-2023", date_range_curr="2024-present",
        cumulative_dose=f"{cumulative_value} mg/m2",
        max_dose=max_dose,
        num_cycles_prev=rng.randint(4, 6),
        interaction_effect=rng.choice(interaction_effects),
    )

    # Derive drug1 status from template
    historical_keywords = [
        "past treatment", "history of", "previously", "prior ",
        "2022-2023", "cumulative", "lifetime",
    ]
    if any(kw in tpl_lower for kw in historical_keywords):
        drug1_status = DrugStatus.HISTORICAL.value
    else:
        drug1_status = DrugStatus.CURRENT.value

    # For line-of-therapy templates, only the latest line is current
    line_therapy_tpl = "prior line" in tpl_lower and ("second line" in tpl_lower or "third line" in tpl_lower)

    dm1 = DrugMention(drug_surface=drug1, drug_normalized=drug1, status=drug1_status)
    mentions = []
    if drug1 in text:
        mentions.append(dm1.to_dict())
    if drug2 in text:
        dm2_status = DrugStatus.HISTORICAL.value if line_therapy_tpl else DrugStatus.CURRENT.value
        dm2 = DrugMention(drug_surface=drug2, drug_normalized=drug2, status=dm2_status)
        mentions.append(dm2.to_dict())
    if drug3 in text:
        dm3_status = DrugStatus.CURRENT.value
        dm3 = DrugMention(drug_surface=drug3, drug_normalized=drug3, status=dm3_status)
        mentions.append(dm3.to_dict())

    # For regimen-only templates, derive drug mentions from regimen components
    if not mentions:
        if regimen_name in text:
            for c in reg_components:
                mentions.append(DrugMention(
                    drug_surface=regimen_name, drug_normalized=c,
                    status=DrugStatus.CURRENT.value
                ).to_dict())
        if regimen_name_prev in text:
            for c in reg_prev_components:
                mentions.append(DrugMention(
                    drug_surface=regimen_name_prev, drug_normalized=c,
                    status=DrugStatus.HISTORICAL.value
                ).to_dict())

    regimen_mentions = []
    if regimen_name in text:
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name,
            regimen_normalized=regimen_name,
            components_normalized=reg_components,
        ).to_dict())
    if regimen_name_prev in text:
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name_prev,
            regimen_normalized=regimen_name_prev,
            components_normalized=reg_prev_components,
        ).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C4_CONTEXT_SAFETY",
        subcategory="C4.4_med_history_conflict",
        difficulty="Hard",
        drug_mentions=mentions,
        regimen_mentions=regimen_mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C4.4_med_history_conflict"),
    )


# ── C5 generators ─────────────────────────────────────────────────────

def generate_c5_1(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C5.1 — Abbreviations / shortened forms."""
    templates = TEMPLATES_BY_SUBCATEGORY["C5.1_abbreviations"]
    tpl = _pick_template(templates, rng)
    force_iv = " IV" in tpl or "infus" in tpl.casefold()
    abbrevs = [
        (abbreviation, sampler.by_casefold[generic.casefold()])
        for abbreviation, generic in DRUG_ABBREVIATIONS.items()
        if generic.casefold() in sampler.by_casefold
        and sampler.by_casefold[generic.casefold()] in sampler.dose_profiles
        and (
            not force_iv
            or "IV" in sampler.dose_profiles[
                sampler.by_casefold[generic.casefold()]
            ]["routes"]
        )
    ]
    rng.shuffle(abbrevs)

    abbrev1, generic1 = abbrevs[0]
    abbrev2, generic2 = abbrevs[1] if len(abbrevs) > 1 else abbrevs[0]

    d1 = sampler.random_dose(generic1, required_route="IV" if force_iv else None)
    d2 = sampler.random_dose(generic2, required_route="IV" if force_iv else None)
    text = tpl.format(
        drug_abbrev=abbrev1, drug_abbrev2=abbrev2,
        dose1=d1["dose"], route1=d1["route"], freq1=d1["freq"],
        dose2=d2["dose"], route2=d2["route"],
    )

    # Determine status based on template context
    dm1_status = DrugStatus.CURRENT.value
    dm2_status = DrugStatus.CURRENT.value
    if "D/C {drug_abbrev}" in tpl:
        dm1_status = DrugStatus.DISCONTINUED.value
    if "held" in tpl.lower():
        dm2_status = DrugStatus.HOLD.value

    dm1 = DrugMention(drug_surface=abbrev1, drug_normalized=generic1, status=dm1_status)
    mentions = [dm1.to_dict()]
    if abbrev2 in text and abbrev2 != abbrev1:
        dm2 = DrugMention(drug_surface=abbrev2, drug_normalized=generic2, status=dm2_status)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C5_NOISE_AMBIGUITY",
        subcategory="C5.1_abbreviations",
        difficulty="Hard",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C5.1_abbreviations"),
    )


def generate_c5_2(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C5.2 — Brand name usage."""
    templates = TEMPLATES_BY_SUBCATEGORY["C5.2_brand_names"]

    # Use explicit BRAND_NAME_MAP for reliable brand→generic pairing
    brand_pairs = [
        (brand, sampler.by_casefold[generic.casefold()])
        for brand, generic in BRAND_NAME_MAP.items()
        if generic.casefold() in sampler.by_casefold
        and sampler.by_casefold[generic.casefold()] in sampler.dose_profiles
    ]
    rng.shuffle(brand_pairs)

    brand1, drug1 = brand_pairs[0]
    brand2, drug2 = brand_pairs[1] if len(brand_pairs) > 1 else brand_pairs[0]
    while drug2 == drug1 and len(brand_pairs) > 1:
        brand2, drug2 = rng.choice(brand_pairs)

    d1 = sampler.random_dose(drug1)
    d2 = sampler.random_dose(drug2)
    condition = rng.choice(["cancer", "lymphoma", "myeloma", "leukemia", "breast cancer"])

    tpl = _pick_template(templates, rng)

    # Avoid infusion templates for non-IV drugs
    if _has_infusion_language(tpl) and d1["route"] != "IV":
        non_infusion = [t for t in templates if not _has_infusion_language(t)]
        tpl = _pick_template(non_infusion, rng)

    text = tpl.format(
        brand_name=brand1, brand_name2=brand2,
        drug1_generic=drug1, drug2_generic=drug2,
        dose1=d1["dose"], route1=d1["route"], freq1=d1["freq"],
        dose2=d2["dose"], route2=d2["route"],
        condition=condition,
        infusion_time=rng.choice(["30 minutes", "1 hour", "90 minutes"]),
    )

    switch_template = "Switch from {brand_name} to {brand_name2}" in tpl
    dm1 = DrugMention(
        drug_surface=brand1,
        drug_normalized=drug1,
        status=(
            DrugStatus.DISCONTINUED.value
            if switch_template else DrugStatus.CURRENT.value
        ),
    )
    mentions = [dm1.to_dict()]
    if brand2 in text and brand2 != brand1:
        dm2 = DrugMention(
            drug_surface=brand2,
            drug_normalized=drug2,
            status=DrugStatus.CURRENT.value,
        )
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C5_NOISE_AMBIGUITY",
        subcategory="C5.2_brand_names",
        difficulty="Medium",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C5.2_brand_names"),
    )


def generate_c5_3(sampler: DrugSampler, rng: random.Random, idx: int) -> BenchmarkSample:
    """C5.3 — Misspellings / typos."""
    templates = TEMPLATES_BY_SUBCATEGORY["C5.3_misspellings"]
    tpl = _pick_template(templates, rng)
    force_iv = " IV" in tpl or "infus" in tpl.casefold()
    misspell_drugs = [
        name for name in MISSPELLING_PATTERNS
        if name.casefold() in sampler.by_casefold
        and sampler.by_casefold[name.casefold()] in sampler.dose_profiles
        and (
            not force_iv
            or "IV" in sampler.dose_profiles[
                sampler.by_casefold[name.casefold()]
            ]["routes"]
        )
    ]

    drug1_correct = rng.choice(misspell_drugs)
    drug1_misspelled = rng.choice(MISSPELLING_PATTERNS[drug1_correct])

    drug2_correct = rng.choice(misspell_drugs)
    while drug2_correct == drug1_correct:
        drug2_correct = rng.choice(misspell_drugs)
    drug2_misspelled = rng.choice(MISSPELLING_PATTERNS[drug2_correct])

    drug2_clean = sampler.random_dosed_drug()  # a correctly-spelled second drug

    d1 = sampler.random_dose(
        sampler.by_casefold[drug1_correct.casefold()],
        required_route="IV" if force_iv else None,
    )
    text = tpl.format(
        drug_misspelled=drug1_misspelled,
        drug_misspelled2=drug2_misspelled,
        drug2=drug2_clean,
        dose1=d1["dose"], route1=d1["route"], freq1=d1["freq"],
        duration=rng.choice(["7 days", "14 days", "21 days"]),
    )

    dm1 = DrugMention(drug_surface=drug1_misspelled, drug_normalized=drug1_correct)
    mentions = [dm1.to_dict()]
    if drug2_misspelled in text:
        dm2 = DrugMention(drug_surface=drug2_misspelled, drug_normalized=drug2_correct)
        mentions.append(dm2.to_dict())
    elif drug2_clean in text:
        dm2 = DrugMention(drug_surface=drug2_clean, drug_normalized=drug2_clean)
        mentions.append(dm2.to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C5_NOISE_AMBIGUITY",
        subcategory="C5.3_misspellings",
        difficulty="Very Hard",
        drug_mentions=mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C5.3_misspellings"),
    )


def generate_c5_4(sampler: DrugSampler, reg_sampler: RegimenSampler,
                   conditions: list[str], rng: random.Random, idx: int) -> BenchmarkSample:
    """C5.4 — High-noise clinical text."""
    templates = TEMPLATES_BY_SUBCATEGORY["C5.4_high_noise"]
    tpl = _pick_template(templates, rng)
    required_slots = max(
        [int(value) for value in re.findall(r"\{drug([1-3])\}", tpl)] or [2]
    )
    regimen_name, components = reg_sampler.random_regimen(
        min_drugs=required_slots,
        require_dose_profiles=True,
        require_iv=_has_infusion_language(tpl) or " IV" in tpl,
        require_condition=True,
    )

    drugs = components[:max(3, required_slots)]

    force_iv = _has_infusion_language(tpl) or " IV" in tpl
    dose_infos = [
        sampler.random_dose(d, required_route="IV" if force_iv else None)
        for d in drugs
    ]
    condition = reg_sampler.condition_for(regimen_name)
    subtypes = ["adenocarcinoma", "squamous cell", "poorly differentiated",
                "high-grade", "triple-negative", "HER2-positive"]
    stages = ["IIA", "IIB", "IIIA", "IIIB", "IV"]

    drug_allergy = sampler.random_dosed_drug()
    while drug_allergy in drugs:
        drug_allergy = sampler.random_dosed_drug()

    antiemetics = [
        sampler.by_casefold[d.casefold()]
        for d in SUPPORTIVE_CARE_DRUGS[:8]
        if d.casefold() in sampler.by_casefold
        and sampler.by_casefold[d.casefold()] in sampler.dose_profiles
        and sampler.by_casefold[d.casefold()] != drug_allergy
    ]
    if "{drug_premed1}" in tpl or "{drug_premed2}" in tpl:
        antiemetics = [
            drug for drug in antiemetics
            if "IV" in sampler.dose_profiles[drug]["routes"]
        ]
    if not antiemetics:
        raise ValueError("No eligible antiemetic for selected high-noise template")
    ae1 = rng.choice(antiemetics) if antiemetics else "Ondansetron"
    ae2_candidates = [drug for drug in antiemetics if drug != ae1]
    ae2 = rng.choice(ae2_candidates or antiemetics)

    intent_surface, intent_normalized = _sample_intent(tpl, rng)
    cycle_num = rng.randint(1, 6)
    num_cycles = rng.randint(4, 8)
    text = tpl.format(
        age=rng.randint(35, 80),
        sex=rng.choice(["M", "F"]),
        condition=condition,
        subtype=rng.choice(subtypes),
        stage=rng.choice(stages),
        ecog=rng.choice(["0", "1", "2"]),
        regimen_name=regimen_name,
        cycle_num=cycle_num,
        num_cycles=num_cycles,
        intent=intent_surface,
        drug1=drugs[0], dose1=dose_infos[0]["dose"], route1=dose_infos[0]["route"],
        freq1=dose_infos[0].get("freq", ""),
        drug2=drugs[1] if len(drugs) > 1 else drugs[0],
        dose2=dose_infos[1]["dose"] if len(dose_infos) > 1 else dose_infos[0]["dose"],
        route2=dose_infos[1]["route"] if len(dose_infos) > 1 else dose_infos[0]["route"],
        freq2=dose_infos[1].get("freq", "") if len(dose_infos) > 1 else "",
        drug3=drugs[2] if len(drugs) > 2 else drugs[0],
        dose3=dose_infos[2]["dose"] if len(dose_infos) > 2 else dose_infos[0]["dose"],
        route3=dose_infos[2]["route"] if len(dose_infos) > 2 else dose_infos[0]["route"],
        drug_allergy=drug_allergy,
        drug_premedx=ae1,
        drug_antiemetic=ae1,
        drug_antiemetic2=ae2,
        drug_premed1=ae1,
        dose_pm1=sampler.random_dose(
            ae1,
            required_route="IV" if "{drug_premed1}" in tpl else None,
        )["dose"],
        drug_premed2=ae2,
        dose_pm2=sampler.random_dose(
            ae2,
            required_route="IV" if "{drug_premed2}" in tpl else None,
        )["dose"],
        drug_abx1=rng.choice(["Cefepime", "Meropenem"]),
        drug_abx2=rng.choice(["Vancomycin", "Gentamicin"]),
        drug_abx_oral=rng.choice(["Levofloxacin 500 mg PO daily",
                                   "Ciprofloxacin 500 mg PO BID"]),
        mrn=rng.randint(100000, 999999),
        infusion_time1=rng.choice(["30 min", "1 hr", "90 min"]),
        infusion_time2=rng.choice(["2 hrs", "3 hrs", "46 hrs CI"]),
    )

    # Collect all drug mentions that appear in text
    mentions = []
    for d in drugs:
        if d in text:
            drug_status = DrugStatus.HOLD.value if f"Held {d}" in text else DrugStatus.CURRENT.value
            mentions.append(DrugMention(drug_surface=d, drug_normalized=d,
                                        status=drug_status).to_dict())

    # Check for supportive meds in text
    for sc in [ae1, ae2]:
        if sc in text and not any(m["drug_normalized"] == sc for m in mentions):
            mentions.append(DrugMention(drug_surface=sc, drug_normalized=sc).to_dict())

    if "{drug_allergy}" in tpl:
        mentions.append(DrugMention(
            drug_surface=drug_allergy,
            drug_normalized=drug_allergy,
            status=DrugStatus.UNKNOWN.value,
            allergy=True,
            adverse_event="rash",
        ).to_dict())

    regimen_mentions = []
    if regimen_name in text:
        regimen_mentions.append(RegimenMention(
            regimen_surface=regimen_name,
            regimen_normalized=regimen_name,
            components_normalized=components,
            cycle_info=_visible_cycle_info(tpl, cycle_num, num_cycles, ""),
            intent=intent_normalized,
        ).to_dict())

    return BenchmarkSample(
        sample_id=f"ONCORX-{idx:04d}",
        clinical_text=text,
        category="C5_NOISE_AMBIGUITY",
        subcategory="C5.4_high_noise",
        difficulty="Very Hard",
        drug_mentions=mentions,
        regimen_mentions=regimen_mentions,
        num_drugs=len(mentions),
        note_type=_note_type(rng, "C5.4_high_noise", text),
    )


# ══════════════════════════════════════════════════════════════════════
# Main orchestrator
# ══════════════════════════════════════════════════════════════════════

GENERATOR_MAP = {
    "C1.1_single_drug_simple":  "c1_1",
    "C1.2_single_drug_dose":    "c1_2",
    "C1.3_two_drugs":           "c1_3",
    "C1.4_supportive_care":     "c1_4",
    "C2.1_dose_route_freq":     "c2_1",
    "C2.2_titration_taper":     "c2_2",
    "C2.3_prn_conditional":     "c2_3",
    "C2.4_duration_stop":       "c2_4",
    "C3.1_multi_drug_explicit": "c3_1",
    "C3.2_regimen_acronym_only":"c3_2",
    "C3.3_regimen_partial":     "c3_3",
    "C3.4_cycles_lines_intent": "c3_4",
    "C4.1_discontinued_hold":   "c4_1",
    "C4.2_allergy_adr":         "c4_2",
    "C4.3_negated":             "c4_3",
    "C4.4_med_history_conflict":"c4_4",
    "C5.1_abbreviations":       "c5_1",
    "C5.2_brand_names":         "c5_2",
    "C5.3_misspellings":        "c5_3",
    "C5.4_high_noise":          "c5_4",
}


def generate_dataset(
    dry_run: bool = False, output_dir: Path = OUTPUT_DIR
) -> list[dict]:
    """Generate the full benchmark dataset."""
    rng = random.Random(RANDOM_SEED)

    # Load knowledge bases
    print("Loading knowledge bases...")
    drug_table = load_drug_table(DRUG_TABLE_PATH)
    regimen_table = load_regimen_table(REGIMEN_TABLE_PATH)
    conditions = load_conditions(CONDITIONS_PATH)
    conditions_by_regimen = load_conditions_by_regimen(
        CONDITIONS_PATH, REGIMEN_TABLE_PATH
    )

    print(f"  Drugs:     {len(drug_table):,}")
    print(f"  Regimens:  {len(regimen_table):,}")
    print(f"  Conditions: {len(conditions):,}")

    sampler = DrugSampler(drug_table, rng)
    drug_names_set = {d.lower() for d in drug_table.keys()} | {d.lower() for d in ONCOLOGY_DRUGS}
    reg_sampler = RegimenSampler(
        regimen_table,
        rng,
        drug_names_set,
        dose_profiles=sampler.dose_profiles,
        conditions_by_regimen=conditions_by_regimen,
    )

    samples: list[dict] = []
    template_assignments: list[dict] = []
    seen_texts: set[str] = set()
    sample_idx = 1
    MAX_RETRIES = 100  # retries to avoid duplicates

    def _call_generator(gen_key, idx):
        if gen_key == "c1_1":
            return generate_c1_1(sampler, rng, idx)
        elif gen_key == "c1_2":
            return generate_c1_2(sampler, rng, idx)
        elif gen_key == "c1_3":
            return generate_c1_3(sampler, rng, idx)
        elif gen_key == "c1_4":
            return generate_c1_4(sampler, rng, idx)
        elif gen_key == "c2_1":
            return generate_c2_1(sampler, rng, idx)
        elif gen_key == "c2_2":
            return generate_c2_2(sampler, rng, idx)
        elif gen_key == "c2_3":
            return generate_c2_3(sampler, rng, idx)
        elif gen_key == "c2_4":
            return generate_c2_4(sampler, rng, idx)
        elif gen_key == "c3_1":
            return generate_c3_1(sampler, reg_sampler, conditions, rng, idx)
        elif gen_key == "c3_2":
            return generate_c3_2(reg_sampler, conditions, rng, idx)
        elif gen_key == "c3_3":
            return generate_c3_3(sampler, reg_sampler, rng, idx)
        elif gen_key == "c3_4":
            return generate_c3_4(reg_sampler, conditions, rng, idx)
        elif gen_key == "c4_1":
            return generate_c4_1(sampler, rng, idx)
        elif gen_key == "c4_2":
            return generate_c4_2(sampler, rng, idx)
        elif gen_key == "c4_3":
            return generate_c4_3(sampler, rng, idx)
        elif gen_key == "c4_4":
            return generate_c4_4(sampler, reg_sampler, conditions, rng, idx)
        elif gen_key == "c5_1":
            return generate_c5_1(sampler, rng, idx)
        elif gen_key == "c5_2":
            return generate_c5_2(sampler, rng, idx)
        elif gen_key == "c5_3":
            return generate_c5_3(sampler, rng, idx)
        elif gen_key == "c5_4":
            return generate_c5_4(sampler, reg_sampler, conditions, rng, idx)
        return None

    for cat_code, cat_info in CATEGORY_DISTRIBUTION.items():
        for subcat_code, subcat_info in cat_info["subcategories"].items():
            target_count = subcat_info["count"]
            gen_key = GENERATOR_MAP[subcat_code]
            generated = 0

            print(f"  Generating {subcat_code} ({target_count} samples)...", end=" ", flush=True)

            for _ in range(target_count):
                sample = None
                for _attempt in range(MAX_RETRIES):
                    candidate = _call_generator(gen_key, sample_idx)
                    if candidate is None:
                        raise RuntimeError(f"No generator registered for {subcat_code}")
                    while "  " in candidate.clinical_text:
                        candidate.clinical_text = candidate.clinical_text.replace("  ", " ")
                    candidate = _finalize_sample(candidate)
                    text_key = candidate.clinical_text.strip().casefold()
                    if text_key not in seen_texts:
                        sample = candidate
                        seen_texts.add(text_key)
                        break
                if sample is None:
                    raise RuntimeError(
                        f"Could not produce a unique sample for {subcat_code} "
                        f"after {MAX_RETRIES} attempts"
                    )

                if _LAST_TEMPLATE_TEXT is None:
                    raise RuntimeError(
                        f"Generator for {subcat_code} did not record a template"
                    )
                try:
                    template_index = TEMPLATES_BY_SUBCATEGORY[subcat_code].index(
                        _LAST_TEMPLATE_TEXT
                    )
                except ValueError as exc:
                    raise RuntimeError(
                        f"Selected template is not registered for {subcat_code}"
                    ) from exc

                template_assignments.append({
                    "sample_id": sample.sample_id,
                    "subcategory": subcat_code,
                    "template_id": f"{subcat_code}:{template_index:03d}",
                    "template_sha256": hashlib.sha256(
                        _LAST_TEMPLATE_TEXT.encode("utf-8")
                    ).hexdigest(),
                })

                samples.append(sample.to_dict())
                sample_idx += 1
                generated += 1

            print(f"done ({generated}/{target_count})")

    print(f"\nTotal samples generated: {len(samples)}")
    expected_total = sum(
        category["total"] for category in CATEGORY_DISTRIBUTION.values()
    )
    if len(samples) != expected_total:
        raise RuntimeError(
            f"Generated {len(samples)} samples; expected {expected_total}"
        )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_jsonl = output_dir / "oncorx_bench.jsonl"
        with open(out_jsonl, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"Written to: {out_jsonl}")

        # Also write category stats
        stats = {}
        for s in samples:
            cat = s["category"]
            subcat = s["subcategory"]
            stats.setdefault(cat, {})
            stats[cat].setdefault(subcat, 0)
            stats[cat][subcat] += 1

        stats_path = output_dir / "generation_stats.json"
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"Stats written to: {stats_path}")

        template_catalog_bytes = json.dumps(
            TEMPLATES_BY_SUBCATEGORY,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assignment_manifest = {
            "schema_version": 1,
            "random_seed": RANDOM_SEED,
            "template_catalog_sha256": hashlib.sha256(
                template_catalog_bytes
            ).hexdigest(),
            "num_templates": sum(
                len(items) for items in TEMPLATES_BY_SUBCATEGORY.values()
            ),
            "num_assignments": len(template_assignments),
            "assignments": template_assignments,
        }
        assignment_path = output_dir / "template_assignments.json"
        with open(assignment_path, "w", encoding="utf-8") as f:
            json.dump(assignment_manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Template assignments written to: {assignment_path}")

    return samples


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate OncoRx-Bench dataset")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    generate_dataset(dry_run=args.dry_run, output_dir=args.output_dir)

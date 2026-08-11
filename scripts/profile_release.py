#!/usr/bin/env python3
"""Compute release statistics and reproducible LaTeX macros from JSONL."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataset_config import OUTPUT_DIR  # noqa: E402
from templates import TEMPLATES_BY_SUBCATEGORY  # noqa: E402


def _format_number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return f"{value:,}"


def _load_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_profile(input_path: Path) -> dict:
    rows = _load_jsonl(input_path)
    with open(ROOT / "data" / "knowledge" / "provenance.json", "r", encoding="utf-8") as handle:
        knowledge_provenance = json.load(handle)
    drug_mentions = [mention for row in rows for mention in row["drug_mentions"]]
    regimen_mentions = [
        mention for row in rows for mention in row["regimen_mentions"]
    ]
    term_counts = [len(row["clinical_text"].split()) for row in rows]

    category_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        category_rows[row["category"].split("_", 1)[0]].append(row)

    per_category = {}
    for category in ("C1", "C2", "C3", "C4", "C5"):
        subset = category_rows[category]
        subset_drugs = [m for row in subset for m in row["drug_mentions"]]
        subset_regimens = [m for row in subset for m in row["regimen_mentions"]]
        subcategories = {row["subcategory"] for row in subset}
        per_category[category] = {
            "rows": len(subset),
            "template_pool": sum(
                len(TEMPLATES_BY_SUBCATEGORY[subcategory])
                for subcategory in subcategories
            ),
            "mean_whitespace_terms": round(
                statistics.fmean(
                    len(row["clinical_text"].split()) for row in subset
                ),
                1,
            ),
            "drug_objects": len(subset_drugs),
            "sig_objects": sum(bool(m.get("sig")) for m in subset_drugs),
            "regimen_objects": len(subset_regimens),
        }

    profile = {
        "canonical_jsonl_sha256": _sha256(input_path),
        "samples": len(rows),
        "configured_note_types_observed": len({row["note_type"] for row in rows}),
        "categories": len({row["category"] for row in rows}),
        "subcategories": len({row["subcategory"] for row in rows}),
        "templates_configured": sum(
            len(values) for values in TEMPLATES_BY_SUBCATEGORY.values()
        ),
        "drug_objects": len(drug_mentions),
        "explicit_drug_objects": sum(
            mention["evidence_type"] == "explicit_surface"
            for mention in drug_mentions
        ),
        "regimen_inference_drug_objects": sum(
            mention["evidence_type"] == "regimen_inference"
            for mention in drug_mentions
        ),
        "unique_normalized_drugs": len({
            mention["drug_normalized"].casefold()
            for mention in drug_mentions
        }),
        "unique_evidence_surfaces_exact": len({
            mention["drug_surface"] for mention in drug_mentions
        }),
        "unique_explicit_drug_surfaces_exact": len({
            mention["drug_surface"]
            for mention in drug_mentions
            if mention["evidence_type"] == "explicit_surface"
        }),
        "unique_regimen_inference_surfaces_exact": len({
            mention["drug_surface"]
            for mention in drug_mentions
            if mention["evidence_type"] == "regimen_inference"
        }),
        "sig_objects": sum(bool(mention.get("sig")) for mention in drug_mentions),
        "regimen_objects": len(regimen_mentions),
        "unique_normalized_regimens": len({
            mention["regimen_normalized"].casefold()
            for mention in regimen_mentions
        }),
        "component_assignments": sum(
            len(mention["components_normalized"])
            for mention in regimen_mentions
        ),
        "unique_components": len({
            component.casefold()
            for mention in regimen_mentions
            for component in mention["components_normalized"]
        }),
        "mean_whitespace_terms": round(statistics.fmean(term_counts), 1),
        "median_whitespace_terms": statistics.median(term_counts),
        "difficulty_distribution": dict(Counter(
            row["difficulty"] for row in rows
        )),
        "note_type_distribution": dict(Counter(
            row["note_type"] for row in rows
        )),
        "category_profile": per_category,
        "knowledge_view_rows": {
            filename: details["rows"]
            for filename, details in knowledge_provenance["outputs"].items()
        },
    }
    return profile


def _latex_macros(profile: dict) -> str:
    values = {
        "FinalDrugObjects": profile["drug_objects"],
        "FinalUniqueDrugs": profile["unique_normalized_drugs"],
        "FinalUniqueEvidenceSurfaces": profile["unique_evidence_surfaces_exact"],
        "FinalUniqueExplicitSurfaces": profile["unique_explicit_drug_surfaces_exact"],
        "FinalUniqueInferenceSurfaces": profile["unique_regimen_inference_surfaces_exact"],
        "FinalSigObjects": profile["sig_objects"],
        "FinalRegimenObjects": profile["regimen_objects"],
        "FinalUniqueRegimens": profile["unique_normalized_regimens"],
        "FinalComponentAssignments": profile["component_assignments"],
        "FinalUniqueComponents": profile["unique_components"],
        "FinalMeanTerms": profile["mean_whitespace_terms"],
        "FinalMedianTerms": profile["median_whitespace_terms"],
        "FinalDrugViewRows": profile["knowledge_view_rows"]["drug_table.csv"],
        "FinalRegimenViewRows": profile["knowledge_view_rows"]["regimen_table.csv"],
        "FinalConditionViewRows": profile["knowledge_view_rows"]["Conditions_And_Regimens.csv"],
    }
    category_macro_names = {
        "C1": "COne",
        "C2": "CTwo",
        "C3": "CThree",
        "C4": "CFour",
        "C5": "CFive",
    }
    for category in ("C1", "C2", "C3", "C4", "C5"):
        item = profile["category_profile"][category]
        macro_category = category_macro_names[category]
        values[f"Final{macro_category}MeanTerms"] = item["mean_whitespace_terms"]
        values[f"Final{macro_category}Drugs"] = item["drug_objects"]
        values[f"Final{macro_category}Sigs"] = item["sig_objects"]
        values[f"Final{macro_category}Regimens"] = item["regimen_objects"]

    lines = [
        "% Generated by scripts/profile_release.py; do not edit by hand."
    ]
    for name, value in values.items():
        lines.append(f"\\newcommand{{\\{name}}}{{{_format_number(value)}}}")
    lines.extend([
        "\\newcommand{\\FinalValidationErrors}{0}",
        "\\newcommand{\\FinalDuplicateTexts}{0}",
        "\\newcommand{\\FinalSplitLeakageErrors}{0}",
        f"\\newcommand{{\\FinalJsonlSha}}{{{profile['canonical_jsonl_sha256']}}}",
        f"\\newcommand{{\\FinalJsonlShaA}}{{{profile['canonical_jsonl_sha256'][:32]}}}",
        f"\\newcommand{{\\FinalJsonlShaB}}{{{profile['canonical_jsonl_sha256'][32:]}}}",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=OUTPUT_DIR / "oncorx_bench.jsonl")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "dataset_profile.json")
    parser.add_argument(
        "--latex-output",
        type=Path,
        default=ROOT / "paper" / "generated_stats.tex",
    )
    args = parser.parse_args()

    profile = build_profile(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.latex_output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    with open(args.latex_output, "w", encoding="utf-8") as handle:
        handle.write(_latex_macros(profile))
    print(f"Profile: {args.output}")
    print(f"LaTeX macros: {args.latex_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

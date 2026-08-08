#!/usr/bin/env python3
"""
OncoRx-Bench: Dataset validation.

Checks generated samples for:
  1. Schema completeness (required fields, correct types)
  2. Drug grounding (drug_normalized exists in drug_table.csv)
  3. Regimen grounding (components exist in regimen_table.csv)
  4. Text integrity (no unfilled template placeholders)
  5. Distribution correctness (category counts match targets)
  6. Duplicate detection

Usage:
    python validate_dataset.py                         # validate output/oncorx_bench.jsonl
    python validate_dataset.py --input path/to/file.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from dataset_config import (
    CATEGORY_DISTRIBUTION,
    DRUG_TABLE_PATH,
    REGIMEN_TABLE_PATH,
    OUTPUT_DIR,
    DRUG_ABBREVIATIONS,
    MISSPELLING_PATTERNS,
)


def load_drug_names(path: Path) -> set[str]:
    """Load all known drug names (generic + synonyms) as a lookup set."""
    import csv
    names = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if row:
                names.add(row[0].strip().lower())
                if len(row) > 1:
                    for syn in row[1].split(","):
                        syn = syn.strip().lower()
                        if syn:
                            names.add(syn)
    return names


def load_regimen_names(path: Path) -> set[str]:
    """Load all known regimen names."""
    import csv
    names = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if row:
                names.add(row[0].strip().lower())
    return names


def validate_dataset(input_path: Path) -> dict:
    """Run all validation checks and return a report dict."""
    print(f"Validating: {input_path}")

    # Load samples
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                samples.append((line_num, json.loads(line)))
    print(f"  Loaded {len(samples)} samples")

    # Load knowledge bases
    drug_names = load_drug_names(DRUG_TABLE_PATH)
    regimen_names = load_regimen_names(REGIMEN_TABLE_PATH)

    # Also add abbreviations and misspelling targets as known
    known_abbrevs = {v.lower() for v in DRUG_ABBREVIATIONS.values()}
    known_misspell_targets = {k.lower() for k in MISSPELLING_PATTERNS.keys()}
    drug_names |= known_abbrevs | known_misspell_targets

    report = {
        "total_samples": len(samples),
        "schema_errors": [],
        "drug_grounding_errors": [],
        "regimen_grounding_errors": [],
        "template_placeholder_errors": [],
        "duplicate_texts": [],
        "category_distribution": {},
        "difficulty_distribution": Counter(),
    }

    required_fields = ["sample_id", "clinical_text", "category", "subcategory",
                       "difficulty", "drug_mentions", "num_drugs"]

    seen_ids = set()
    seen_texts = {}
    unfilled_pattern = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")

    for line_num, sample in samples:
        sid = sample.get("sample_id", f"line:{line_num}")

        # 1. Schema completeness
        for field in required_fields:
            if field not in sample:
                report["schema_errors"].append(f"{sid}: missing field '{field}'")

        if sid in seen_ids:
            report["schema_errors"].append(f"{sid}: duplicate sample_id")
        seen_ids.add(sid)

        # 2. Drug grounding
        for dm in sample.get("drug_mentions", []):
            normalized = dm.get("drug_normalized", "").lower()
            if normalized and normalized not in drug_names:
                report["drug_grounding_errors"].append(
                    f"{sid}: ungrounded drug '{dm.get('drug_normalized')}'"
                )

        # 3. Regimen grounding
        for rm in sample.get("regimen_mentions", []):
            rname = rm.get("regimen_normalized", "").lower()
            if rname and rname not in regimen_names:
                report["regimen_grounding_errors"].append(
                    f"{sid}: ungrounded regimen '{rm.get('regimen_normalized')}'"
                )

        # 4. Unfilled template placeholders
        text = sample.get("clinical_text", "")
        placeholders = unfilled_pattern.findall(text)
        if placeholders:
            report["template_placeholder_errors"].append(
                f"{sid}: unfilled placeholders {placeholders}"
            )

        # 5. Duplicates
        text_normalized = text.strip().lower()
        if text_normalized in seen_texts:
            report["duplicate_texts"].append(
                f"{sid} is duplicate of {seen_texts[text_normalized]}"
            )
        else:
            seen_texts[text_normalized] = sid

        # 6. Distribution tracking
        cat = sample.get("category", "UNKNOWN")
        subcat = sample.get("subcategory", "UNKNOWN")
        report["category_distribution"].setdefault(cat, Counter())
        report["category_distribution"][cat][subcat] += 1
        report["difficulty_distribution"][sample.get("difficulty", "UNKNOWN")] += 1

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)

    # Category distribution vs targets
    print("\nCategory Distribution:")
    total_generated = 0
    total_target = 0
    for cat_code, cat_info in CATEGORY_DISTRIBUTION.items():
        cat_total = sum(report["category_distribution"].get(cat_code, Counter()).values())
        cat_target = cat_info["total"]
        total_generated += cat_total
        total_target += cat_target
        print(f"  {cat_code}: {cat_total}/{cat_target}")
        for subcat_code, subcat_info in cat_info["subcategories"].items():
            actual = report["category_distribution"].get(cat_code, Counter()).get(subcat_code, 0)
            target = subcat_info["count"]
            status = "✓" if actual == target else f"✗ ({'+' if actual > target else ''}{actual - target})"
            print(f"    {subcat_code}: {actual}/{target} {status}")

    print(f"\n  Total: {total_generated}/{total_target}")

    # Difficulty distribution
    print(f"\nDifficulty Distribution:")
    for diff, count in sorted(report["difficulty_distribution"].items()):
        print(f"  {diff}: {count}")

    # Error summaries
    error_types = [
        ("Schema errors", report["schema_errors"]),
        ("Drug grounding errors", report["drug_grounding_errors"]),
        ("Regimen grounding errors", report["regimen_grounding_errors"]),
        ("Template placeholder errors", report["template_placeholder_errors"]),
        ("Duplicate texts", report["duplicate_texts"]),
    ]

    print(f"\nError Summary:")
    total_errors = 0
    for label, errors in error_types:
        total_errors += len(errors)
        status = f"✓ PASS ({len(errors)})" if len(errors) == 0 else f"✗ FAIL ({len(errors)})"
        print(f"  {label}: {status}")
        if errors and len(errors) <= 10:
            for e in errors:
                print(f"    - {e}")
        elif errors:
            for e in errors[:5]:
                print(f"    - {e}")
            print(f"    ... and {len(errors) - 5} more")

    passed = total_errors == 0
    print(f"\n{'✓ ALL CHECKS PASSED' if passed else f'✗ {total_errors} TOTAL ERRORS'}")

    # Write report
    report_path = input_path.parent / "validation_report.json"
    serializable_report = {
        "total_samples": report["total_samples"],
        "schema_errors": len(report["schema_errors"]),
        "drug_grounding_errors": len(report["drug_grounding_errors"]),
        "regimen_grounding_errors": len(report["regimen_grounding_errors"]),
        "template_placeholder_errors": len(report["template_placeholder_errors"]),
        "duplicate_texts": len(report["duplicate_texts"]),
        "total_errors": total_errors,
        "passed": passed,
        "difficulty_distribution": dict(report["difficulty_distribution"]),
    }
    with open(report_path, "w") as f:
        json.dump(serializable_report, f, indent=2)
    print(f"\nReport saved: {report_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate OncoRx-Bench dataset")
    parser.add_argument("--input", type=Path,
                        default=OUTPUT_DIR / "oncorx_bench.jsonl")
    args = parser.parse_args()
    validate_dataset(args.input)

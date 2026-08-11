#!/usr/bin/env python3
"""Export deterministic, template-disjoint OncoRx-Bench release splits.

The generator records the exact source template for every row in a separate
manifest.  This exporter keeps complete template groups together and selects
whole groups for an exact 80/20 split within every subcategory.  If an exact
grouped split is impossible, export fails instead of leaking a template across
train and test.

Usage:
    python export_csv.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from dataset_config import CATEGORY_DISTRIBUTION, OUTPUT_DIR, RANDOM_SEED


CSV_COLUMNS = [
    "sample_id",
    "clinical_text",
    "category",
    "subcategory",
    "difficulty",
    "num_drugs",
    "note_type",
    "drug_summary",
    "regimen_summary",
    "drug_mentions_json",
    "regimen_mentions_json",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"Expected an object at {path}:{line_number}")
                rows.append(value)
    return rows


def _drug_summary(drug_mentions: list[dict]) -> str:
    parts = []
    for mention in drug_mentions:
        surface = mention.get("drug_surface", "")
        normalized = mention.get("drug_normalized", "")
        flags = []
        if mention.get("negated"):
            flags.append("NEG")
        if mention.get("allergy"):
            flags.append("ALLERGY")
        if mention.get("uncertain"):
            flags.append("UNCERTAIN")
        status = mention.get("status", "current")
        if status not in ("current", ""):
            flags.append(status.upper())

        sig_parts = []
        sig = mention.get("sig") or {}
        if sig.get("dose_value"):
            sig_parts.append(
                f"{sig['dose_value']} {sig.get('dose_unit', '')}".strip()
            )
        if sig.get("route"):
            sig_parts.append(sig["route"])
        if sig.get("frequency"):
            sig_parts.append(sig["frequency"])
        if sig.get("taper"):
            sig_parts.append(f"taper: {sig['taper']}")
        if sig.get("prn"):
            sig_parts.append("PRN")

        flag_text = f" [{', '.join(flags)}]" if flags else ""
        sig_text = " | " + " ".join(sig_parts) if sig_parts else ""
        label = f"{surface} → {normalized}" if surface != normalized else normalized
        parts.append(f"{label}{flag_text}{sig_text}")
    return "; ".join(parts)


def _regimen_summary(regimen_mentions: list[dict]) -> str:
    parts = []
    for mention in regimen_mentions:
        name = mention.get("regimen_surface", "")
        components = mention.get("components_normalized", [])
        extras = [
            value
            for value in (mention.get("intent"), mention.get("cycle_info"))
            if value
        ]
        component_text = ", ".join(components)
        extra_text = f" ({'; '.join(extras)})" if extras else ""
        parts.append(f"{name} [{component_text}]{extra_text}")
    return "; ".join(parts)


def _csv_row(sample: dict) -> dict:
    return {
        "sample_id": sample["sample_id"],
        "clinical_text": sample["clinical_text"],
        "category": sample["category"],
        "subcategory": sample["subcategory"],
        "difficulty": sample["difficulty"],
        "num_drugs": sample["num_drugs"],
        "note_type": sample["note_type"],
        "drug_summary": _drug_summary(sample.get("drug_mentions", [])),
        "regimen_summary": _regimen_summary(sample.get("regimen_mentions", [])),
        "drug_mentions_json": json.dumps(
            sample.get("drug_mentions", []), ensure_ascii=False
        ),
        "regimen_mentions_json": json.dumps(
            sample.get("regimen_mentions", []), ensure_ascii=False
        ),
    }


def _write_csv(path: Path, samples: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for sample in samples:
            writer.writerow(_csv_row(sample))


def _write_jsonl(path: Path, samples: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")


def _subcategory_targets() -> dict[str, int]:
    targets = {}
    for category in CATEGORY_DISTRIBUTION.values():
        for code, details in category["subcategories"].items():
            count = details["count"]
            if count % 5:
                raise ValueError(
                    f"Subcategory {code} count {count} cannot be split exactly 80/20"
                )
            targets[code] = count // 5
    return targets


def _select_test_groups(
    subcategory: str, groups: dict[str, list[str]], target: int
) -> set[str]:
    """Choose whole template groups whose row counts sum exactly to target."""
    group_ids = sorted(groups)
    seed_bytes = hashlib.sha256(
        f"{RANDOM_SEED}:{subcategory}".encode("utf-8")
    ).digest()
    rng = random.Random(int.from_bytes(seed_bytes[:8], "big"))
    rng.shuffle(group_ids)

    possibilities: dict[int, tuple[str, ...]] = {0: ()}
    for template_id in group_ids:
        size = len(groups[template_id])
        for subtotal, selected in list(possibilities.items()):
            new_total = subtotal + size
            if new_total <= target and new_total not in possibilities:
                possibilities[new_total] = selected + (template_id,)

    if target not in possibilities:
        sizes = sorted(len(value) for value in groups.values())
        raise RuntimeError(
            f"No template-disjoint split reaches {target} test rows for "
            f"{subcategory}; template group sizes are {sizes}"
        )
    return set(possibilities[target])


def export_release(
    input_path: Path,
    assignment_path: Path,
    output_dir: Path,
) -> dict:
    samples = _load_jsonl(input_path)
    if len(samples) != 2000:
        raise ValueError(f"Expected 2,000 samples, found {len(samples)}")

    sample_by_id = {sample["sample_id"]: sample for sample in samples}
    if len(sample_by_id) != len(samples):
        raise ValueError("Duplicate sample_id values in canonical JSONL")

    with open(assignment_path, "r", encoding="utf-8") as handle:
        assignment_manifest = json.load(handle)
    assignments = assignment_manifest.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("Template assignment manifest has no assignments list")
    assignment_by_id = {item["sample_id"]: item for item in assignments}
    if len(assignment_by_id) != len(assignments):
        raise ValueError("Duplicate sample IDs in template assignment manifest")
    if set(assignment_by_id) != set(sample_by_id):
        missing = sorted(set(sample_by_id) - set(assignment_by_id))[:5]
        extra = sorted(set(assignment_by_id) - set(sample_by_id))[:5]
        raise ValueError(
            f"Template assignments do not match rows; missing={missing}, extra={extra}"
        )

    targets = _subcategory_targets()
    by_subcategory: dict[str, list[dict]] = defaultdict(list)
    template_members: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for sample in samples:
        sample_id = sample["sample_id"]
        subcategory = sample["subcategory"]
        assignment = assignment_by_id[sample_id]
        if assignment["subcategory"] != subcategory:
            raise ValueError(f"Subcategory mismatch for {sample_id}")
        by_subcategory[subcategory].append(sample)
        template_members[subcategory][assignment["template_id"]].append(sample_id)

    if set(by_subcategory) != set(targets):
        raise ValueError("Generated subcategory set does not match configuration")

    test_ids: set[str] = set()
    split_details = {}
    for subcategory in sorted(targets):
        expected_total = targets[subcategory] * 5
        actual_total = len(by_subcategory[subcategory])
        if actual_total != expected_total:
            raise ValueError(
                f"{subcategory}: expected {expected_total}, found {actual_total}"
            )
        selected = _select_test_groups(
            subcategory,
            template_members[subcategory],
            targets[subcategory],
        )
        sub_test_ids = {
            sample_id
            for template_id in selected
            for sample_id in template_members[subcategory][template_id]
        }
        if len(sub_test_ids) != targets[subcategory]:
            raise AssertionError(f"Internal split count error for {subcategory}")
        test_ids.update(sub_test_ids)
        all_templates = set(template_members[subcategory])
        split_details[subcategory] = {
            "total_rows": actual_total,
            "train_rows": actual_total - len(sub_test_ids),
            "test_rows": len(sub_test_ids),
            "train_template_ids": sorted(all_templates - selected),
            "test_template_ids": sorted(selected),
        }

    train_samples = [s for s in samples if s["sample_id"] not in test_ids]
    test_samples = [s for s in samples if s["sample_id"] in test_ids]
    if len(train_samples) != 1600 or len(test_samples) != 400:
        raise AssertionError(
            f"Expected 1,600/400 rows, found {len(train_samples)}/{len(test_samples)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "oncorx_bench_full.csv": output_dir / "oncorx_bench_full.csv",
        "oncorx_bench_train.csv": output_dir / "oncorx_bench_train.csv",
        "oncorx_bench_test.csv": output_dir / "oncorx_bench_test.csv",
        "oncorx_bench_train.jsonl": output_dir / "oncorx_bench_train.jsonl",
        "oncorx_bench_test.jsonl": output_dir / "oncorx_bench_test.jsonl",
    }
    _write_csv(artifact_paths["oncorx_bench_full.csv"], samples)
    _write_csv(artifact_paths["oncorx_bench_train.csv"], train_samples)
    _write_csv(artifact_paths["oncorx_bench_test.csv"], test_samples)
    _write_jsonl(artifact_paths["oncorx_bench_train.jsonl"], train_samples)
    _write_jsonl(artifact_paths["oncorx_bench_test.jsonl"], test_samples)

    manifest = {
        "schema_version": 1,
        "strategy": "subcategory_stratified_template_grouped_80_20",
        "random_seed": RANDOM_SEED,
        "template_disjoint": True,
        "source_jsonl": input_path.name,
        "source_jsonl_sha256": _sha256(input_path),
        "template_assignment_manifest": assignment_path.name,
        "template_assignment_manifest_sha256": _sha256(assignment_path),
        "template_catalog_sha256": assignment_manifest.get(
            "template_catalog_sha256"
        ),
        "row_counts": {
            "full": len(samples),
            "train": len(train_samples),
            "test": len(test_samples),
        },
        "subcategories": split_details,
        "artifact_sha256": {
            name: _sha256(path) for name, path in sorted(artifact_paths.items())
        },
    }
    manifest_path = output_dir / "split_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"Loaded {len(samples):,} rows from {input_path}")
    print(f"  train: {len(train_samples):,} rows")
    print(f"  test:  {len(test_samples):,} rows")
    print("  template overlap: 0")
    print(f"Release split manifest: {manifest_path}")
    return manifest


if __name__ == "__main__":
    export_release(
        input_path=OUTPUT_DIR / "oncorx_bench.jsonl",
        assignment_path=OUTPUT_DIR / "template_assignments.json",
        output_dir=OUTPUT_DIR,
    )

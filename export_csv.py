#!/usr/bin/env python3
"""
OncoRx-Bench: Export train/test splits as CSV files.

Produces flat CSVs with one row per sample. Drug mentions and regimen mentions
are serialised as JSON strings in dedicated columns, and also expanded into
human-readable summary columns for easier inspection.

Usage:
    python export_csv.py
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from dataset_config import OUTPUT_DIR, RANDOM_SEED


def _drug_summary(drug_mentions: list[dict]) -> str:
    """Human-readable one-liner of drug mentions."""
    parts = []
    for dm in drug_mentions:
        s = dm.get("drug_surface", "")
        n = dm.get("drug_normalized", "")
        flags = []
        if dm.get("negated"):
            flags.append("NEG")
        if dm.get("allergy"):
            flags.append("ALLERGY")
        if dm.get("uncertain"):
            flags.append("UNCERTAIN")
        status = dm.get("status", "current")
        if status not in ("current", ""):
            flags.append(status.upper())
        sig = dm.get("sig", {})
        sig_str = ""
        if sig:
            sig_parts = []
            if sig.get("dose_value"):
                sig_parts.append(f"{sig['dose_value']} {sig.get('dose_unit', '')}".strip())
            if sig.get("route"):
                sig_parts.append(sig["route"])
            if sig.get("frequency"):
                sig_parts.append(sig["frequency"])
            if sig.get("taper"):
                sig_parts.append(f"taper: {sig['taper']}")
            if sig.get("prn"):
                sig_parts.append("PRN")
            sig_str = " | " + " ".join(sig_parts) if sig_parts else ""

        flag_str = f" [{', '.join(flags)}]" if flags else ""
        if s != n:
            parts.append(f"{s} → {n}{flag_str}{sig_str}")
        else:
            parts.append(f"{n}{flag_str}{sig_str}")
    return "; ".join(parts)


def _regimen_summary(regimen_mentions: list[dict]) -> str:
    """Human-readable one-liner of regimen mentions."""
    parts = []
    for rm in regimen_mentions:
        name = rm.get("regimen_surface", "")
        components = rm.get("components_normalized", [])
        intent = rm.get("intent", "")
        cycle = rm.get("cycle_info", "")
        comp_str = ", ".join(components) if components else ""
        extras = []
        if intent:
            extras.append(intent)
        if cycle:
            extras.append(cycle)
        extra_str = f" ({'; '.join(extras)})" if extras else ""
        parts.append(f"{name} [{comp_str}]{extra_str}")
    return "; ".join(parts)


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


def export_csv(input_path: Path, output_dir: Path):
    """Export JSONL to CSV train/test splits."""

    # Load samples
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    print(f"Loaded {len(samples)} samples from {input_path}")

    # Stratified 80/20 split by category
    rng = random.Random(RANDOM_SEED)
    by_category: dict[str, list] = defaultdict(list)
    for s in samples:
        by_category[s["category"]].append(s)

    train_samples, test_samples = [], []
    for cat, cat_samples in by_category.items():
        rng.shuffle(cat_samples)
        split_point = int(len(cat_samples) * 0.8)
        train_samples.extend(cat_samples[:split_point])
        test_samples.extend(cat_samples[split_point:])

    rng.shuffle(train_samples)
    rng.shuffle(test_samples)

    output_dir.mkdir(parents=True, exist_ok=True)

    for split_name, split_data in [("train", train_samples), ("test", test_samples)]:
        csv_path = output_dir / f"oncorx_bench_{split_name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for s in split_data:
                writer.writerow({
                    "sample_id": s["sample_id"],
                    "clinical_text": s["clinical_text"],
                    "category": s["category"],
                    "subcategory": s["subcategory"],
                    "difficulty": s["difficulty"],
                    "num_drugs": s["num_drugs"],
                    "note_type": s["note_type"],
                    "drug_summary": _drug_summary(s.get("drug_mentions", [])),
                    "regimen_summary": _regimen_summary(s.get("regimen_mentions", [])),
                    "drug_mentions_json": json.dumps(s.get("drug_mentions", []), ensure_ascii=False),
                    "regimen_mentions_json": json.dumps(s.get("regimen_mentions", []), ensure_ascii=False),
                })
        print(f"  {split_name}: {len(split_data)} rows → {csv_path}")

    # Also export full dataset as single CSV
    full_csv = output_dir / "oncorx_bench_full.csv"
    with open(full_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for s in samples:
            writer.writerow({
                "sample_id": s["sample_id"],
                "clinical_text": s["clinical_text"],
                "category": s["category"],
                "subcategory": s["subcategory"],
                "difficulty": s["difficulty"],
                "num_drugs": s["num_drugs"],
                "note_type": s["note_type"],
                "drug_summary": _drug_summary(s.get("drug_mentions", [])),
                "regimen_summary": _regimen_summary(s.get("regimen_mentions", [])),
                "drug_mentions_json": json.dumps(s.get("drug_mentions", []), ensure_ascii=False),
                "regimen_mentions_json": json.dumps(s.get("regimen_mentions", []), ensure_ascii=False),
            })
    print(f"  full:  {len(samples)} rows → {full_csv}")
    print("✓ CSV export complete")


if __name__ == "__main__":
    export_csv(
        input_path=OUTPUT_DIR / "oncorx_bench.jsonl",
        output_dir=OUTPUT_DIR,
    )

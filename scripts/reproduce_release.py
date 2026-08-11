#!/usr/bin/env python3
"""Build or byte-check the complete OncoRx-Bench release in one command."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dataset_config import OUTPUT_DIR, RANDOM_SEED  # noqa: E402
from export_csv import export_release  # noqa: E402
from generate_dataset import generate_dataset  # noqa: E402
from scripts.profile_release import _latex_macros, build_profile  # noqa: E402
from validate_dataset import validate_dataset  # noqa: E402


GENERATED_ARTIFACTS = (
    "oncorx_bench.jsonl",
    "generation_stats.json",
    "template_assignments.json",
    "validation_report.json",
    "oncorx_bench_full.csv",
    "oncorx_bench_train.csv",
    "oncorx_bench_test.csv",
    "oncorx_bench_train.jsonl",
    "oncorx_bench_test.jsonl",
    "split_manifest.json",
    "dataset_profile.json",
    "release_manifest.json",
)

SOURCE_FILES = (
    "dataset_config.py",
    "schema.py",
    "templates.py",
    "generate_dataset.py",
    "validate_dataset.py",
    "export_csv.py",
    "scripts/build_uotd_inputs.py",
    "scripts/profile_release.py",
    "scripts/reproduce_release.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _verify_knowledge() -> dict:
    knowledge_dir = ROOT / "data" / "knowledge"
    provenance_path = knowledge_dir / "provenance.json"
    with open(provenance_path, "r", encoding="utf-8") as handle:
        provenance = json.load(handle)
    errors = []
    for filename, expected in provenance.get("outputs", {}).items():
        path = knowledge_dir / filename
        if not path.is_file():
            errors.append(f"missing {path}")
        elif _sha256(path) != expected.get("sha256"):
            errors.append(f"hash mismatch for {path}")

    transformation = provenance.get("transformation", {})
    coupled_files = {
        "scripts/build_uotd_inputs.py": transformation.get("script_sha256"),
        "dataset_config.py": transformation.get("dataset_config_sha256"),
    }
    for filename, expected_hash in coupled_files.items():
        if not expected_hash or _sha256(ROOT / filename) != expected_hash:
            errors.append(
                f"{filename} changed after knowledge materialization; rebuild views"
            )
    if errors:
        raise RuntimeError("Knowledge provenance verification failed:\n- " + "\n- ".join(errors))
    return provenance


def _write_profile(input_path: Path, output_path: Path) -> tuple[dict, str]:
    profile = build_profile(input_path)
    _write_json(output_path, profile)
    return profile, _latex_macros(profile)


def _build_in_directory(build_dir: Path, provenance: dict) -> str:
    generate_dataset(dry_run=False, output_dir=build_dir)
    report = validate_dataset(
        build_dir / "oncorx_bench.jsonl",
        report_path=build_dir / "validation_report.json",
    )
    if not report["passed"]:
        raise RuntimeError("Strict dataset validation failed")
    split_manifest = export_release(
        input_path=build_dir / "oncorx_bench.jsonl",
        assignment_path=build_dir / "template_assignments.json",
        output_dir=build_dir,
    )
    profile, latex_macros = _write_profile(
        build_dir / "oncorx_bench.jsonl",
        build_dir / "dataset_profile.json",
    )

    artifact_names = [
        name for name in GENERATED_ARTIFACTS if name != "release_manifest.json"
    ]
    manifest = {
        "schema_version": 1,
        "release": "oncorx-bench-reproducible-v1",
        "random_seed": RANDOM_SEED,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "external_packages": [],
        },
        "knowledge_provenance_sha256": _sha256(
            ROOT / "data" / "knowledge" / "provenance.json"
        ),
        "uotd": provenance["upstream"],
        "source_sha256": {
            filename: _sha256(ROOT / filename) for filename in SOURCE_FILES
        },
        "validation": {
            "passed": report["passed"],
            "total_errors": report["total_errors"],
            "error_counts": report["error_counts"],
        },
        "split": {
            "strategy": split_manifest["strategy"],
            "template_disjoint": split_manifest["template_disjoint"],
            "row_counts": split_manifest["row_counts"],
        },
        "profile": {
            "samples": profile["samples"],
            "drug_objects": profile["drug_objects"],
            "regimen_objects": profile["regimen_objects"],
        },
        "artifacts": {
            name: {
                "bytes": (build_dir / name).stat().st_size,
                "sha256": _sha256(build_dir / name),
            }
            for name in artifact_names
        },
    }
    _write_json(build_dir / "release_manifest.json", manifest)
    return latex_macros


def _compare(expected_dir: Path, actual_dir: Path, latex_macros: str) -> None:
    differences = []
    for filename in GENERATED_ARTIFACTS:
        expected = expected_dir / filename
        actual = actual_dir / filename
        if not actual.is_file():
            differences.append(f"missing committed artifact: {actual}")
        elif expected.read_bytes() != actual.read_bytes():
            differences.append(f"byte mismatch: {filename}")
    paper_stats = ROOT / "paper" / "generated_stats.tex"
    if not paper_stats.is_file() or paper_stats.read_text(encoding="utf-8") != latex_macros:
        differences.append("byte mismatch: paper/generated_stats.tex")
    if differences:
        raise RuntimeError("Reproduction check failed:\n- " + "\n- ".join(differences))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild or byte-check the full OncoRx-Bench release"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in a temporary directory and compare every release byte",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="release destination when not using --check",
    )
    parser.add_argument(
        "--uotd-dir",
        type=Path,
        default=None,
        help="also rebuild-check knowledge views against this pinned UOTD checkout",
    )
    args = parser.parse_args()

    provenance = _verify_knowledge()
    if args.uotd_dir is not None:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_uotd_inputs.py"),
                "--uotd-dir",
                str(args.uotd_dir),
                "--output-dir",
                str(ROOT / "data" / "knowledge"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    with tempfile.TemporaryDirectory(prefix="oncorx-release-") as temp_name:
        build_dir = Path(temp_name)
        latex_macros = _build_in_directory(build_dir, provenance)
        if args.check:
            _compare(build_dir, args.output_dir, latex_macros)
            print("PASS: every generated release artifact is byte-identical")
            return 0

        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename in GENERATED_ARTIFACTS:
            shutil.copyfile(build_dir / filename, args.output_dir / filename)
        paper_stats = ROOT / "paper" / "generated_stats.tex"
        paper_stats.parent.mkdir(parents=True, exist_ok=True)
        paper_stats.write_text(latex_macros, encoding="utf-8")
        print(f"Release written to: {args.output_dir}")
        print(f"Paper statistics written to: {paper_stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

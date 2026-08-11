from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dataset_config import CATEGORY_DISTRIBUTION  # noqa: E402
from export_csv import export_release  # noqa: E402


GENERATION_ARTIFACTS = (
    "oncorx_bench.jsonl",
    "generation_stats.json",
    "template_assignments.json",
)

SPLIT_ARTIFACTS = (
    "oncorx_bench_full.csv",
    "oncorx_bench_train.csv",
    "oncorx_bench_test.csv",
    "oncorx_bench_train.jsonl",
    "oncorx_bench_test.jsonl",
    "split_manifest.json",
)

EVIDENCE_TYPES = {"explicit_surface", "regimen_inference"}


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError(f"Expected a JSON object in {path}")
    return value


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AssertionError(
                    f"Expected an object at {path}:{line_number}"
                )
            rows.append(value)
    return rows


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class GenerationReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="oncorx-generation-release-test-"
        )
        cls.temp_root = Path(cls.temporary.name)
        cls.generation_a = cls.temp_root / "generation-a"
        cls.generation_b = cls.temp_root / "generation-b"
        cls.split_a = cls.temp_root / "split-a"
        cls.split_b = cls.temp_root / "split-b"

        # Use separate processes and distinct hash seeds so determinism does
        # not depend on state retained in the generator module or hash-table
        # iteration order.
        for output_dir, hash_seed in (
            (cls.generation_a, "7"),
            (cls.generation_b, "8675309"),
        ):
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONHASHSEED"] = hash_seed
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "generate_dataset.py"),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode:
                raise AssertionError(
                    "Dataset generation failed:\n"
                    f"stdout:\n{completed.stdout}\n"
                    f"stderr:\n{completed.stderr}"
                )

        with contextlib.redirect_stdout(io.StringIO()):
            cls.manifest_a = export_release(
                cls.generation_a / "oncorx_bench.jsonl",
                cls.generation_a / "template_assignments.json",
                cls.split_a,
            )
            cls.manifest_b = export_release(
                cls.generation_b / "oncorx_bench.jsonl",
                cls.generation_b / "template_assignments.json",
                cls.split_b,
            )

        cls.samples = _load_jsonl(
            cls.generation_a / "oncorx_bench.jsonl"
        )
        cls.assignments = _load_json(
            cls.generation_a / "template_assignments.json"
        )
        cls.train_samples = _load_jsonl(
            cls.split_a / "oncorx_bench_train.jsonl"
        )
        cls.test_samples = _load_jsonl(
            cls.split_a / "oncorx_bench_test.jsonl"
        )

        cls.expected_categories: dict[str, int] = {}
        cls.expected_subcategories: dict[str, int] = {}
        for category, category_details in CATEGORY_DISTRIBUTION.items():
            cls.expected_categories[category] = category_details["total"]
            for subcategory, details in category_details[
                "subcategories"
            ].items():
                cls.expected_subcategories[subcategory] = details["count"]

        drug_rows = _load_csv(
            REPO_ROOT / "data" / "knowledge" / "drug_table.csv"
        )
        regimen_rows = _load_csv(
            REPO_ROOT / "data" / "knowledge" / "regimen_table.csv"
        )
        cls.canonical_drugs = {row["drug_name"] for row in drug_rows}
        cls.canonical_regimens = {
            row["regimen_name"]: json.loads(row["components_json"])
            for row in regimen_rows
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_generation_artifacts_are_byte_identical(self) -> None:
        for name in GENERATION_ARTIFACTS:
            with self.subTest(artifact=name):
                self.assertEqual(
                    (self.generation_a / name).read_bytes(),
                    (self.generation_b / name).read_bytes(),
                )

    def test_exact_quota_and_unique_identifiers_and_texts(self) -> None:
        self.assertEqual(len(self.samples), 2000)
        self.assertEqual(
            sum(self.expected_categories.values()), len(self.samples)
        )
        self.assertEqual(
            sum(self.expected_subcategories.values()), len(self.samples)
        )

        sample_ids = [sample["sample_id"] for sample in self.samples]
        self.assertEqual(len(set(sample_ids)), 2000)
        self.assertEqual(
            sample_ids,
            [f"ONCORX-{index:04d}" for index in range(1, 2001)],
        )

        normalized_texts = {
            sample["clinical_text"].strip().casefold()
            for sample in self.samples
        }
        self.assertNotIn("", normalized_texts)
        self.assertEqual(len(normalized_texts), 2000)

        self.assertEqual(
            Counter(sample["category"] for sample in self.samples),
            Counter(self.expected_categories),
        )
        self.assertEqual(
            Counter(sample["subcategory"] for sample in self.samples),
            Counter(self.expected_subcategories),
        )

        expected_stats = {
            category: {
                subcategory: details["count"]
                for subcategory, details in category_details[
                    "subcategories"
                ].items()
            }
            for category, category_details in CATEGORY_DISTRIBUTION.items()
        }
        self.assertEqual(
            _load_json(self.generation_a / "generation_stats.json"),
            expected_stats,
        )

    def test_all_mention_offsets_slice_the_exact_surface(self) -> None:
        mention_count = 0
        for sample in self.samples:
            text = sample["clinical_text"]
            for mentions, surface_key in (
                (sample["drug_mentions"], "drug_surface"),
                (sample["regimen_mentions"], "regimen_surface"),
            ):
                for mention in mentions:
                    mention_count += 1
                    start = mention.get("start_char")
                    end = mention.get("end_char")
                    surface = mention.get(surface_key)
                    self.assertIs(type(start), int, sample["sample_id"])
                    self.assertIs(type(end), int, sample["sample_id"])
                    self.assertIsInstance(surface, str, sample["sample_id"])
                    self.assertTrue(surface, sample["sample_id"])
                    self.assertGreaterEqual(start, 0, sample["sample_id"])
                    self.assertGreater(end, start, sample["sample_id"])
                    self.assertLessEqual(end, len(text), sample["sample_id"])
                    self.assertEqual(
                        text[start:end], surface, sample["sample_id"]
                    )
        self.assertGreater(mention_count, 0)

    def test_evidence_types_and_regimen_inference_are_grounded(self) -> None:
        inferred_count = 0
        for sample in self.samples:
            for drug in sample["drug_mentions"]:
                evidence_type = drug.get("evidence_type")
                self.assertIn(
                    evidence_type, EVIDENCE_TYPES, sample["sample_id"]
                )
                if evidence_type != "regimen_inference":
                    continue

                inferred_count += 1
                corresponding_regimens = [
                    regimen
                    for regimen in sample["regimen_mentions"]
                    if regimen["regimen_surface"] == drug["drug_surface"]
                    and regimen["start_char"] == drug["start_char"]
                    and regimen["end_char"] == drug["end_char"]
                    and drug["drug_normalized"]
                    in regimen["components_normalized"]
                ]
                self.assertTrue(
                    corresponding_regimens,
                    f"{sample['sample_id']}: ungrounded regimen inference {drug}",
                )
        self.assertGreater(inferred_count, 0)

    def test_sig_dose_values_always_have_units(self) -> None:
        dose_count = 0
        for sample in self.samples:
            for drug in sample["drug_mentions"]:
                sig = drug.get("sig") or {}
                if not sig.get("dose_value"):
                    continue
                dose_count += 1
                dose_unit = sig.get("dose_unit")
                self.assertIsInstance(dose_unit, str, sample["sample_id"])
                self.assertTrue(dose_unit.strip(), sample["sample_id"])
        self.assertGreater(dose_count, 0)

    def test_normalized_drugs_and_regimens_are_canonical(self) -> None:
        regimen_count = 0
        for sample in self.samples:
            normalized_drugs = {
                drug["drug_normalized"].casefold()
                for drug in sample["drug_mentions"]
            }
            self.assertEqual(
                sample["num_drugs"],
                len(normalized_drugs),
                sample["sample_id"],
            )
            for drug in sample["drug_mentions"]:
                self.assertIn(
                    drug["drug_normalized"],
                    self.canonical_drugs,
                    sample["sample_id"],
                )

            for regimen in sample["regimen_mentions"]:
                regimen_count += 1
                normalized_name = regimen.get("regimen_normalized")
                self.assertIn(
                    normalized_name,
                    self.canonical_regimens,
                    sample["sample_id"],
                )
                expected_components = self.canonical_regimens[normalized_name]
                self.assertEqual(
                    regimen["components_normalized"],
                    expected_components,
                    sample["sample_id"],
                )
                self.assertTrue(
                    set(expected_components).issubset(self.canonical_drugs),
                    sample["sample_id"],
                )
        self.assertGreater(regimen_count, 0)

    def test_export_is_exact_exhaustive_and_template_disjoint(self) -> None:
        self.assertEqual(len(self.train_samples), 1600)
        self.assertEqual(len(self.test_samples), 400)
        self.assertEqual(
            self.manifest_a["row_counts"],
            {"full": 2000, "train": 1600, "test": 400},
        )
        self.assertTrue(self.manifest_a["template_disjoint"])

        full_ids = {sample["sample_id"] for sample in self.samples}
        train_ids = {sample["sample_id"] for sample in self.train_samples}
        test_ids = {sample["sample_id"] for sample in self.test_samples}
        self.assertEqual(len(train_ids), 1600)
        self.assertEqual(len(test_ids), 400)
        self.assertTrue(train_ids.isdisjoint(test_ids))
        self.assertEqual(train_ids | test_ids, full_ids)

        train_counts = Counter(
            sample["subcategory"] for sample in self.train_samples
        )
        test_counts = Counter(
            sample["subcategory"] for sample in self.test_samples
        )
        for subcategory, total in self.expected_subcategories.items():
            with self.subTest(subcategory=subcategory):
                self.assertEqual(total % 5, 0)
                self.assertEqual(train_counts[subcategory], total * 4 // 5)
                self.assertEqual(test_counts[subcategory], total // 5)
                details = self.manifest_a["subcategories"][subcategory]
                self.assertEqual(details["total_rows"], total)
                self.assertEqual(details["train_rows"], total * 4 // 5)
                self.assertEqual(details["test_rows"], total // 5)
                self.assertTrue(
                    set(details["train_template_ids"]).isdisjoint(
                        details["test_template_ids"]
                    )
                )

        assignment_items = self.assignments["assignments"]
        assignment_by_id = {
            item["sample_id"]: item for item in assignment_items
        }
        self.assertEqual(len(assignment_items), 2000)
        self.assertEqual(set(assignment_by_id), full_ids)
        train_templates = {
            assignment_by_id[sample_id]["template_id"]
            for sample_id in train_ids
        }
        test_templates = {
            assignment_by_id[sample_id]["template_id"]
            for sample_id in test_ids
        }
        self.assertTrue(train_templates.isdisjoint(test_templates))

        csv_ids = {
            name: {row["sample_id"] for row in _load_csv(self.split_a / name)}
            for name in (
                "oncorx_bench_full.csv",
                "oncorx_bench_train.csv",
                "oncorx_bench_test.csv",
            )
        }
        self.assertEqual(csv_ids["oncorx_bench_full.csv"], full_ids)
        self.assertEqual(csv_ids["oncorx_bench_train.csv"], train_ids)
        self.assertEqual(csv_ids["oncorx_bench_test.csv"], test_ids)

    def test_split_artifacts_are_byte_deterministic_and_checksummed(self) -> None:
        self.assertEqual(self.manifest_a, self.manifest_b)
        for name in SPLIT_ARTIFACTS:
            with self.subTest(artifact=name):
                self.assertEqual(
                    (self.split_a / name).read_bytes(),
                    (self.split_b / name).read_bytes(),
                )

        expected_hashes = self.manifest_a["artifact_sha256"]
        self.assertEqual(
            expected_hashes,
            {
                name: _sha256(self.split_a / name)
                for name in SPLIT_ARTIFACTS
                if name != "split_manifest.json"
            },
        )


if __name__ == "__main__":
    unittest.main()

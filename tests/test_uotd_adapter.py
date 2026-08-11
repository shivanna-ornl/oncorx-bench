from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "scripts" / "build_uotd_inputs.py"

spec = importlib.util.spec_from_file_location("build_uotd_inputs", ADAPTER_PATH)
if spec is None or spec.loader is None:  # pragma: no cover - import contract
    raise RuntimeError(f"Cannot import {ADAPTER_PATH}")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


EXPECTED_OUTPUT_HASHES = {
    "drug_table.csv":
        "0899d8da47de87f0db983c6915be42c46474a06e5c691089baa7c791ede5fe2e",
    "regimen_table.csv":
        "56362ba12e81f4f4c045d9f198f0729e2a9164108086389eee696c1c52990828",
    "Conditions_And_Regimens.csv":
        "6b192bf58320578f143457b645fa35445f5b660fc261d7bc24363645a7797dde",
    "regimen_projection_audit.csv":
        "725b2e99eb2904e612db940c495fea39dae6a125a4188d776e1fd0f29d62e423",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class UOTDAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="oncorx-adapter-test-")
        cls.temp_root = Path(cls.temporary.name)

        configured = os.environ.get("UOTD_DIR")
        candidates = []
        if configured:
            candidates.append(Path(configured).expanduser())
        candidates.append(REPO_ROOT.parent / "uotd_source")
        cls.uotd_dir = next(
            (
                candidate.resolve()
                for candidate in candidates
                if (candidate / "metadata" / "release_manifest.json").is_file()
            ),
            None,
        )

        if cls.uotd_dir is not None:
            cls.sources = adapter.obtain_sources(
                cls.uotd_dir, cls.temp_root / "unused-downloads"
            )
            cls.output_dir = cls.temp_root / "generated"
            cls.manifest = adapter.build_views(
                cls.sources, cls.output_dir, REPO_ROOT
            )
        else:
            # A clean public clone can run the non-network regression tests
            # against the committed, checksummed views. Set UOTD_DIR to enable
            # raw-source and CLI check-mode tests without network access.
            cls.sources = None
            cls.output_dir = REPO_ROOT / "data" / "knowledge"
            provenance = cls.output_dir / "provenance.json"
            if not provenance.is_file():
                raise unittest.SkipTest(
                    "No committed UOTD views; set UOTD_DIR for adapter tests"
                )
            cls.manifest = json.loads(provenance.read_text(encoding="utf-8"))

        cls.drugs = read_csv(cls.output_dir / "drug_table.csv")
        cls.regimens = read_csv(cls.output_dir / "regimen_table.csv")
        cls.conditions = read_csv(
            cls.output_dir / "Conditions_And_Regimens.csv"
        )
        cls.audit = read_csv(
            cls.output_dir / "regimen_projection_audit.csv"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_release_counts(self) -> None:
        canonical = [
            row for row in self.regimens
            if row["projection_method"] == "lexical_name_projection"
        ]
        aliases = [
            row for row in self.regimens
            if row["projection_method"] == "release_unique_terminal_acronym"
        ]
        self.assertEqual(len(canonical), 472)
        self.assertEqual(len(aliases), 20)
        self.assertEqual(len(self.regimens), 492)
        self.assertEqual(len(self.conditions), 804)
        self.assertEqual(
            len({row["condition_name"] for row in self.conditions}), 113
        )
        self.assertEqual(len(self.audit), 2151)

    def test_expected_output_hashes(self) -> None:
        observed = {
            name: file_sha256(self.output_dir / name)
            for name in EXPECTED_OUTPUT_HASHES
        }
        self.assertEqual(observed, EXPECTED_OUTPUT_HASHES)

    def test_tx_and_ce_are_exact(self) -> None:
        by_name = {row["regimen_name"]: row for row in self.regimens}
        self.assertEqual(
            json.loads(by_name["TX"]["components_json"]),
            ["Capecitabine", "Docetaxel"],
        )
        self.assertEqual(
            json.loads(by_name["CE"]["components_json"]),
            ["Carboplatin", "Etoposide"],
        )
        self.assertEqual(
            by_name["TX"]["projection_method"],
            "release_unique_terminal_acronym",
        )
        self.assertEqual(
            by_name["CE"]["projection_method"],
            "release_unique_terminal_acronym",
        )

    def test_known_ambiguous_or_incomplete_acronyms_are_excluded(self) -> None:
        published = {row["regimen_name"].casefold() for row in self.regimens}
        excluded = {"chop", "abvd", "folfiri", "r-chop", "mpv"}
        self.assertTrue(excluded.isdisjoint(published))

        audit_by_name = {row["regimen_name"].casefold(): row for row in self.audit}
        for name in excluded:
            row = audit_by_name[name]
            self.assertEqual(row["benchmark_eligible"], "false")
            self.assertEqual(
                row["reason"], "fewer_than_two_direct_lexical_components"
            )

    def test_fail_closed_incomplete_explicit_regimen(self) -> None:
        audit_by_name = {row["regimen_name"].casefold(): row for row in self.audit}
        row = audit_by_name["carboplatin, docetaxel, prednisone"]
        self.assertEqual(row["benchmark_eligible"], "false")
        self.assertEqual(
            row["reason"],
            "explicit_curated_component_missing_from_uotd_links",
        )
        self.assertEqual(
            json.loads(row["explicit_missing_curated_components_json"]),
            ["Prednisone"],
        )

    def test_known_collision_clusters_are_reduced_to_lexical_truth(self) -> None:
        audit_by_name = {row["regimen_name"].casefold(): row for row in self.audit}
        tx = audit_by_name["capecitabine and docetaxel (tx)"]
        ce = audit_by_name["carboplatin and etoposide (ce)"]
        self.assertEqual(int(tx["source_component_count"]), 14)
        self.assertEqual(int(tx["projected_component_count"]), 2)
        self.assertEqual(int(ce["source_component_count"]), 11)
        self.assertEqual(int(ce["projected_component_count"]), 2)

    def test_every_component_is_a_published_canonical_drug(self) -> None:
        canonical_drugs = {row["drug_name"] for row in self.drugs}
        for row in self.regimens:
            components = json.loads(row["components_json"])
            self.assertGreaterEqual(len(components), 2, row["regimen_name"])
            self.assertEqual(
                components,
                sorted(set(components), key=lambda item: (item.casefold(), item)),
            )
            self.assertTrue(
                set(components).issubset(canonical_drugs), row["regimen_name"]
            )

    def test_condition_foreign_keys_resolve(self) -> None:
        regimen_ids = {row["regimen_id"] for row in self.regimens}
        self.assertTrue(
            {row["regimen_id"] for row in self.conditions}.issubset(regimen_ids)
        )
        self.assertEqual(
            len({row["condition_id"] for row in self.conditions}),
            len(self.conditions),
        )

    def test_provenance_hashes_code_configuration_and_outputs(self) -> None:
        transformation = self.manifest["transformation"]
        self.assertEqual(transformation["adapter_version"], adapter.ADAPTER_VERSION)
        self.assertEqual(
            transformation["script_sha256"], file_sha256(ADAPTER_PATH)
        )
        self.assertEqual(
            transformation["dataset_config_sha256"],
            file_sha256(REPO_ROOT / "dataset_config.py"),
        )
        self.assertEqual(transformation["eligible_canonical_regimens"], 472)
        self.assertEqual(transformation["eligible_acronym_aliases"], 20)
        self.assertEqual(
            transformation["quarantined_explicit_incomplete_regimens"], 70
        )
        self.assertEqual(
            {
                name: metadata["sha256"]
                for name, metadata in self.manifest["outputs"].items()
            },
            EXPECTED_OUTPUT_HASHES,
        )
        self.assertEqual(
            self.manifest["upstream"]["source_files"],
            {
                relative: {"sha256": digest}
                for relative, digest in sorted(adapter.SOURCE_FILES.items())
            },
        )

    def test_check_mode_is_byte_deterministic(self) -> None:
        if self.uotd_dir is None:
            self.skipTest("Set UOTD_DIR to exercise source-to-view check mode")
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(ADAPTER_PATH),
                "--uotd-dir",
                str(self.uotd_dir),
                "--output-dir",
                str(self.output_dir),
                "--check",
            ],
            cwd=REPO_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("byte-identical", completed.stdout)

    def test_tampered_upstream_source_is_rejected(self) -> None:
        if self.uotd_dir is None:
            self.skipTest("Set UOTD_DIR to exercise source hash rejection")
        altered = self.temp_root / "altered-uotd"
        for relative in adapter.SOURCE_FILES:
            destination = altered / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.uotd_dir / relative, destination)
        target = altered / "outputs" / "production" / "Anchor_Regimen.csv"
        with target.open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            adapter.obtain_sources(altered, self.temp_root / "unused")


if __name__ == "__main__":
    unittest.main()

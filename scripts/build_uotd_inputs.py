#!/usr/bin/env python3
"""Build the three OncoRx-Bench knowledge views from a pinned UOTD release.

The adapter accepts either a local checkout of the Unified Oncology Treatment
Database (UOTD) or downloads the required release metadata and production
tables from the commit pinned below.  All source hashes are verified before
transformation.

The generated views deliberately retain the legacy filenames used by the
benchmark while encoding list-valued cells as JSON arrays.  The benchmark
loaders also accept the older comma-separated representation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import tempfile
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable


REPOSITORY = "https://github.com/shivanna-ornl/unified-oncology-treatment-database"
UOTD_COMMIT = "e4ba3722b5505cfa587b30032b8896d86baf8092"
UOTD_BUILD = "publication-build-2026-08-09"
RXNORM_DATASET_VERSION = "03-Aug-2026"
RXNORM_API_VERSION = "3.1.354"
ADAPTER_VERSION = 1

EXPECTED_UPSTREAM_ROWS = {
    "Anchor_Drugs": 5478,
    "Anchor_Drugs_And_Synonyms": 31855,
    "Anchor_Drugs_To_Regimens": 5507,
    "Anchor_Regimen": 2151,
    "Conditions_And_Regimens": 3361,
}

SOURCE_FILES = {
    "metadata/build_release.json":
        "cdf6e3231420897e9f3ccee430dbd2cf0d47dd28b386fe3829f6269e11593b09",
    "metadata/release_manifest.json":
        "6c13645b0c112297e15c6776d7c5366744fee4b14b6d394b3ffde97ae9c33c75",
    "metadata/rxnorm_api_manifest.json":
        "cf366286dbf5f6e99df13a34dd681371df77d661d2271c0e786375c14d6693d3",
    "outputs/production/Anchor_Drugs.csv":
        "4a225e5c2bf0557b4b93206f832f00e963a6ea23035b2ffcc4912878ec11ccb4",
    "outputs/production/Anchor_Drugs_And_Synonyms.csv":
        "c42f89453780896d37a1b8bb8f90799194ac2710764d980e34493298aea8c820",
    "outputs/production/Anchor_Regimen.csv":
        "9bb2ea12ca1cba2b2f668c69ce92ea306801a087d29ea6cb45da05ce58a52f01",
    "outputs/production/Anchor_Drugs_To_Regimens.csv":
        "c8ad83b432d84553cb5f14318cf11bff10be3c33ce81bfe46cfa5713673727cb",
    "outputs/production/Conditions_And_Regimens.csv":
        "b179b99ab9a0cc320ba44af368e078c120512fb47cc9d1f3214f5140b8ebb09c",
}

EXPECTED_HEADERS = {
    "outputs/production/Anchor_Drugs.csv":
        ["anchor_drug_id", "anchor_drug_name"],
    "outputs/production/Anchor_Drugs_And_Synonyms.csv":
        ["synonym_id", "anchor_drug_id", "synonym_name"],
    "outputs/production/Anchor_Regimen.csv":
        ["regimen_id", "regimen_name"],
    "outputs/production/Anchor_Drugs_To_Regimens.csv":
        ["regimen_id", "anchor_drug_id", "source_id"],
    "outputs/production/Conditions_And_Regimens.csv":
        ["condition_id", "condition_name", "regimen_id", "source_id"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _load_configuration(repo_root: Path):
    spec = importlib.util.spec_from_file_location(
        "oncorx_dataset_config", repo_root / "dataset_config.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not import dataset_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preferred_drug_casing(repo_root: Path) -> dict[str, str]:
    """Return one unambiguous display spelling for curated benchmark drugs."""
    cfg = _load_configuration(repo_root)
    candidates: list[str] = []
    candidates.extend(cfg.COMMON_DRUG_DOSES)
    candidates.extend(cfg.ONCOLOGY_DRUGS)
    candidates.extend(cfg.SUPPORTIVE_CARE_DRUGS)
    candidates.extend(cfg.ADVERSE_REACTIONS)
    candidates.extend(cfg.BRAND_NAME_MAP.values())
    candidates.extend(cfg.PRN_DRUG_CONDITIONS)
    candidates.extend(cfg.DRUG_ABBREVIATIONS.values())
    candidates.extend(cfg.MISSPELLING_PATTERNS)
    candidates.extend(cfg.PREMEDICATION_APPROPRIATE)
    candidates.extend(cfg.IV_ONLY_DRUGS)
    candidates.extend(cfg.CUMULATIVE_DOSE_DRUGS)
    candidates.extend(cfg.HIGH_NOISE_DRUGS)
    candidates.extend(cfg.HIGH_NOISE_ALIASES.values())

    result: dict[str, str] = {}
    for value in candidates:
        display = normalized(value)
        key = display.casefold()
        prior = result.get(key)
        if prior is not None and prior != display:
            raise ValueError(f"Conflicting curated spellings for {key!r}: {prior!r}, {display!r}")
        result[key] = display
    return result


def read_rows(path: Path, expected_header: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected_header:
            raise ValueError(
                f"Unexpected header in {path}: {reader.fieldnames!r}; "
                f"expected {expected_header!r}"
            )
        return list(reader)


def obtain_sources(local_checkout: Path | None, destination: Path) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for relative, expected_hash in SOURCE_FILES.items():
        if local_checkout is not None:
            source = local_checkout / relative
            if not source.is_file():
                raise FileNotFoundError(f"Missing UOTD source table: {source}")
        else:
            source = destination / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://raw.githubusercontent.com/shivanna-ornl/"
                f"unified-oncology-treatment-database/{UOTD_COMMIT}/{relative}"
            )
            with urllib.request.urlopen(url, timeout=120) as response:  # nosec B310
                source.write_bytes(response.read())
        actual_hash = sha256(source)
        if actual_hash != expected_hash:
            raise ValueError(
                f"UOTD checksum mismatch for {relative}: {actual_hash}; "
                f"expected {expected_hash}"
            )
        resolved[relative] = source
    return resolved


def write_csv(path: Path, header: list[str], rows: Iterable[list[object]]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def verify_release_metadata(sources: dict[str, Path]) -> dict:
    """Verify pinned build labels and the release manifest's table contract."""
    build_metadata = json.loads(
        sources["metadata/build_release.json"].read_text(encoding="utf-8")
    )
    release_metadata = json.loads(
        sources["metadata/release_manifest.json"].read_text(encoding="utf-8")
    )
    rxnorm_metadata = json.loads(
        sources["metadata/rxnorm_api_manifest.json"].read_text(encoding="utf-8")
    )

    if build_metadata.get("build_name") != UOTD_BUILD:
        raise ValueError("Pinned UOTD build name does not match build_release.json")
    for key, expected in (
        ("rxnorm_dataset_version", RXNORM_DATASET_VERSION),
        ("rxnorm_api_version", RXNORM_API_VERSION),
    ):
        if (
            build_metadata.get(key) != expected
            or release_metadata.get(key) != expected
            or rxnorm_metadata.get(key) != expected
        ):
            raise ValueError(f"Pinned {key} does not match UOTD metadata")

    release_rows = release_metadata.get("row_counts", {})
    for table, expected_rows in EXPECTED_UPSTREAM_ROWS.items():
        if release_rows.get(table) != expected_rows:
            raise ValueError(
                f"UOTD release row count mismatch for {table}: "
                f"{release_rows.get(table)!r}; expected {expected_rows}"
            )

    release_files = release_metadata.get("files", {})
    for relative, expected_hash in SOURCE_FILES.items():
        if not relative.startswith("outputs/production/"):
            continue
        release_entry = release_files.get(relative)
        if not isinstance(release_entry, dict):
            raise ValueError(f"UOTD release manifest omits {relative}")
        if release_entry.get("sha256") != expected_hash:
            raise ValueError(
                f"UOTD release-manifest hash mismatch for {relative}: "
                f"{release_entry.get('sha256')!r}; expected {expected_hash}"
            )
    return release_metadata


def build_views(sources: dict[str, Path], output_dir: Path, repo_root: Path) -> dict:
    verify_release_metadata(sources)

    drug_rows = read_rows(
        sources["outputs/production/Anchor_Drugs.csv"],
        EXPECTED_HEADERS["outputs/production/Anchor_Drugs.csv"],
    )
    synonym_rows = read_rows(
        sources["outputs/production/Anchor_Drugs_And_Synonyms.csv"],
        EXPECTED_HEADERS["outputs/production/Anchor_Drugs_And_Synonyms.csv"],
    )
    regimen_rows = read_rows(
        sources["outputs/production/Anchor_Regimen.csv"],
        EXPECTED_HEADERS["outputs/production/Anchor_Regimen.csv"],
    )
    link_rows = read_rows(
        sources["outputs/production/Anchor_Drugs_To_Regimens.csv"],
        EXPECTED_HEADERS["outputs/production/Anchor_Drugs_To_Regimens.csv"],
    )
    condition_rows = read_rows(
        sources["outputs/production/Conditions_And_Regimens.csv"],
        EXPECTED_HEADERS["outputs/production/Conditions_And_Regimens.csv"],
    )

    observed_rows = {
        "Anchor_Drugs": len(drug_rows),
        "Anchor_Drugs_And_Synonyms": len(synonym_rows),
        "Anchor_Drugs_To_Regimens": len(link_rows),
        "Anchor_Regimen": len(regimen_rows),
        "Conditions_And_Regimens": len(condition_rows),
    }
    if observed_rows != EXPECTED_UPSTREAM_ROWS:
        raise ValueError(
            f"UOTD source row counts differ from the pinned release: {observed_rows!r}"
        )

    casing = preferred_drug_casing(repo_root)
    source_drug_names = {
        row["anchor_drug_id"]: normalized(row["anchor_drug_name"])
        for row in drug_rows
    }
    if len(source_drug_names) != len(drug_rows):
        raise ValueError("Duplicate UOTD anchor_drug_id values")
    if len({name.casefold() for name in source_drug_names.values()}) != len(drug_rows):
        raise ValueError("Case-insensitive UOTD canonical drug-name collision")
    display_drug_names = {
        drug_id: casing.get(source_name.casefold(), source_name)
        for drug_id, source_name in source_drug_names.items()
    }

    for row in synonym_rows:
        if row["anchor_drug_id"] not in source_drug_names:
            raise ValueError(
                f"Synonym references missing drug id {row['anchor_drug_id']}"
            )

    canonical_id_by_casefold = {
        name.casefold(): drug_id for drug_id, name in source_drug_names.items()
    }
    curated_canonical_ids = {
        canonical_id_by_casefold[key]
        for key in casing
        if key in canonical_id_by_casefold
    }
    unresolved_curated_surfaces = {
        display for key, display in casing.items()
        if key not in canonical_id_by_casefold
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    regimen_names = {
        row["regimen_id"]: normalized(row["regimen_name"])
        for row in regimen_rows
    }
    if len(regimen_names) != len(regimen_rows):
        raise ValueError("Duplicate UOTD regimen_id values")
    components_by_regimen: dict[str, set[str]] = defaultdict(set)
    for row in link_rows:
        regimen_id = row["regimen_id"]
        drug_id = row["anchor_drug_id"]
        if regimen_id not in regimen_names:
            raise ValueError(f"Component link references missing regimen id {regimen_id}")
        if drug_id not in display_drug_names:
            raise ValueError(f"Component link references missing drug id {drug_id}")
        components_by_regimen[regimen_id].add(display_drug_names[drug_id])

    # UOTD's public regimen table is structurally valid, but some regimen
    # anchors combine aliases that have different component sets.  A direct
    # union of every linked component can therefore over-expand a regimen.  For
    # benchmark labels we use a conservative, auditable projection: retain only
    # component names that occur literally in the canonical regimen name, and
    # require at least two such components.  This yields high-precision
    # explicit-name regimens without treating structural QA as clinical
    # validation.
    projected_components: dict[str, list[str]] = {}
    direct_lexical_by_regimen: dict[str, list[str]] = {}
    projection_reasons: dict[str, str] = {}
    explicit_missing_by_regimen: dict[str, list[str]] = {}
    for regimen_id, regimen_name in regimen_names.items():
        candidates = {
            (component, component)
            for component in components_by_regimen[regimen_id]
        }
        possible_matches = []
        for surface, canonical in candidates:
            if len(surface) < 4 or sum(char.isalpha() for char in surface) < 3:
                continue
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(regimen_name):
                possible_matches.append((
                    match.start(), match.end(), canonical, surface
                ))
        # Prefer the longest surface at an overlapping location (for example,
        # Nab-Paclitaxel rather than both Nab-Paclitaxel and Paclitaxel).
        accepted = []
        for candidate in sorted(
            possible_matches,
            key=lambda item: (-(item[1] - item[0]), item[0], item[3].casefold()),
        ):
            if not any(candidate[0] < end and candidate[1] > start
                       for start, end, _canonical, _surface in accepted):
                accepted.append(candidate)
        matches = sorted(
            {
                canonical for _start, _end, canonical, _surface in accepted
                if canonical is not None
            },
            key=lambda item: (item.casefold(), item),
        )
        direct_lexical_by_regimen[regimen_id] = matches
        # Fail closed when an author-curated drug surface is explicit in the
        # regimen name but missing from the direct-link lexical projection.
        # This exposes incomplete UOTD links without inventing a component edge.
        curated_surface_matches = []
        for surface in casing.values():
            if len(surface) < 4:
                continue
            pattern = re.compile(
                r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            for match in pattern.finditer(regimen_name):
                curated_surface_matches.append((match.start(), match.end(), surface))
        curated_accepted = []
        for candidate in sorted(
            curated_surface_matches,
            key=lambda item: (-(item[1] - item[0]), item[0], item[2].casefold()),
        ):
            if not any(candidate[0] < end and candidate[1] > start
                       for start, end, _surface in curated_accepted):
                curated_accepted.append(candidate)
        projected_casefold = {component.casefold() for component in matches}
        explicit_missing = sorted(
            {
                surface for _start, _end, surface in curated_accepted
                if surface.casefold() not in projected_casefold
            },
            key=str.casefold,
        )
        if explicit_missing:
            explicit_missing_by_regimen[regimen_id] = explicit_missing
            projection_reasons[regimen_id] = "explicit_curated_component_missing_from_uotd_links"
        elif len(matches) >= 2:
            projected_components[regimen_id] = matches
            projection_reasons[regimen_id] = "at_least_two_direct_components_lexically_grounded_in_regimen_name"
        else:
            projection_reasons[regimen_id] = "fewer_than_two_direct_lexical_components"

    included_regimens = set(projected_components)

    display_id_by_casefold = {
        display.casefold(): drug_id for drug_id, display in display_drug_names.items()
    }
    required_drug_ids = set(curated_canonical_ids)
    for components in projected_components.values():
        for component in components:
            drug_id = display_id_by_casefold.get(component.casefold())
            if drug_id is None:
                raise ValueError(f"Projected component is not a UOTD canonical drug: {component}")
            required_drug_ids.add(drug_id)

    # Publish only canonical anchors needed by the benchmark controls and the
    # eligible regimen projection.  The full UOTD synonym inventory is used as
    # a checksummed upstream input but is not republished here; surface variants
    # used by the benchmark remain explicit in dataset_config.py.
    drug_output = output_dir / "drug_table.csv"
    drug_count = write_csv(
        drug_output,
        ["drug_name", "synonyms_json", "anchor_drug_id"],
        (
            [display_drug_names[drug_id], "[]", drug_id]
            for drug_id in sorted(required_drug_ids, key=lambda item: int(item))
        ),
    )

    # When an explicit canonical name ends in an unambiguous parenthetical
    # acronym, publish a second row for acronym-only benchmark scenarios.  The
    # acronym is accepted only when it maps to exactly one projected component
    # tuple across the entire release.
    acronym_candidates: dict[str, list[str]] = defaultdict(list)
    acronym_denials = {"HD", "HORSE", "IV", "PO", "RT", "SC"}
    for regimen_id in sorted(included_regimens, key=lambda item: int(item)):
        match = re.search(
            r"\(([A-Za-z][A-Za-z0-9+/-]{1,11})\)\s*$",
            regimen_names[regimen_id],
        )
        if match:
            acronym = match.group(1).upper()
            if acronym not in acronym_denials:
                acronym_candidates[acronym].append(regimen_id)
    safe_acronyms: dict[str, str] = {}
    for acronym, regimen_ids in acronym_candidates.items():
        component_sets = {
            tuple(projected_components[regimen_id]) for regimen_id in regimen_ids
        }
        if len(component_sets) == 1 and acronym.casefold() not in {
            name.casefold() for name in regimen_names.values()
        }:
            safe_acronyms[acronym] = min(regimen_ids, key=int)

    regimen_output = output_dir / "regimen_table.csv"
    regimen_view_rows = []
    for regimen_id in sorted(included_regimens, key=lambda item: int(item)):
        regimen_view_rows.append([
            regimen_names[regimen_id],
            json.dumps(
                projected_components[regimen_id],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            regimen_id,
            "lexical_name_projection",
            regimen_names[regimen_id],
        ])
    for acronym in sorted(safe_acronyms):
        regimen_id = safe_acronyms[acronym]
        regimen_view_rows.append([
            acronym,
            json.dumps(
                projected_components[regimen_id],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            regimen_id,
            "release_unique_terminal_acronym",
            regimen_names[regimen_id],
        ])
    regimen_count = write_csv(
        regimen_output,
        [
            "regimen_name",
            "components_json",
            "regimen_id",
            "projection_method",
            "canonical_regimen_name",
        ],
        regimen_view_rows,
    )

    condition_output = output_dir / "Conditions_And_Regimens.csv"
    retained_conditions = [
        row for row in condition_rows if row["regimen_id"] in included_regimens
    ]
    condition_count = write_csv(
        condition_output,
        ["condition_id", "condition_name", "regimen_id", "source_id", "regimen_name"],
        (
            [
                row["condition_id"],
                normalized(row["condition_name"]),
                row["regimen_id"],
                row["source_id"],
                regimen_names[row["regimen_id"]],
            ]
            for row in sorted(retained_conditions, key=lambda item: int(item["condition_id"]))
        ),
    )

    projection_audit = output_dir / "regimen_projection_audit.csv"
    audit_count = write_csv(
        projection_audit,
        [
            "regimen_id",
            "regimen_name",
            "source_component_count",
            "projected_component_count",
            "projected_components_json",
            "excluded_components_json",
            "added_lexical_components_json",
            "explicit_missing_curated_components_json",
            "benchmark_eligible",
            "reason",
        ],
        (
            [
                regimen_id,
                regimen_names[regimen_id],
                len(components_by_regimen[regimen_id]),
                len(projected_components.get(regimen_id, [])),
                json.dumps(
                    projected_components.get(regimen_id, []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    sorted(
                        components_by_regimen[regimen_id]
                        - set(projected_components.get(regimen_id, [])),
                        key=lambda item: (item.casefold(), item),
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    explicit_missing_by_regimen.get(regimen_id, []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "true" if regimen_id in included_regimens else "false",
                projection_reasons[regimen_id],
            ]
            for regimen_id in sorted(regimen_names, key=lambda item: int(item))
        ),
    )

    output_metadata = {}
    for path, rows in (
        (drug_output, drug_count),
        (regimen_output, regimen_count),
        (condition_output, condition_count),
        (projection_audit, audit_count),
    ):
        output_metadata[path.name] = {
            "rows": rows,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    manifest = {
        "schema_version": 1,
        "upstream": {
            "repository": REPOSITORY,
            "commit": UOTD_COMMIT,
            "build": UOTD_BUILD,
            "rxnorm_dataset_version": RXNORM_DATASET_VERSION,
            "rxnorm_api_version": RXNORM_API_VERSION,
            "source_files": {
                relative: {"sha256": digest}
                for relative, digest in sorted(SOURCE_FILES.items())
            },
        },
        "transformation": {
            "adapter_version": ADAPTER_VERSION,
            "script": "scripts/build_uotd_inputs.py",
            "script_sha256": sha256(repo_root / "scripts" / "build_uotd_inputs.py"),
            "dataset_config_sha256": sha256(repo_root / "dataset_config.py"),
            "drug_view": (
                "benchmark-required UOTD canonical anchors; the full upstream synonym inventory "
                "is checksum-verified but not republished"
            ),
            "regimen_view": (
                "Anchor_Regimen joined through Anchor_Drugs_To_Regimens to Anchor_Drugs; "
                "direct UOTD components conservatively projected by literal occurrence in the canonical "
                "regimen name; rows with an explicit but unlinked curated drug surface are quarantined"
            ),
            "condition_view": "Conditions_And_Regimens restricted to benchmark-eligible projected regimens",
            "list_encoding": "compact JSON arrays in CSV cells",
            "ordering": "numeric UOTD identifiers; list values sorted case-insensitively",
            "display_casing": "UOTD canonical spelling except exact curated benchmark names",
            "curated_names_without_exact_uotd_canonical_match": sorted(
                unresolved_curated_surfaces, key=str.casefold
            ),
            "excluded_uotd_synonym_rows": len(synonym_rows),
            "eligible_canonical_regimens": len(included_regimens),
            "eligible_acronym_aliases": len(safe_acronyms),
            "quarantined_explicit_incomplete_regimens": len(
                [
                    regimen_id
                    for regimen_id in explicit_missing_by_regimen
                    if len(direct_lexical_by_regimen[regimen_id]) >= 2
                ]
            ),
            "explicit_curated_surface_quarantine_rows": len(
                explicit_missing_by_regimen
            ),
            "excluded_regimens": len(regimen_names) - len(included_regimens),
            "excluded_condition_rows": len(condition_rows) - len(retained_conditions),
        },
        "outputs": output_metadata,
    }
    manifest_path = output_dir / "provenance.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def compare_directories(expected: Path, actual: Path) -> None:
    names = [
        "drug_table.csv",
        "regimen_table.csv",
        "Conditions_And_Regimens.csv",
        "regimen_projection_audit.csv",
        "provenance.json",
    ]
    differences = []
    for name in names:
        expected_path = expected / name
        actual_path = actual / name
        if not expected_path.is_file():
            differences.append(f"missing committed file: {expected_path}")
        elif expected_path.read_bytes() != actual_path.read_bytes():
            differences.append(f"content differs: {name}")
    if differences:
        raise SystemExit("UOTD view check failed:\n- " + "\n- ".join(differences))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uotd-dir",
        type=Path,
        help="Local UOTD checkout; omit to download the pinned production tables",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "knowledge",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild in a temporary directory and compare with committed views",
    )
    args = parser.parse_args()

    local_checkout = args.uotd_dir.resolve() if args.uotd_dir else None
    with tempfile.TemporaryDirectory(prefix="oncorx-uotd-") as temp_name:
        temp_root = Path(temp_name)
        sources = obtain_sources(local_checkout, temp_root / "sources")
        destination = temp_root / "generated" if args.check else args.output_dir.resolve()
        manifest = build_views(sources, destination, repo_root)
        if args.check:
            compare_directories(args.output_dir.resolve(), destination)
            print("UOTD input views are byte-identical to a clean rebuild.")
        else:
            print(f"Wrote UOTD-derived benchmark inputs to {destination}")
        for name, metadata in manifest["outputs"].items():
            print(f"  {name}: {metadata['rows']:,} rows; sha256={metadata['sha256']}")


if __name__ == "__main__":
    main()

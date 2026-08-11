# Reproducing OncoRx-Bench

## Exact benchmark release

The release uses CPython 3.9.6 and no external Python packages. From the
repository root:

```bash
python3 scripts/reproduce_release.py --check
```

This command verifies the checked-in knowledge-view hashes, regenerates all
2,000 records in a temporary directory, runs the strict validator, creates the
template-disjoint 1,600/400 split, recomputes paper statistics and every
release hash, and compares each byte with the archived artifacts. It exits
nonzero on any difference.

To intentionally refresh the archived release after a reviewed source change:

```bash
python3 scripts/reproduce_release.py
python3 scripts/reproduce_release.py --check
python3 -m unittest discover -s tests -v
```

`output/release_manifest.json` records the seed, Python version, UOTD lineage,
source hashes, artifact hashes, validation result, split policy, and profile
totals. `paper/generated_stats.tex` is derived from the same JSONL artifact.

## Rebuilding the knowledge views from UOTD

The adapter pins UOTD commit
`e4ba3722b5505cfa587b30032b8896d86baf8092`, verifies the production-table and
release-metadata SHA-256 values, and fails on any source mismatch. With a local
checkout at that commit:

```bash
python3 scripts/build_uotd_inputs.py --uotd-dir /path/to/uotd --check
python3 scripts/reproduce_release.py --uotd-dir /path/to/uotd --check
```

Omitting `--uotd-dir` from the adapter downloads only the pinned, hash-verified
files and rebuild-checks the committed views:

```bash
python3 scripts/build_uotd_inputs.py --check
```

UOTD structural QA does not establish clinical correctness of regimen
components. The OncoRx adapter therefore uses a fail-closed lexical eligibility
projection, requires at least two directly linked components supported by the
canonical regimen name, quarantines incomplete explicit names, and records all
2,151 decisions in `regimen_projection_audit.csv`.

## What is and is not reproduced

The commands reproduce the released benchmark exactly from checked-in views
and independently reproduce those views from the pinned public UOTD production
tables. Reconstructing UOTD from raw upstream sources may require separately
licensed snapshots. Public availability of derived files does not supersede
upstream terms; see `DATA_NOTICE.md`.

# OncoRx-Bench

OncoRx-Bench is a deterministic framework and 2,000-row synthetic benchmark
for oncology medication and regimen extraction. The repository contains the
generator, a conservative adapter for the
[Unified Oncology Treatment Database](https://github.com/shivanna-ornl/unified-oncology-treatment-database),
strict release validation, a template-disjoint split, tests, and the paper
source.

The corresponding dataset repository is
[AbhishekShivanna/oncorx-bench](https://huggingface.co/datasets/AbhishekShivanna/oncorx-bench).
That dataset card links back here so the data and exact generating source remain
cross-referenced.

All records are synthetic and automatically generated. They contain no patient
records, have not been independently clinically adjudicated, and must not be
used for patient care or clinical decision-making.

## Release status

- 2,000 unique records in 5 categories and 20 subcategories
- 347 versioned clinical-text templates
- 3,525 drug objects: 2,974 literal-surface objects and 551
  regimen-inference objects
- 170 normalized drugs; 433 stored evidence surfaces (328 literal drug
  surfaces and 105 regimen-evidence spans); 444 regimen objects
- strict validator: 0 errors across all release gates
- 1,600/400 train/test rows, stratified by subcategory
- 0 source templates shared between train and test
- CPython 3.9.6; no external runtime packages

These are structural and reproducibility results, not evidence of clinical
validity.

## Repository layout

```text
.
├── data/knowledge/                 # Checked-in UOTD-derived generator views
│   ├── drug_table.csv
│   ├── regimen_table.csv
│   ├── Conditions_And_Regimens.csv
│   ├── regimen_projection_audit.csv
│   └── provenance.json
├── docs/                           # Reproducibility and quality boundaries
├── output/                         # Canonical, split, profile, and manifests
├── paper/                          # CAFCW/SC26 LaTeX and generated statistics
├── scripts/
│   ├── build_uotd_inputs.py        # Pinned UOTD adapter
│   ├── profile_release.py          # JSON/LaTeX profile generation
│   └── reproduce_release.py        # One-command release build/check
├── tests/                          # Adapter, generation, split, validator tests
├── dataset_config.py
├── export_csv.py
├── generate_dataset.py
├── schema.py
├── templates.py
└── validate_dataset.py
```

There is no Hub upload or dataset-generation implementation in this source
repository. The release JSONL files are ordinary artifacts produced by the
local generator.

## Exact reproduction

Use CPython 3.9.6 from the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_release.py --check
python3 -m unittest discover -s tests -v
```

The requirements file is intentionally empty apart from a comment: generation,
validation, export, profiling, and tests use only the Python standard library.

The reproduction command verifies the checked-in knowledge hashes, regenerates
the benchmark in a temporary directory, validates it, rebuilds the
template-disjoint split and profile, and byte-compares every archived artifact.
It exits nonzero on any mismatch.

To intentionally refresh all artifacts after a reviewed code change:

```bash
python3 scripts/reproduce_release.py
python3 scripts/reproduce_release.py --check
```

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for UOTD-to-benchmark
reproduction and [output/release_manifest.json](output/release_manifest.json)
for the complete source and artifact hashes.

## UOTD knowledge materialization

The adapter pins UOTD commit
`e4ba3722b5505cfa587b30032b8896d86baf8092` and verifies release metadata and
production-table SHA-256 values before transformation. A local checkout can be
checked end to end with:

```bash
python3 scripts/build_uotd_inputs.py --uotd-dir /path/to/uotd --check
python3 scripts/reproduce_release.py --uotd-dir /path/to/uotd --check
```

The benchmark view contains 241 required canonical drug anchors, 492 eligible
regimen rows (472 canonical names plus 20 release-unique aliases), and 804
condition associations across 113 conditions. The full UOTD synonym inventory
is not republished.

UOTD's checks establish file, schema, and referential consistency rather than
clinical correctness. OncoRx therefore applies a fail-closed lexical regimen
projection and records all 2,151 retained or quarantined decisions in
`data/knowledge/regimen_projection_audit.csv`. This reduces known
over-aggregation risk but is not independent clinical validation.

## Record schema

Each JSONL row contains:

- `sample_id`, `clinical_text`, `category`, `subcategory`, and `difficulty`
- `note_type`, an author-specified scenario attribute rather than a prevalence
  estimate or independently validated document classifier
- `drug_mentions`, including exact `[start_char,end_char)` evidence offsets,
  canonical normalization, status/context flags, optional `adverse_event`, and
  optional structured `sig`
- `regimen_mentions`, including exact evidence offsets, canonical components,
  and only text-visible cycle/intent metadata
- `num_drugs`, the number of unique normalized drugs in `drug_mentions`

`evidence_type` distinguishes literal drug surfaces (`explicit_surface`) from
components inferred through a named-regimen span (`regimen_inference`). This
prevents inferred components from being presented as literal token spans.

## Split policy

The exporter uses the generator's exact template-assignment manifest. Entire
template groups remain together, and a deterministic subset-sum selection
creates an exact 80/20 split inside every subcategory. Export fails if a grouped
split cannot meet the configured counts. Drug and regimen identities may still
occur in both partitions; entity- and regimen-disjoint evaluations are future
work.

## Validation scope and limitations

The strict validator checks nested types/enums, quotas and sequential IDs,
canonical foreign keys, exact evidence spans, visible intent/cycle/adverse-event
and sig values, unique normalized-drug counts, placeholders, and duplicates.
The regression suite additionally verifies byte determinism, source tamper
rejection, split exhaustiveness, and zero template overlap.

Author-specified dose/route profiles replace the former arbitrary generic
fallbacks, and regimen-linked conditions replace independent random pairing.
Neither change turns the data into treatment guidance. Independent clinical
review, evaluation on real clinical text, and stronger entity/regimen-held-out
partitions remain necessary. See [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

Anthropic Claude assisted initial drafting of portions of the code, template
library, and configuration. The exact model revision, prompts, and decoding
settings were not retained. The retained artifacts were reviewed and revised,
are fully versioned, and invoke no LLM while generating records.

## Citation links

- Source: https://github.com/shivanna-ornl/oncorx-bench
- Dataset: https://huggingface.co/datasets/AbhishekShivanna/oncorx-bench
- Knowledge base: https://github.com/shivanna-ornl/unified-oncology-treatment-database

Use immutable commit/revision URLs in archival papers whenever available.

## License and data terms

No source-code license is currently declared in this repository. The
knowledge-view files do not receive a new license by being placed here. Review
[DATA_NOTICE.md](DATA_NOTICE.md), UOTD's notice, and upstream terms before
redistribution or commercial use.

# OncoRx-Bench: Oncology Drug Extraction Benchmark

This repository contains the original OncoRx-Bench generation, schema,
validation, and CSV export code. The published dataset is available at
[AbhishekShivanna/oncorx-bench](https://huggingface.co/datasets/AbhishekShivanna/oncorx-bench).

The records and annotations are synthetic and automatically generated. They
may contain labeling or medical errors and are not intended for clinical use,
clinical decision-making, or patient care.

## Repository Layout

- `generate_dataset.py`: dataset generator
- `dataset_config.py`: category counts and source-data paths
- `schema.py`: record and annotation schema
- `templates.py`: synthetic clinical-text templates
- `validate_dataset.py`: artifact validation
- `export_csv.py`: JSONL-to-CSV export
- `output/`: supplied JSONL, CSV, generation statistics, and validation report

Full regeneration expects five knowledge-base files in `TreatmentV4June/` at
the repository root. Those source files are not included in this repository.

## Dataset Description

**OncoRx-Bench** is a comprehensive benchmark dataset for evaluating drug and
regimen extraction systems on oncology clinical text. It contains **2,000
annotated samples** spanning five major evaluation categories, designed to test
systems across a spectrum of clinical complexity — from simple drug name
extraction to regimen acronym resolution, adverse drug reaction detection, and
noisy/misspelled clinical text.

### Key Features

- **2,000 samples** across 20 subcategories in 5 major evaluation axes
- **Rich annotation schema**: surface form, normalized name, status, negation,
  allergy, uncertainty, sig (dose/route/frequency/taper), regimen components
- **Grounded in real pharmacology**: drugs sourced from a 27,000+ drug
  knowledge base (HemOnc); regimens from 1,500+ regimen definitions
- **Difficulty-stratified**: Easy → Medium → Hard → Very Hard
- **Clinical note diversity**: progress notes, discharge summaries, chemo
  orders, pharmacy orders, telephone encounters, and more

### Intended Uses

- Benchmarking NER/IE models for clinical drug extraction
- Evaluating regimen acronym resolution systems (e.g. FOLFOX → Fluorouracil +
  Leucovorin + Oxaliplatin)
- Testing robustness to abbreviations, brand names, misspellings, negation
- Comparing retrieval-augmented vs. direct extraction approaches

## Dataset Structure

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `sample_id` | string | Unique identifier (ONCORX-0001 .. ONCORX-2000) |
| `clinical_text` | string | Input clinical text |
| `category` | string | Major category (C1–C5) |
| `subcategory` | string | Fine-grained subcategory (C1.1–C5.4) |
| `difficulty` | string | Easy, Medium, Hard, Very Hard |
| `drug_mentions` | list | Annotated drug mentions (see below) |
| `regimen_mentions` | list | Annotated regimen mentions (see below) |
| `num_drugs` | int | Number of unique drugs in clinical_text |
| `note_type` | string | Clinical note type |

### Drug Mention Schema

```json
{
  "drug_surface": "Taxol",
  "drug_normalized": "Paclitaxel",
  "status": "current",
  "negated": false,
  "allergy": false,
  "uncertain": false,
  "reason": "breast cancer",
  "sig": {
    "dose_value": "175",
    "dose_unit": "mg/m2",
    "route": "IV",
    "frequency": "q3w",
    "duration": null,
    "prn": false,
    "taper": null
  }
}
```

### Regimen Mention Schema

```json
{
  "regimen_surface": "FOLFOX",
  "regimen_normalized": "FOLFOX",
  "components_normalized": ["Fluorouracil", "Leucovorin", "Oxaliplatin"],
  "cycle_info": "q2w x 12 cycles",
  "intent": "adjuvant"
}
```

## Category Taxonomy

| Category | Label | Samples | Description |
|----------|-------|---------|-------------|
| **C1** | Core Medication Extraction | 600 | Single/dual drug mentions, supportive care |
| **C2** | Attributes & Sig Complexity | 450 | Full sig, titration/taper, PRN, duration |
| **C3** | Regimen & Oncology Complexity | 450 | Multi-drug, acronyms, partial lists, cycles/intent |
| **C4** | Context & Safety | 300 | Discontinued/hold, allergy/ADR, negation, history |
| **C5** | Noise & Ambiguity | 200 | Abbreviations, brand names, misspellings, high-noise |

### Subcategory Detail

| Code | Subcategory | Count | Difficulty |
|------|------------|-------|------------|
| C1.1 | Single drug, simple mention | 150 | Easy |
| C1.2 | Single drug with dose/route | 200 | Easy |
| C1.3 | Two drugs in sentence | 150 | Medium |
| C1.4 | Supportive care medications | 100 | Medium |
| C2.1 | Full dose + route + frequency | 150 | Medium |
| C2.2 | Titration and taper | 100 | Hard |
| C2.3 | PRN / conditional dosing | 100 | Medium |
| C2.4 | Duration and stop instructions | 100 | Medium |
| C3.1 | Multi-drug explicit | 150 | Hard |
| C3.2 | Regimen acronym only | 150 | Hard |
| C3.3 | Regimen partial drug list | 100 | Very Hard |
| C3.4 | Cycles, lines, intent | 50 | Very Hard |
| C4.1 | Discontinued / on hold | 100 | Medium |
| C4.2 | Allergy / ADR | 80 | Medium |
| C4.3 | Negated mentions | 70 | Hard |
| C4.4 | Medication history / conflicts | 50 | Hard |
| C5.1 | Abbreviations | 60 | Hard |
| C5.2 | Brand names | 60 | Medium |
| C5.3 | Misspellings / typos | 50 | Very Hard |
| C5.4 | High-noise clinical text | 30 | Very Hard |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("AbhishekShivanna/oncorx-bench")

# Access a sample
sample = ds["test"][0]
print(sample["clinical_text"])
print(sample["drug_mentions"])

# Filter by category
c3_samples = ds["test"].filter(lambda x: x["category"] == "C3_REGIMEN_ONCOLOGY")

# Filter by difficulty
hard_samples = ds["test"].filter(lambda x: x["difficulty"] in ["Hard", "Very Hard"])
```

## Evaluation Metrics

We recommend reporting:

- **Drug-level Micro F1**: Exact match on `drug_normalized`
- **Attribute Accuracy**: Status, negated, allergy correctness (C2/C4)
- **Regimen Resolution Recall**: Fraction of regimen components recovered (C3)
- **Robustness Δ**: Performance drop from Easy → Very Hard

## Dataset Generation

The dataset was generated using a template-based pipeline grounded in the
[HemOnc.org](https://hemonc.org) ontology:

1. **Drug Knowledge Base**: 27,000+ drugs with brand names, abbreviations,
   and synonyms
2. **Regimen Knowledge Base**: 1,500+ oncology regimens with constituent drugs
3. **Template Library**: 200+ clinical text templates across 20 subcategories
4. **Grounded Generation**: Drug and regimen mentions are sampled from the
   supplied knowledge-base tables

## Limitations

- Templates are synthetic — they approximate clinical text but do not capture
  the full variability of real EHR data
- Sig fields (dose/route/frequency) are drawn from standard oncology dosing
  but may not cover all real-world variations
- The supplied snapshot has not been independently clinically adjudicated and
  should be treated as an automatically generated research artifact

## Citation

```bibtex
@dataset{oncorx_bench_2024,
  title={OncoRx-Bench: A Benchmark Dataset for Drug and Regimen Extraction from Oncology Clinical Text},
  year={2024},
  url={https://huggingface.co/datasets/AbhishekShivanna/oncorx-bench},
}
```

## Source and dataset

- Source repository: https://github.com/shivanna-ornl/oncorx-bench
- Dataset repository: https://huggingface.co/datasets/AbhishekShivanna/oncorx-bench

## License and redistribution

No license is declared in this repository. Confirm source-data and
redistribution rights before redistributing the generated artifacts.

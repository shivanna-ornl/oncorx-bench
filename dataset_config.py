"""
OncoRx-Bench: Dataset configuration and category distribution.

Defines the target sample counts, category hierarchy, difficulty levels,
and paths to the drug/regimen knowledge bases.
"""
from pathlib import Path

# ── Base paths ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR
DATA_DIR = PROJECT_DIR / "data" / "knowledge"

# Knowledge-base files
DRUG_TABLE_PATH = DATA_DIR / "drug_table.csv"
REGIMEN_TABLE_PATH = DATA_DIR / "regimen_table.csv"
CONDITIONS_PATH = DATA_DIR / "Conditions_And_Regimens.csv"
KNOWLEDGE_PROVENANCE_PATH = DATA_DIR / "provenance.json"
REGIMEN_PROJECTION_AUDIT_PATH = DATA_DIR / "regimen_projection_audit.csv"

# Output
OUTPUT_DIR = BASE_DIR / "output"
RANDOM_SEED = 42

# ── Category hierarchy with target counts ──────────────────────────────

CATEGORY_DISTRIBUTION = {
    "C1_CORE_MED_EXTRACTION": {
        "label": "Core Medication Extraction",
        "total": 600,
        "subcategories": {
            "C1.1_single_drug_simple": {
                "label": "Single drug, simple mention",
                "count": 150,
                "difficulty": "Easy",
            },
            "C1.2_single_drug_dose": {
                "label": "Single drug with dose/route",
                "count": 200,
                "difficulty": "Easy",
            },
            "C1.3_two_drugs": {
                "label": "Two drugs in sentence",
                "count": 150,
                "difficulty": "Medium",
            },
            "C1.4_supportive_care": {
                "label": "Supportive care medications",
                "count": 100,
                "difficulty": "Medium",
            },
        },
    },
    "C2_ATTRIBUTES_SIG": {
        "label": "Attributes & Instruction Complexity",
        "total": 450,
        "subcategories": {
            "C2.1_dose_route_freq": {
                "label": "Full dose + route + frequency",
                "count": 150,
                "difficulty": "Medium",
            },
            "C2.2_titration_taper": {
                "label": "Titration and taper instructions",
                "count": 100,
                "difficulty": "Hard",
            },
            "C2.3_prn_conditional": {
                "label": "PRN / conditional dosing",
                "count": 100,
                "difficulty": "Medium",
            },
            "C2.4_duration_stop": {
                "label": "Duration and stop instructions",
                "count": 100,
                "difficulty": "Medium",
            },
        },
    },
    "C3_REGIMEN_ONCOLOGY": {
        "label": "Regimen & Oncology-Style Complexity",
        "total": 450,
        "subcategories": {
            "C3.1_multi_drug_explicit": {
                "label": "Multi-drug regimen, explicit drugs",
                "count": 150,
                "difficulty": "Hard",
            },
            "C3.2_regimen_acronym_only": {
                "label": "Regimen acronym only (e.g. FOLFOX)",
                "count": 150,
                "difficulty": "Hard",
            },
            "C3.3_regimen_partial": {
                "label": "Regimen with partial drug list",
                "count": 100,
                "difficulty": "Very Hard",
            },
            "C3.4_cycles_lines_intent": {
                "label": "Cycle/line/intent metadata",
                "count": 50,
                "difficulty": "Very Hard",
            },
        },
    },
    "C4_CONTEXT_SAFETY": {
        "label": "Context & Safety",
        "total": 300,
        "subcategories": {
            "C4.1_discontinued_hold": {
                "label": "Discontinued / on hold",
                "count": 100,
                "difficulty": "Medium",
            },
            "C4.2_allergy_adr": {
                "label": "Allergy / adverse drug reaction",
                "count": 80,
                "difficulty": "Medium",
            },
            "C4.3_negated": {
                "label": "Negated drug mentions",
                "count": 70,
                "difficulty": "Hard",
            },
            "C4.4_med_history_conflict": {
                "label": "Medication history / conflicts",
                "count": 50,
                "difficulty": "Hard",
            },
        },
    },
    "C5_NOISE_AMBIGUITY": {
        "label": "Noise, Ambiguity & Domain Messiness",
        "total": 200,
        "subcategories": {
            "C5.1_abbreviations": {
                "label": "Abbreviations and shortened forms",
                "count": 60,
                "difficulty": "Hard",
            },
            "C5.2_brand_names": {
                "label": "Brand name usage",
                "count": 60,
                "difficulty": "Medium",
            },
            "C5.3_misspellings": {
                "label": "Misspellings and typos",
                "count": 50,
                "difficulty": "Very Hard",
            },
            "C5.4_high_noise": {
                "label": "High-noise clinical text",
                "count": 30,
                "difficulty": "Very Hard",
            },
        },
    },
}


# ── Difficulty Weights ─────────────────────────────────────────────────
DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard", "Very Hard"]

# ── Note types ─────────────────────────────────────────────────────────
NOTE_TYPES = [
    "progress_note",
    "discharge_summary",
    "oncology_consult",
    "pharmacy_order",
    "chemo_order",
    "nursing_note",
    "medication_reconciliation",
    "allergy_note",
    "telephone_encounter",
    "treatment_plan",
]

# Note type is a scenario attribute, not an independently sampled label.  Each
# subcategory is restricted to document contexts in which its template family
# is plausible; selection within the allowed set remains seeded.
NOTE_TYPES_BY_SUBCATEGORY = {
    "C1.1_single_drug_simple": ["progress_note", "oncology_consult", "treatment_plan"],
    "C1.2_single_drug_dose": ["chemo_order", "pharmacy_order", "treatment_plan"],
    "C1.3_two_drugs": ["progress_note", "chemo_order", "treatment_plan"],
    "C1.4_supportive_care": ["chemo_order", "pharmacy_order", "progress_note"],
    "C2.1_dose_route_freq": ["chemo_order", "pharmacy_order"],
    "C2.2_titration_taper": ["treatment_plan", "discharge_summary", "progress_note"],
    "C2.3_prn_conditional": ["pharmacy_order", "discharge_summary", "progress_note"],
    "C2.4_duration_stop": ["treatment_plan", "chemo_order", "progress_note"],
    "C3.1_multi_drug_explicit": ["chemo_order", "treatment_plan", "oncology_consult"],
    "C3.2_regimen_acronym_only": ["oncology_consult", "treatment_plan", "progress_note"],
    "C3.3_regimen_partial": ["chemo_order", "nursing_note", "progress_note"],
    "C3.4_cycles_lines_intent": ["oncology_consult", "treatment_plan", "progress_note"],
    "C4.1_discontinued_hold": ["progress_note", "medication_reconciliation", "treatment_plan"],
    "C4.2_allergy_adr": ["allergy_note", "progress_note", "oncology_consult"],
    "C4.3_negated": ["oncology_consult", "progress_note", "treatment_plan"],
    "C4.4_med_history_conflict": ["medication_reconciliation", "oncology_consult", "progress_note"],
    "C5.1_abbreviations": ["chemo_order", "pharmacy_order", "nursing_note"],
    "C5.2_brand_names": ["progress_note", "medication_reconciliation", "treatment_plan"],
    "C5.3_misspellings": ["progress_note", "telephone_encounter", "pharmacy_order"],
    "C5.4_high_noise": ["progress_note", "discharge_summary", "oncology_consult", "nursing_note"],
}


# ── Commonly-encountered supportive care drugs (for C1.4 generation) ──
SUPPORTIVE_CARE_DRUGS = [
    "Ondansetron", "Granisetron", "Palonosetron", "Dexamethasone",
    "Prochlorperazine", "Metoclopramide", "Lorazepam", "Diphenhydramine",
    "Ranitidine", "Famotidine", "Omeprazole", "Pantoprazole",
    "Filgrastim", "Pegfilgrastim", "Epoetin Alfa", "Darbepoetin Alfa",
    "Megestrol", "Dronabinol", "Loperamide", "Senna",
    "Docusate", "Polyethylene Glycol", "Oxycodone", "Morphine",
    "Hydromorphone", "Fentanyl", "Gabapentin", "Pregabalin",
    "Acetaminophen", "Ibuprofen", "Allopurinol", "Rasburicase",
    "Leucovorin", "Mesna", "Amifostine", "Dexrazoxane",
    "Fluconazole", "Acyclovir", "Valacyclovir", "Sulfamethoxazole/Trimethoprim",
    "Levofloxacin", "Ciprofloxacin",
]


# ── Common abbreviation mappings for C5.1 ─────────────────────────────
DRUG_ABBREVIATIONS = {
    "5-FU": "Fluorouracil",
    "6-MP": "Mercaptopurine",
    "ARA-C": "Cytarabine",
    "BCNU": "Carmustine",
    "CCNU": "Lomustine",
    "CDDP": "Cisplatin",
    "CTX": "Cyclophosphamide",
    "DTIC": "Dacarbazine",
    "MTX": "Methotrexate",
    "VCR": "Vincristine",
    "VBL": "Vinblastine",
    "VP-16": "Etoposide",
    "CPT-11": "Irinotecan",
    "ATRA": "Tretinoin",
    "L-ASP": "Asparaginase",
    "DOXO": "Doxorubicin",
    "CARBO": "Carboplatin",
    "GEM": "Gemcitabine",
    "VNR": "Vinorelbine",
    "BLEO": "Bleomycin",
    "IFX": "Ifosfamide",
    "DAC": "Decitabine",
    "AZA": "Azacitidine",
    "PEMBRO": "Pembrolizumab",
    "NIVO": "Nivolumab",
    "ATEZO": "Atezolizumab",
    "TXL": "Paclitaxel",
    "DOC": "Docetaxel",
    "OX": "Oxaliplatin",
    "IRI": "Irinotecan",
    "BEV": "Bevacizumab",
    "CAPE": "Capecitabine",
    "TEM": "Temozolomide",
    "DARA": "Daratumumab",
    "LEN": "Lenalidomide",
    "BOR": "Bortezomib",
    "POM": "Pomalidomide",
}


# ── Common misspelling patterns for C5.3 ──────────────────────────────
MISSPELLING_PATTERNS = {
    "Cyclophosphamide": ["cyclophosphamid", "cyclophosamide", "cyclophophamide", "ciclophosphamide"],
    "Doxorubicin": ["doxyrubicin", "doxorubicine", "doxarubicin", "doxorubicn"],
    "Cisplatin": ["cis-platin", "cisplatine", "cysplatin", "cisplatinum"],
    "Carboplatin": ["carboplaten", "carboplaitn", "carboplatine", "carboplaton"],
    "Methotrexate": ["methotrexat", "methotrexte", "methotraxate", "metotrexate"],
    "Paclitaxel": ["paclitaxle", "paclitaxal", "paclitaxell", "paciltaxel"],
    "Rituximab": ["rituximad", "rituxamab", "rituxumab", "rituxiamb"],
    "Bevacizumab": ["bevacizumad", "bevacuzimab", "bevaczumab", "bevacizimab"],
    "Pembrolizumab": ["pembrolozumab", "pemrolizumab", "pembrlizumab", "pembralizumab"],
    "Nivolumab": ["nivlumab", "nivolumad", "novolumab", "nivoluamb"],
    "Capecitabine": ["capectiabine", "capecitabin", "capecitibine", "capecetabine"],
    "Irinotecan": ["irinotecane", "irinoteacon", "iriontecan", "irinotecn"],
    "Gemcitabine": ["gemcitabin", "gemcitibine", "gemciatbine", "gemcetabine"],
    "Oxaliplatin": ["oxaloplatin", "oxalipaltin", "oxaliplaten", "oxaliplatine"],
    "Fluorouracil": ["fluoruracil", "fluororuacil", "fluorouricil", "floururacil"],
    "Vincristine": ["vincristien", "vincristne", "vincristiene", "vincrstine"],
    "Etoposide": ["etoposid", "etopoisde", "etoposdide", "etopaside"],
    "Bortezomib": ["bortezomid", "bortezamib", "bortezoimb", "borteziomib"],
    "Lenalidomide": ["lenalidamide", "lenaliomide", "lenaldomide", "lenalidoimde"],
    "Temozolomide": ["temozolomid", "temozolmide", "temozolamide", "temozolomde"],
}


# ── Dose ranges for common oncology drugs ────────────────────────────
COMMON_DRUG_DOSES = {
    "Cisplatin": {"doses": ["50 mg/m2", "75 mg/m2", "100 mg/m2"], "routes": ["IV"], "freq": ["day 1 q3w", "day 1 q4w"]},
    "Carboplatin": {"doses": ["AUC 5", "AUC 6", "AUC 2"], "routes": ["IV"], "freq": ["day 1 q3w", "day 1 q4w"]},
    "Paclitaxel": {"doses": ["175 mg/m2", "80 mg/m2", "135 mg/m2"], "routes": ["IV"], "freq": ["q3w", "weekly", "day 1 q3w"]},
    "Docetaxel": {"doses": ["75 mg/m2", "100 mg/m2", "60 mg/m2"], "routes": ["IV"], "freq": ["q3w"]},
    "Doxorubicin": {"doses": ["60 mg/m2", "50 mg/m2", "75 mg/m2"], "routes": ["IV"], "freq": ["day 1 q3w", "day 1 q4w"]},
    "Cyclophosphamide": {"doses": ["600 mg/m2", "750 mg/m2", "1000 mg/m2", "100 mg"], "routes": ["IV", "PO"], "freq": ["day 1 q3w", "day 1 q4w", "daily x 14 days"]},
    "Fluorouracil": {"doses": ["400 mg/m2", "2400 mg/m2", "1000 mg/m2/day"], "routes": ["IV"], "freq": ["q2w", "days 1-4 q4w", "days 1-5 q4w"]},
    "Capecitabine": {"doses": ["1000 mg/m2", "1250 mg/m2", "850 mg/m2"], "routes": ["PO"], "freq": ["BID days 1-14 q3w"]},
    "Gemcitabine": {"doses": ["1000 mg/m2", "1250 mg/m2", "800 mg/m2"], "routes": ["IV"], "freq": ["days 1,8 q3w", "days 1,8,15 q4w"]},
    "Oxaliplatin": {"doses": ["85 mg/m2", "130 mg/m2"], "routes": ["IV"], "freq": ["q2w", "q3w"]},
    "Irinotecan": {"doses": ["180 mg/m2", "125 mg/m2", "150 mg/m2"], "routes": ["IV"], "freq": ["q2w", "days 1,8,15,22 q6w"]},
    "Methotrexate": {"doses": ["15 mg", "3.5 g/m2", "12 mg", "25 mg"], "routes": ["PO", "IV", "IT"], "freq": ["weekly", "q2w"]},
    "Vincristine": {"doses": ["1.4 mg/m2", "2 mg"], "routes": ["IV"], "freq": ["day 1 q3w", "weekly x 4"]},
    "Etoposide": {"doses": ["100 mg/m2", "50 mg/m2"], "routes": ["IV", "PO"], "freq": ["days 1-3 q3w", "days 1-5 q3w", "daily x 21 days"]},
    "Bleomycin": {"doses": ["10 units/m2", "30 units"], "routes": ["IV"], "freq": ["day 1 q3w", "days 1,8,15"]},
    "Rituximab": {"doses": ["375 mg/m2"], "routes": ["IV"], "freq": ["day 1 q3w", "weekly x 4"]},
    "Pembrolizumab": {"doses": ["200 mg", "2 mg/kg"], "routes": ["IV"], "freq": ["q3w", "q6w"]},
    "Nivolumab": {"doses": ["240 mg", "3 mg/kg", "480 mg"], "routes": ["IV"], "freq": ["q2w", "q4w"]},
    "Atezolizumab": {"doses": ["840 mg", "1200 mg", "1680 mg"], "routes": ["IV"], "freq": ["q2w", "q3w", "q4w"]},
    "Bevacizumab": {"doses": ["5 mg/kg", "7.5 mg/kg", "10 mg/kg", "15 mg/kg"], "routes": ["IV"], "freq": ["q2w", "q3w"]},
    "Trastuzumab": {"doses": ["6 mg/kg", "8 mg/kg loading"], "routes": ["IV"], "freq": ["q3w"]},
    "Bortezomib": {"doses": ["1.3 mg/m2"], "routes": ["SC", "IV"], "freq": ["days 1,4,8,11 q3w", "days 1,8,15,22 q5w"]},
    "Lenalidomide": {"doses": ["25 mg", "10 mg", "15 mg"], "routes": ["PO"], "freq": ["days 1-21 q4w", "daily"]},
    "Dexamethasone": {"doses": ["40 mg", "20 mg", "12 mg", "8 mg", "4 mg"], "routes": ["PO", "IV"], "freq": ["weekly", "days 1-4", "daily", "BID"]},
    "Prednisone": {"doses": ["100 mg", "60 mg", "40 mg", "20 mg", "10 mg", "5 mg"], "routes": ["PO"], "freq": ["daily", "daily x 5 days q4w", "BID"]},
    "Ondansetron": {"doses": ["8 mg", "4 mg", "16 mg", "0.15 mg/kg"], "routes": ["PO", "IV"], "freq": ["q8h PRN", "prior to chemo", "BID"]},
    "Filgrastim": {"doses": ["5 mcg/kg", "300 mcg", "480 mcg"], "routes": ["SC"], "freq": ["daily x 7-10 days", "daily until ANC recovery"]},
    "Pegfilgrastim": {"doses": ["6 mg"], "routes": ["SC"], "freq": ["once per cycle, day 2"]},
    "Tamoxifen": {"doses": ["20 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Letrozole": {"doses": ["2.5 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Anastrozole": {"doses": ["1 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Temozolomide": {"doses": ["75 mg/m2", "150 mg/m2", "200 mg/m2"], "routes": ["PO"], "freq": ["daily x 42 days", "days 1-5 q4w"]},
    "Azacitidine": {"doses": ["75 mg/m2"], "routes": ["SC", "IV"], "freq": ["days 1-7 q4w"]},
    "Decitabine": {"doses": ["20 mg/m2"], "routes": ["IV"], "freq": ["days 1-5 q4w"]},
    "Ibrutinib": {"doses": ["420 mg", "560 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Venetoclax": {"doses": ["400 mg", "100 mg", "200 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Imatinib": {"doses": ["400 mg", "600 mg", "800 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Sorafenib": {"doses": ["400 mg"], "routes": ["PO"], "freq": ["BID"]},
    "Sunitinib": {"doses": ["50 mg", "37.5 mg"], "routes": ["PO"], "freq": ["daily x 28 days q6w", "daily"]},
    "Erlotinib": {"doses": ["150 mg", "100 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Osimertinib": {"doses": ["80 mg", "40 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Abiraterone": {"doses": ["1000 mg"], "routes": ["PO"], "freq": ["daily"]},
    "Enzalutamide": {"doses": ["160 mg"], "routes": ["PO"], "freq": ["daily"]},
}

# ── Common adverse reactions used in C4.2 ─────────────────────────────
ADVERSE_REACTIONS = {
    "Cisplatin": ["nephrotoxicity", "ototoxicity", "severe nausea and vomiting", "peripheral neuropathy"],
    "Carboplatin": ["thrombocytopenia", "hypersensitivity reaction", "anaphylaxis"],
    "Doxorubicin": ["cardiomyopathy", "congestive heart failure", "myelosuppression"],
    "Bleomycin": ["pulmonary fibrosis", "pulmonary toxicity", "skin rash"],
    "Methotrexate": ["hepatotoxicity", "mucositis", "pancytopenia", "renal toxicity"],
    "Paclitaxel": ["anaphylaxis", "peripheral neuropathy", "neutropenia", "hypersensitivity"],
    "Fluorouracil": ["hand-foot syndrome", "mucositis", "cardiotoxicity", "diarrhea"],
    "Irinotecan": ["severe diarrhea", "cholinergic syndrome"],
    "Oxaliplatin": ["peripheral neuropathy", "cold-induced neuropathy", "anaphylaxis"],
    "Rituximab": ["infusion reaction", "progressive multifocal leukoencephalopathy"],
    "Pembrolizumab": ["immune-mediated pneumonitis", "immune-mediated colitis", "immune-mediated hepatitis"],
    "Nivolumab": ["immune-mediated pneumonitis", "immune-mediated thyroiditis", "immune-mediated colitis"],
    "Bortezomib": ["peripheral neuropathy", "thrombocytopenia"],
    "Lenalidomide": ["deep vein thrombosis", "neutropenia", "rash"],
    "Vincristine": ["peripheral neuropathy", "constipation", "jaw pain"],
    "Cyclophosphamide": ["hemorrhagic cystitis", "myelosuppression"],
    "Gemcitabine": ["myelosuppression", "pulmonary toxicity", "hemolytic uremic syndrome"],
    "Bevacizumab": ["hypertension", "proteinuria", "GI perforation", "hemorrhage"],
    "Trastuzumab": ["cardiotoxicity", "infusion reaction"],
    "Capecitabine": ["hand-foot syndrome", "diarrhea"],
}

# ── Curated list of known oncology drugs for realistic sampling ───────
# Used by C1.1 and other generators that need real oncology drugs
# instead of sampling from the full 27K-entry drug_table.
ONCOLOGY_DRUGS = [
    # Classic cytotoxics
    "Cisplatin", "Carboplatin", "Oxaliplatin",
    "Paclitaxel", "Docetaxel", "Nab-Paclitaxel",
    "Doxorubicin", "Epirubicin", "Daunorubicin", "Idarubicin",
    "Cyclophosphamide", "Ifosfamide", "Bendamustine",
    "Fluorouracil", "Capecitabine", "Gemcitabine", "Cytarabine", "Pemetrexed",
    "Methotrexate", "Vincristine", "Vinblastine", "Vinorelbine",
    "Etoposide", "Irinotecan", "Topotecan",
    "Bleomycin", "Mitomycin", "Melphalan", "Busulfan", "Chlorambucil",
    "Carmustine", "Lomustine", "Dacarbazine", "Temozolomide",
    "Procarbazine", "Hydroxyurea", "Mercaptopurine", "Thioguanine",
    "Asparaginase", "Tretinoin", "Arsenic Trioxide",
    # Targeted and small-molecule
    "Imatinib", "Dasatinib", "Nilotinib", "Ponatinib",
    "Erlotinib", "Gefitinib", "Afatinib", "Osimertinib",
    "Crizotinib", "Alectinib", "Ceritinib", "Lorlatinib",
    "Vemurafenib", "Dabrafenib", "Trametinib", "Cobimetinib",
    "Sorafenib", "Sunitinib", "Pazopanib", "Axitinib", "Cabozantinib", "Lenvatinib",
    "Ibrutinib", "Acalabrutinib", "Zanubrutinib",
    "Venetoclax", "Idelalisib",
    "Bortezomib", "Carfilzomib", "Ixazomib",
    "Lenalidomide", "Pomalidomide", "Thalidomide",
    "Olaparib", "Rucaparib", "Niraparib", "Talazoparib",
    "Everolimus", "Temsirolimus",
    "Palbociclib", "Ribociclib", "Abemaciclib",
    "Abiraterone", "Enzalutamide", "Apalutamide", "Darolutamide",
    # Hormonal
    "Tamoxifen", "Letrozole", "Anastrozole", "Exemestane", "Fulvestrant",
    "Leuprolide", "Goserelin", "Degarelix",
    # Immune checkpoint inhibitors
    "Pembrolizumab", "Nivolumab", "Atezolizumab",
    "Durvalumab", "Avelumab", "Ipilimumab", "Cemiplimab",
    # Monoclonal antibodies
    "Rituximab", "Obinutuzumab",
    "Trastuzumab", "Pertuzumab", "Trastuzumab Emtansine",
    "Bevacizumab", "Ramucirumab",
    "Cetuximab", "Panitumumab",
    "Daratumumab", "Elotuzumab",
    "Brentuximab Vedotin", "Polatuzumab Vedotin",
    # Supportive agents commonly in oncology notes
    "Dexamethasone", "Prednisone", "Methylprednisolone",
    "Azacitidine", "Decitabine",
    "Filgrastim", "Pegfilgrastim",
]

# ── Explicit brand name → generic mapping for C5.2 ───────────────────
BRAND_NAME_MAP = {
    "Keytruda": "Pembrolizumab",
    "Opdivo": "Nivolumab",
    "Tecentriq": "Atezolizumab",
    "Imfinzi": "Durvalumab",
    "Bavencio": "Avelumab",
    "Yervoy": "Ipilimumab",
    "Avastin": "Bevacizumab",
    "Herceptin": "Trastuzumab",
    "Perjeta": "Pertuzumab",
    "Rituxan": "Rituximab",
    "Erbitux": "Cetuximab",
    "Vectibix": "Panitumumab",
    "Taxol": "Paclitaxel",
    "Taxotere": "Docetaxel",
    "Abraxane": "Nab-Paclitaxel",
    "Alimta": "Pemetrexed",
    "Eloxatin": "Oxaliplatin",
    "Camptosar": "Irinotecan",
    "Xeloda": "Capecitabine",
    "Gemzar": "Gemcitabine",
    "Adriamycin": "Doxorubicin",
    "Cytoxan": "Cyclophosphamide",
    "Ifex": "Ifosfamide",
    "Velcade": "Bortezomib",
    "Revlimid": "Lenalidomide",
    "Pomalyst": "Pomalidomide",
    "Darzalex": "Daratumumab",
    "Temodar": "Temozolomide",
    "Gleevec": "Imatinib",
    "Ibrance": "Palbociclib",
    "Kisqali": "Ribociclib",
    "Verzenio": "Abemaciclib",
    "Lynparza": "Olaparib",
    "Tagrisso": "Osimertinib",
    "Tarceva": "Erlotinib",
    "Stivarga": "Regorafenib",
    "Nexavar": "Sorafenib",
    "Sutent": "Sunitinib",
    "Imbruvica": "Ibrutinib",
    "Venclexta": "Venetoclax",
    "Zytiga": "Abiraterone",
    "Xtandi": "Enzalutamide",
    "Nolvadex": "Tamoxifen",
    "Femara": "Letrozole",
    "Arimidex": "Anastrozole",
    "Faslodex": "Fulvestrant",
    "Neulasta": "Pegfilgrastim",
    "Neupogen": "Filgrastim",
    "Vidaza": "Azacitidine",
    "Adcetris": "Brentuximab Vedotin",
    "Kadcyla": "Trastuzumab Emtansine",
    "Hycamtin": "Topotecan",
    "Oncovin": "Vincristine",
    "Navelbine": "Vinorelbine",
    "VePesid": "Etoposide",
    "Platinol": "Cisplatin",
    "Paraplatin": "Carboplatin",
}

# ── PRN drug → appropriate condition mappings for C2.3 ────────────────
PRN_DRUG_CONDITIONS = {
    # Antiemetics
    "Ondansetron": {"conditions": ["nausea", "vomiting", "nausea/vomiting"], "doses": ["4 mg", "8 mg"], "routes": ["PO", "IV"], "freq": "q8h"},
    "Granisetron": {"conditions": ["nausea", "vomiting"], "doses": ["1 mg", "2 mg"], "routes": ["PO", "IV"], "freq": "q12h"},
    "Prochlorperazine": {"conditions": ["nausea", "vomiting"], "doses": ["5 mg", "10 mg"], "routes": ["PO", "IV", "PR"], "freq": "q6h"},
    "Metoclopramide": {"conditions": ["nausea", "delayed gastric emptying"], "doses": ["10 mg"], "routes": ["PO", "IV"], "freq": "q6h"},
    "Lorazepam": {"conditions": ["anxiety", "anticipatory nausea", "insomnia"], "doses": ["0.5 mg", "1 mg"], "routes": ["PO", "IV"], "freq": "q6h"},
    # Analgesics
    "Oxycodone": {"conditions": ["pain", "breakthrough pain"], "doses": ["5 mg", "10 mg", "15 mg"], "routes": ["PO"], "freq": "q4-6h"},
    "Morphine": {"conditions": ["pain", "breakthrough pain", "severe pain"], "doses": ["2 mg", "4 mg", "15 mg"], "routes": ["IV", "PO"], "freq": "q4h"},
    "Hydromorphone": {"conditions": ["pain", "breakthrough pain", "severe pain"], "doses": ["0.5 mg", "1 mg", "2 mg"], "routes": ["IV", "PO"], "freq": "q3-4h"},
    "Fentanyl": {"conditions": ["severe pain", "breakthrough pain"], "doses": ["25 mcg", "50 mcg"], "routes": ["IV", "transdermal"], "freq": "q1h"},
    "Acetaminophen": {"conditions": ["pain", "fever", "headache"], "doses": ["500 mg", "650 mg", "1000 mg"], "routes": ["PO", "IV"], "freq": "q6h"},
    "Ibuprofen": {"conditions": ["pain", "fever", "inflammation"], "doses": ["200 mg", "400 mg", "600 mg"], "routes": ["PO"], "freq": "q6-8h"},
    "Gabapentin": {"conditions": ["neuropathic pain", "peripheral neuropathy"], "doses": ["100 mg", "300 mg"], "routes": ["PO"], "freq": "q8h"},
    # GI
    "Loperamide": {"conditions": ["diarrhea", "chemotherapy-induced diarrhea"], "doses": ["2 mg", "4 mg"], "routes": ["PO"], "freq": "q4h"},
    "Diphenhydramine": {"conditions": ["allergic reaction", "insomnia", "pruritus"], "doses": ["25 mg", "50 mg"], "routes": ["PO", "IV"], "freq": "q6h"},
    # Fever/infection
    "Filgrastim": {"conditions": ["ANC < 1000", "febrile neutropenia prophylaxis"], "doses": ["300 mcg", "480 mcg"], "routes": ["SC"], "freq": "daily"},
}

# ── Suspicious drug names to filter from regimen components ───────────
SUSPICIOUS_DRUG_BLOCKLIST = {
    "Ultraviolet A", "Ultraviolet B",
    "Baker'S Antifol", "Baker's Antifol",
    "Carbenicillin", "Testosterone",
    "Antithymocyte Globulin Rabbit Atg",
    "Meg-Csf", "Bcg Vaccine",
    "Cephalosporin", "Liposome-Encapsulated",
    "Amoxicillin", "Omeprazole", "Omemprazole",
}

# ── Drugs that should never be labeled as PO (parenteral only) ────────
IV_ONLY_DRUGS = {
    "Cisplatin", "Carboplatin", "Oxaliplatin",
    "Paclitaxel", "Docetaxel", "Nab-Paclitaxel",
    "Doxorubicin", "Epirubicin", "Daunorubicin", "Idarubicin",
    "Pegylated Liposomal Doxorubicin",
    "Fluorouracil", "Cytarabine", "Pemetrexed", "Gemcitabine",
    "Vincristine", "Vinblastine", "Vinorelbine",
    "Irinotecan", "Topotecan",
    "Bleomycin", "Mitomycin", "Ifosfamide", "Bendamustine",
    "Dacarbazine", "Asparaginase",
    "Rituximab", "Obinutuzumab",
    "Trastuzumab", "Pertuzumab", "Trastuzumab Emtansine",
    "Bevacizumab", "Ramucirumab",
    "Cetuximab", "Panitumumab",
    "Daratumumab", "Elotuzumab",
    "Brentuximab Vedotin", "Polatuzumab Vedotin",
    "Pembrolizumab", "Nivolumab", "Atezolizumab",
    "Durvalumab", "Avelumab", "Ipilimumab", "Cemiplimab",
    "Carfilzomib", "Arsenic Trioxide",
}

# ── Anthracyclines with scenario-level cumulative-dose controls ──────
# These values are synthetic template constraints, not patient-specific dose
# recommendations.  They prevent the prior generic 550 mg/m2 ceiling from
# being applied to unrelated platinum agents.
CUMULATIVE_DOSE_LIMITS = {
    "Doxorubicin": "450 mg/m2",
    "Epirubicin": "900 mg/m2",
    "Daunorubicin": "550 mg/m2",
    "Idarubicin": "150 mg/m2",
}
CUMULATIVE_DOSE_DRUGS = list(CUMULATIVE_DOSE_LIMITS)

# ── Drugs appropriate for premedication / prophylaxis context (C1.4) ──
PREMEDICATION_APPROPRIATE = {
    "Ondansetron", "Granisetron", "Prochlorperazine",
    "Metoclopramide", "Lorazepam", "Diphenhydramine",
    "Acetaminophen", "Ibuprofen",
}

# Explicit distractor medications embedded in the high-noise templates.  They
# are included so C5.4 can be exhaustively annotated rather than silently
# leaving fixed medication strings outside the target objects.
HIGH_NOISE_DRUGS = {
    "Aspirin", "Famotidine", "Lorazepam", "Cefepime", "Meropenem",
    "Vancomycin", "Gentamicin", "Levofloxacin", "Ciprofloxacin",
    "Atenolol", "Amlodipine", "Metformin", "Lisinopril",
}
HIGH_NOISE_ALIASES = {"ASA": "Aspirin"}

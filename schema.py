"""
OncoRx-Bench: Schema definitions for the oncology drug extraction benchmark.

Defines the data models for drug mentions, signature (sig) fields,
regimen objects, and full benchmark samples. All models serialize
to JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ── Enumerations ──────────────────────────────────────────────────────

class DrugStatus(str, Enum):
    CURRENT = "current"
    PLANNED = "planned"
    HISTORICAL = "historical"
    DISCONTINUED = "discontinued"
    HOLD = "hold"
    UNKNOWN = "unknown"


class Route(str, Enum):
    PO = "PO"
    IV = "IV"
    SC = "SC"
    IM = "IM"
    TOPICAL = "topical"
    INHALED = "inhaled"
    OPHTHALMIC = "ophthalmic"
    INTRATHECAL = "IT"
    PR = "PR"
    SL = "SL"
    TRANSDERMAL = "transdermal"
    OTHER = "other"


class Intent(str, Enum):
    NEOADJUVANT = "neoadjuvant"
    ADJUVANT = "adjuvant"
    FIRST_LINE = "first_line"
    SECOND_LINE = "second_line"
    THIRD_LINE_PLUS = "third_line_plus"
    MAINTENANCE = "maintenance"
    PALLIATIVE = "palliative"
    CURATIVE = "curative"
    SALVAGE = "salvage"
    CONDITIONING = "conditioning"
    CONSOLIDATION = "consolidation"
    INDUCTION = "induction"
    OTHER = "other"


# ── Signature (Sig) fields ────────────────────────────────────────────

@dataclass
class SigFields:
    """Structured prescription signature extracted from clinical text."""
    dose_value: Optional[str] = None       # e.g. "75", "1000", "AUC 5"
    dose_unit: Optional[str] = None        # e.g. "mg", "mg/m2", "units"
    route: Optional[str] = None            # PO, IV, SC, etc.
    frequency: Optional[str] = None        # BID, qDay, q3w, once weekly
    duration: Optional[str] = None         # "x 7 days", "for 2 weeks"
    form: Optional[str] = None             # tablet, capsule, infusion
    prn: bool = False                      # as needed
    taper: Optional[str] = None            # "20mg x5d then 10mg x5d"
    cycle_day: Optional[str] = None        # "day 1", "days 1-3"
    infusion_time: Optional[str] = None    # "over 3 hours"

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            if v is not None and v is not False:
                d[k] = v
        return d


# ── Drug Mention ──────────────────────────────────────────────────────

@dataclass
class DrugMention:
    """A single drug mention extracted from clinical text."""
    drug_surface: str                       # exact string from text
    drug_normalized: str                    # canonical generic/ingredient name
    status: str = DrugStatus.CURRENT.value  # current, planned, historical, etc.
    negated: bool = False
    allergy: bool = False
    uncertain: bool = False                 # "may start", "consider"
    reason: Optional[str] = None            # indication (nausea, pain, DLBCL)
    sig: Optional[dict] = None              # SigFields.to_dict() output

    def to_dict(self) -> dict:
        d = {
            "drug_surface": self.drug_surface,
            "drug_normalized": self.drug_normalized,
            "status": self.status,
            "negated": self.negated,
            "allergy": self.allergy,
            "uncertain": self.uncertain,
        }
        if self.reason:
            d["reason"] = self.reason
        if self.sig:
            d["sig"] = self.sig
        return d


# ── Regimen Object ────────────────────────────────────────────────────

@dataclass
class RegimenMention:
    """A regimen mention with component resolution."""
    regimen_surface: str                           # "carbo/taxol + Keytruda"
    regimen_normalized: Optional[str] = None       # standard name e.g. "Carboplatin/Paclitaxel/Pembrolizumab"
    components_normalized: list = field(default_factory=list)  # ["Carboplatin", "Paclitaxel", "Pembrolizumab"]
    cycle_info: Optional[str] = None               # "q3w x4"
    intent: Optional[str] = None                   # neoadjuvant, adjuvant, etc.

    def to_dict(self) -> dict:
        d = {
            "regimen_surface": self.regimen_surface,
            "components_normalized": self.components_normalized,
        }
        if self.regimen_normalized:
            d["regimen_normalized"] = self.regimen_normalized
        if self.cycle_info:
            d["cycle_info"] = self.cycle_info
        if self.intent:
            d["intent"] = self.intent
        return d


# ── Full Benchmark Sample ─────────────────────────────────────────────

@dataclass
class BenchmarkSample:
    """One benchmark sample: clinical text + structured ground truth."""
    sample_id: str                                  # unique ID (e.g. "ONCORX-0001")
    clinical_text: str                              # input text
    category: str                                   # category code
    subcategory: str                                # finer-grained subcategory
    difficulty: str                                 # Easy, Medium, Hard, Very Hard
    drug_mentions: list = field(default_factory=list)   # List[DrugMention.to_dict()]
    regimen_mentions: list = field(default_factory=list) # List[RegimenMention.to_dict()]
    num_drugs: int = 0
    note_type: Optional[str] = None                 # progress_note, order, pharmacy, discharge, etc.

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "clinical_text": self.clinical_text,
            "category": self.category,
            "subcategory": self.subcategory,
            "difficulty": self.difficulty,
            "drug_mentions": self.drug_mentions,
            "regimen_mentions": self.regimen_mentions,
            "num_drugs": self.num_drugs,
            "note_type": self.note_type,
        }

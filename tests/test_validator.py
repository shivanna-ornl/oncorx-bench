"""Focused unit tests for strict release-validation primitives."""
from __future__ import annotations

import unittest

from validate_dataset import (
    ErrorCollector,
    _cycle_part_is_visible,
    _intent_is_visible,
    _parse_json_string_list,
    _validate_sig,
    _validate_span,
)


class ValidatorPrimitiveTests(unittest.TestCase):
    def test_json_array_cell_preserves_commas_inside_synonyms(self) -> None:
        errors = ErrorCollector()
        parsed = _parse_json_string_list(
            '["Drug, extended release", "Drug XR"]',
            "fixture:synonyms_json",
            errors,
            allow_empty=True,
        )
        self.assertEqual(parsed, ["Drug, extended release", "Drug XR"])
        self.assertEqual(errors.total, 0)

    def test_surface_span_must_match_exact_source_text(self) -> None:
        errors = ErrorCollector()
        self.assertTrue(
            _validate_span(
                sid="ONCORX-0001",
                object_label="drug_mentions[0]",
                text="Start Paclitaxel today.",
                surface="Paclitaxel",
                start=6,
                end=16,
                collector=errors,
            )
        )
        self.assertEqual(errors.total, 0)

        self.assertFalse(
            _validate_span(
                sid="ONCORX-0001",
                object_label="drug_mentions[0]",
                text="Start Paclitaxel today.",
                surface="paclitaxel",
                start=6,
                end=16,
                collector=errors,
            )
        )
        self.assertEqual(errors.count("text_evidence_errors"), 1)

    def test_cycle_evidence_accepts_supported_renderings(self) -> None:
        self.assertTrue(_cycle_part_is_visible("Cycle: 2/6. Next q3w.", "cycle 2/6"))
        self.assertTrue(
            _cycle_part_is_visible(
                "Patient on cycle 2 today. Plan 6 total cycles.",
                "cycle 2/6",
            )
        )
        self.assertTrue(_cycle_part_is_visible("Status C4D1.", "cycle 4"))
        self.assertTrue(_cycle_part_is_visible("Plan: regimen x6 cycles.", "6 cycles"))
        self.assertTrue(_cycle_part_is_visible("Next cycle in 3 weeks.", "q3w"))
        self.assertFalse(_cycle_part_is_visible("Cycle 2 today.", "cycle 2/6"))

    def test_normalized_intent_requires_visible_surface(self) -> None:
        self.assertTrue(_intent_is_visible("Proceed with second-line therapy.", "second_line"))
        self.assertTrue(_intent_is_visible("Plan is neo-adjuvant chemotherapy.", "neoadjuvant"))
        self.assertFalse(_intent_is_visible("Proceed with therapy.", "second_line"))

    def test_sig_requires_visible_dose_and_does_not_invent_taper_steps(self) -> None:
        valid_errors = ErrorCollector()
        _validate_sig(
            {"dose_value": "75", "dose_unit": "mg/m2", "route": "IV", "prn": True},
            sid="ONCORX-0001",
            label="drug_mentions[0]",
            text="Paclitaxel 75 mg/m2 IV PRN toxicity.",
            collector=valid_errors,
        )
        self.assertEqual(valid_errors.total, 0)

        invalid_errors = ErrorCollector()
        _validate_sig(
            {
                "dose_value": "12",
                "dose_unit": "mg",
                "taper": "12 mg → 8 mg → 4 mg",
            },
            sid="ONCORX-0002",
            label="drug_mentions[0]",
            text="Dexamethasone 12 mg; decrease by 4 mg weekly.",
            collector=invalid_errors,
        )
        self.assertEqual(invalid_errors.count("sig_errors"), 1)


if __name__ == "__main__":
    unittest.main()

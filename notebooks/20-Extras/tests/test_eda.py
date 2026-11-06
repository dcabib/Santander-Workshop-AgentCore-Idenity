"""Execute with the extras kernel: python -m unittest discover -s tests."""

import importlib.util
import json
import unittest
from pathlib import Path

import pandas as pd

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SPEC = importlib.util.spec_from_file_location("eda", ASSETS / "eda.py")
eda = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eda)


class AnalysisTests(unittest.TestCase):
    def test_detects_both_frequency_tails_and_reports_category_units(self):
        frequencies = {"rare": 1, "common": 30, **{f"middle{i}": 10 for i in range(6)}}
        frame = pd.DataFrame({"category": [key for key, count in frequencies.items()
                                           for _ in range(count)]})
        summary = eda.summarize(frame)
        self.assertEqual(summary["columns"]["category"]["outliers"], {"common": 30, "rare": 1})
        self.assertEqual(summary["outlier_categories"], 2)
        self.assertEqual(summary["outlier_unit"], "category_frequency")
        self.assertEqual(summary["rows"], 91)

    def test_actual_csv_includes_previously_omitted_low_frequency_names(self):
        summary = eda.summarize(pd.read_csv(ASSETS / "data.csv"))
        self.assertEqual(summary["rows"], 299130)
        self.assertEqual(summary["missing"], 0)
        self.assertEqual(summary["outlier_categories"], 13)
        names = summary["columns"]["Name"]
        self.assertEqual((names["lower_bound"], names["upper_bound"]), (139.5, 207.5))
        self.assertEqual({key: names["outliers"][key] for key in
                          ["James Flores", "Linda Allen", "Joshua Martinez", "Donald Jackson"]},
                         {"James Flores": 137, "Linda Allen": 132,
                          "Joshua Martinez": 132, "Donald Jackson": 120})
        self.assertEqual(summary["columns"]["Preferred_Animal"]["outliers"], {"Shark": 5761})

    def test_stream_narration_does_not_hide_json_answer(self):
        expected = {"rows": 3, "outlier_categories": 0}
        for text in [json.dumps(expected),
                     "I ran the tool.\n```json\n" + json.dumps(expected) + "\n```",
                     "Result:\n" + json.dumps(expected)]:
            with self.subTest(text=text):
                self.assertEqual(eda.parse_summary(text), expected)

    def test_invalid_answer_is_rejected(self):
        for text in ["No answer", "```json\n{invalid}\n```"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                eda.parse_summary(text)


if __name__ == "__main__":
    unittest.main()

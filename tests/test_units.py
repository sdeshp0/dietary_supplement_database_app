"""Run with: python -m unittest discover tests"""

import json
import re
import unittest
from pathlib import Path

import pandas as pd

from utils.units import Amount, normalize_amount, parse_amount, target_unit

DATA_DIR = Path(__file__).parents[1] / "data"


class ParseAmount(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_amount("250"), 250)
        self.assertEqual(parse_amount("1,000"), 1000)
        self.assertEqual(parse_amount(0.5), 0.5)

    def test_not_a_number(self):
        for text in [None, "", "<1", "~50", ">200", "-5"]:
            self.assertIsNone(parse_amount(text))


class NormalizeAmount(unittest.TestCase):
    def assertAmount(self, result, value, unit, note=False):
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, value, places=6)
        self.assertEqual(result.unit, unit)
        self.assertEqual(result.note is not None, note)

    def test_mass(self):
        self.assertAmount(normalize_amount("1", "Gram(s)", "Magnesium"), 1000, "mg")
        self.assertAmount(normalize_amount("500", "mcg", "Zinc"), 0.5, "mg")
        self.assertAmount(normalize_amount("2", "mg", "Selenium"), 2000, "mcg")
        self.assertAmount(normalize_amount("100", "ug", "Iodine"), 100, "mcg")
        self.assertAmount(normalize_amount("1200", "mg", "Omega-3"), 1.2, "g")

    def test_vitamin_d(self):
        self.assertAmount(normalize_amount("1000", "IU", "Vitamin D"), 25, "mcg")

    def test_vitamin_a(self):
        self.assertAmount(normalize_amount("5000", "IU", "Vitamin A", "Retinyl Palmitate"),
                          1500, "mcg RAE")
        self.assertAmount(normalize_amount("5000", "IU", "Vitamin A", "Vitamin A"),
                          1500, "mcg RAE", note=True)
        self.assertAmount(normalize_amount("900", "mcg RAE", "Vitamin A"), 900, "mcg RAE")
        self.assertAmount(normalize_amount("900", "mcg", "Vitamin A"), 900, "mcg RAE")

    def test_vitamin_e(self):
        self.assertAmount(normalize_amount("100", "IU", "Vitamin E", "d-alpha tocopherol"),
                          67, "mg")
        self.assertAmount(normalize_amount("100", "IU", "Vitamin E", "dl-alpha tocopheryl acetate"),
                          45, "mg")
        self.assertAmount(normalize_amount("100", "IU", "Vitamin E", "Vitamin E"),
                          67, "mg", note=True)
        self.assertAmount(normalize_amount("15", "mg {alpha}-TE", "Vitamin E"), 15, "mg")

    def test_beta_carotene(self):
        self.assertAmount(normalize_amount("5000", "IU", "Vitamin A", "Beta-Carotene"),
                          750, "mcg RAE")
        self.assertAmount(normalize_amount("3", "mg", "Vitamin A", "Beta-Carotene"),
                          1500, "mcg RAE", note=True)
        self.assertAmount(normalize_amount("900", "mcg", "Vitamin A", "Beta-Carotene"),
                          900, "mcg RAE", note=True)
        self.assertAmount(normalize_amount("900", "mcg RAE", "Vitamin A", "Beta-Carotene"),
                          900, "mcg RAE")

    def test_vitamin_k_and_molybdenum_in_mcg(self):
        self.assertAmount(normalize_amount("0.1", "mg", "Vitamin K", "Vitamin K1"), 100, "mcg")
        self.assertAmount(normalize_amount("75", "mcg", "Molybdenum"), 75, "mcg")

    def test_folate(self):
        self.assertAmount(normalize_amount("400", "mcg DFE", "Folate"), 400, "mcg DFE")
        self.assertAmount(normalize_amount("400", "mcg", "Folate", "Folic Acid"), 680, "mcg DFE")
        self.assertAmount(normalize_amount("1", "mg", "Folate", "Folic Acid"), 1700, "mcg DFE")
        self.assertAmount(normalize_amount("400", "mcg", "Folate", "Folate"),
                          680, "mcg DFE", note=True)

    def test_niacin_equivalents(self):
        self.assertAmount(normalize_amount("20", "mg NE", "Niacin"), 20, "mg")

    def test_units_that_dont_convert(self):
        self.assertEqual(normalize_amount("10", "CFU", "Probiotics"), Amount(10, "CFU"))
        self.assertEqual(normalize_amount("500", "HUT", "Protease"), Amount(500, "HUT"))
        self.assertEqual(normalize_amount("400", "IU", "Zinc"), Amount(400, "IU"))

    def test_no_amount(self):
        self.assertIsNone(normalize_amount(None, "mg", "Zinc"))
        self.assertIsNone(normalize_amount("<1", "g", "Fiber"))
        self.assertIsNone(normalize_amount("5", None, "Zinc"))


class TargetUnits(unittest.TestCase):
    def test_match_ods_recommended_amounts(self):
        """Each compound's target unit is the unit of its ODS recommended amount."""
        metadata = pd.read_csv(DATA_DIR / "compound_metadata.csv")
        unit = re.compile(r"[\d.,]+\s*(mcg DFE|mcg RAE|mg NE|mcg|mg|g)\b")
        checked = 0
        for row in metadata.itertuples():
            if not isinstance(row.rda_json, str) or row.rda_json.strip() in ("", "[]"):
                continue
            amounts = [v for entry in json.loads(row.rda_json) for k, v in entry.items()
                       if k.startswith("Recommended Amount") and isinstance(v, str)]
            units = {m.group(1) for a in amounts if (m := unit.search(a))}
            # Niacin is given in mg NE, which equals mg for supplements
            units = {"mg" if u == "mg NE" else u for u in units}
            with self.subTest(compound=row.compound):
                self.assertIn(target_unit(row.compound), units)
            checked += 1
        self.assertGreater(checked, 20)


if __name__ == "__main__":
    unittest.main()

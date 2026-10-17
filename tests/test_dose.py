"""Run with: python -m unittest discover tests"""

import unittest

from utils.dose import Comparison, adult_reference, compare_dose


class AdultReference(unittest.TestCase):
    def test_ranges_across_sexes_and_ages(self):
        calcium = adult_reference("Calcium")
        self.assertEqual(calcium.unit, "mg")
        self.assertEqual(calcium.rda, (1000, 1200))
        self.assertEqual(calcium.ul, (2000, 2500))

    def test_leaves_out_pregnancy_and_teens(self):
        self.assertEqual(adult_reference("Iron").rda, (8, 18))
        self.assertEqual(adult_reference("Magnesium").rda, (310, 420))

    def test_units(self):
        self.assertEqual(adult_reference("Vitamin D").rda, (15, 20))
        self.assertEqual(adult_reference("Vitamin D").ul, (100, 100))
        self.assertEqual(adult_reference("Copper").ul, (10000, 10000))

    def test_folate_upper_limit_in_dfe(self):
        folate = adult_reference("Folate")
        self.assertEqual(folate.unit, "mcg DFE")
        self.assertAlmostEqual(folate.ul[0], 1700)

    def test_vitamin_e_upper_limit(self):
        self.assertEqual(adult_reference("Vitamin E").ul, (1000, 1000))

    def test_vitamin_k(self):
        self.assertEqual(adult_reference("Vitamin K").rda, (90, 120))
        self.assertIsNone(adult_reference("Vitamin K").ul)

    def test_not_compared(self):
        self.assertIsNone(adult_reference("Omega-3"))
        self.assertIsNone(adult_reference("Ashwagandha"))


class CompareDose(unittest.TestCase):
    def test_percent_of_rda(self):
        self.assertEqual(compare_dose("Calcium", "Calcium", "600", "mg"),
                         Comparison("50–60%", ""))
        self.assertEqual(compare_dose("Vitamin D", "Vitamin D3", "1000", "IU"),
                         Comparison("125–167%", ""))

    def test_upper_limit(self):
        self.assertEqual(compare_dose("Vitamin D", "Vitamin D3", "5000", "IU").upper_limit,
                         "Over the limit")
        self.assertEqual(compare_dose("Calcium", "Calcium", "2200", "mg").upper_limit,
                         "Over for some adults")
        self.assertEqual(compare_dose("Zinc", "Zinc", "30", "mg").upper_limit, "")

    def test_estimate(self):
        result = compare_dose("Vitamin A", "Vitamin A", "25000", "IU")
        self.assertTrue(result.percent_of_rda.endswith("(estimate)"))
        self.assertEqual(result.upper_limit, "Over the limit (estimate)")

    def test_beta_carotene_has_no_upper_limit(self):
        # The vitamin A upper limit is for preformed vitamin A only
        result = compare_dose("Vitamin A", "Beta-Carotene", "25000", "IU")
        self.assertEqual(result.percent_of_rda, "417–536%")
        self.assertEqual(result.upper_limit, "")

    def test_salt_names_not_compared(self):
        result = compare_dose("Magnesium", "Magnesium Citrate", "500", "mg")
        self.assertEqual(result.percent_of_rda, "")
        self.assertIn("salt", result.upper_limit)

    def test_unit_error(self):
        self.assertIn("unit error",
                      compare_dose("Vitamin D", "Vitamin D3", "1000", "mg").upper_limit)

    def test_nothing_to_compare(self):
        self.assertIsNone(compare_dose(None, "Ginger", "100", "mg"))
        self.assertIsNone(compare_dose("Probiotics", "L. acidophilus", "10", "CFU"))
        self.assertIsNone(compare_dose("Calcium", "Calcium", None, "mg"))
        self.assertIsNone(compare_dose("Calcium", "Calcium", "5", "%"))


if __name__ == "__main__":
    unittest.main()

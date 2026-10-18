"""Run with: python -m unittest discover tests"""

import unittest

import pandas as pd

from utils.stack import (StackItem, choose_label_column, format_stack, parse_stack,
                         product_doses, stack_totals)

ALIASES = {
    "vitamin a": "Vitamin A",
    "beta-carotene": "Vitamin A",
    "vitamin d3": "Vitamin D",
    "magnesium": "Magnesium",
    "magnesium citrate": "Magnesium",
    "vitamin k1": "Vitamin K",
    "vitamin k2": "Vitamin K2",
    "turmeric": "Curcumin",
}


def facts(rows, serving="1 Tablet(s)"):
    """Supplement Facts rows from (ingredient, amount, unit[, target group[, serving]])."""
    records = []
    for order, row in enumerate(rows):
        ingredient, amount, unit, *rest = row
        records.append({
            "Ingredient": ingredient,
            "Amount Per Serving": amount,
            "Amount Per Serving Unit": unit,
            "Daily Value Target Group": rest[0] if rest else "Adults and children 4 or more years of age",
            "Serving Size": rest[1] if len(rest) > 1 else serving,
            "Row Order": order,
        })
    return pd.DataFrame(records)


class StackLink(unittest.TestCase):
    def test_round_trip(self):
        items = [StackItem(683, 1.0), StackItem(2043, 2.5)]
        self.assertEqual(format_stack(items), "683:1,2043:2.5")
        self.assertEqual(parse_stack("683:1,2043:2.5"), items)

    def test_bad_entries_skipped(self):
        self.assertEqual(parse_stack("683,abc,683:2,9:0,10:99,11:2"),
                         [StackItem(683, 1.0), StackItem(11, 2.0)])
        self.assertEqual(parse_stack(None), [])


class LabelColumn(unittest.TestCase):
    def test_serving_size_for_adults(self):
        rows = facts([
            ("Vitamin A", "2500", "IU", "Children less than 4 years of age", "0.5 Tablet(s)"),
            ("Vitamin A", "5000", "IU", "Adults and children 4 or more years of age", "1 Tablet(s)"),
            ("Vitamin D3", "200", "IU", "Children less than 4 years of age", "0.5 Tablet(s)"),
            ("Vitamin D3", "400", "IU", "Adults and children 4 or more years of age", "1 Tablet(s)"),
        ])
        self.assertEqual(choose_label_column(rows)["Amount Per Serving"].tolist(), ["5000", "400"])

    def test_consecutive_columns_for_one_serving(self):
        rows = facts([
            ("Vitamin A", "4500", "IU"), ("Vitamin A", "4800", "IU"), ("Vitamin A", "3000", "IU", None),
            ("Magnesium", "100", "mg"),
            ("Vitamin D3", "450", "IU"), ("Vitamin D3", "500", "IU"), ("Vitamin D3", "300", "IU", None),
        ])
        self.assertEqual(choose_label_column(rows)["Amount Per Serving"].tolist(),
                         ["4500", "100", "450"])


class ProductDoses(unittest.TestCase):
    def test_form_under_its_total_is_not_added(self):
        doses = product_doses(facts([
            ("Vitamin A", "5000", "IU"),
            ("Beta-Carotene", "3000", "IU", None),
        ]), ALIASES)
        self.assertEqual(doses["not_counted"].tolist(), ["", "Part of the total above it"])
        self.assertAlmostEqual(doses["dose"].iloc[0], 1500)

    def test_why_not_counted(self):
        doses = product_doses(facts([
            ("Magnesium Citrate", "500", "mg"),
            ("Vitamin D3", "5000", "mg"),
            ("Magnesium", None, None),
            ("Turmeric", "500", "mg"),
        ]), ALIASES)
        # Turmeric (curcumin) has no adult reference amount, so it isn't listed
        self.assertEqual(doses["not_counted"].tolist(), [
            "Weight of the whole salt", "Likely a unit error on the label",
            "No amount on the label",
        ])


class StackTotals(unittest.TestCase):
    def test_totals_across_products_and_servings(self):
        multi = product_doses(facts([("Vitamin D3", "1000", "IU"), ("Magnesium", "100", "mg")]), ALIASES)
        vitamin_d = product_doses(facts([("Vitamin D3", "5000", "IU")]), ALIASES)
        totals, not_counted = stack_totals([("Multi", 2, multi), ("D3", 1, vitamin_d)])
        totals = totals.set_index("Nutrient")
        self.assertEqual(totals.loc["Vitamin D", "Total per day"], "175 mcg")
        self.assertEqual(totals.loc["Vitamin D", "Upper limit"], "Over the limit")
        self.assertEqual(totals.loc["Vitamin D", "From"], "Multi: 50 mcg; D3: 125 mcg")
        self.assertEqual(totals.loc["Magnesium", "Total per day"], "200 mg")
        self.assertTrue(not_counted.empty)

    def test_vitamin_k_forms_add_up(self):
        doses = product_doses(facts([("Vitamin K1", "90", "mcg"), ("Vitamin K2", "45", "mcg")]), ALIASES)
        totals, _ = stack_totals([("Multi", 1, doses)])
        self.assertEqual(totals.set_index("Nutrient").loc["Vitamin K", "Total per day"], "135 mcg")

    def test_beta_carotene_not_held_to_vitamin_a_limit(self):
        retinol = product_doses(facts([("Vitamin A", "5000", "IU")]), ALIASES)
        carotene = product_doses(facts([("Beta-Carotene", "25000", "IU")]), ALIASES)
        totals, _ = stack_totals([("A", 1, retinol), ("Carotene", 1, carotene)])
        vitamin_a = totals.set_index("Nutrient").loc["Vitamin A"]
        self.assertEqual(vitamin_a["Total per day"], "5,250 mcg RAE")
        self.assertEqual(vitamin_a["Upper limit"], "")

    def test_empty(self):
        totals, not_counted = stack_totals([])
        self.assertTrue(totals.empty)
        self.assertTrue(not_counted.empty)


if __name__ == "__main__":
    unittest.main()

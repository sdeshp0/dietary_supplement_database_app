"""
Adds up each nutrient across the products in a supplement stack, per day,
and compares the totals with the adult RDA and upper limit (utils/dose.py).

A stack is a list of (DSLD ID, servings per day). It travels in the page
link as "683:1,2043:2", so it can be bookmarked or shared.
"""

import re
from typing import NamedTuple

import pandas as pd

from utils.dose import (SALT_NAME, SALT_WEIGHT, adult_reference, compare_amount,
                        looks_like_unit_error)
from utils.units import is_beta_carotene, normalize_amount, target_unit

# Compounds whose reference amounts cover another compound's forms, so the
# stack adds them together (the vitamin K AI covers K1 and K2)
STACK_GROUPS = {
    "Vitamin K2": "Vitamin K",
    "B3": "Niacin",
    "B7": "Biotin",
}

MAX_SERVINGS = 20


class StackItem(NamedTuple):
    dsld_id: int
    servings: float


def parse_stack(text):
    """[StackItem] from "683:1,2043:2"; bad entries are skipped."""
    items, seen = [], set()
    for part in str(text or "").split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?::\s*(\d+(?:\.\d+)?))?\s*", part)
        if not match:
            continue
        dsld_id = int(match.group(1))
        servings = float(match.group(2)) if match.group(2) else 1.0
        if dsld_id in seen or not 0 < servings <= MAX_SERVINGS:
            continue
        seen.add(dsld_id)
        items.append(StackItem(dsld_id, servings))
    return items


def format_stack(items):
    return ",".join(f"{i.dsld_id}:{i.servings:g}" for i in items)


def _normalize(name):
    return " ".join(str(name).lower().split()) if isinstance(name, str) else ""


def choose_label_column(facts):
    """
    The rows of one label column. Some labels give amounts for several
    serving sizes or preparations (children and adults, with or without
    milk). DSLD lists a column per serving size as its own block of rows,
    and columns for the same serving size as runs of the same ingredient
    on consecutive rows. This keeps one column: the one with the most rows
    for adults, or the first.
    """
    if facts.empty:
        return facts
    facts = facts.sort_values("Row Order")
    adult = facts["Daily Value Target Group"].fillna("").str.contains("adult", case=False)

    servings = facts["Serving Size"].fillna("")
    if servings.nunique() > 1:
        adult_rows = adult.groupby(servings, sort=False).sum()
        facts = facts[servings == adult_rows.idxmax()]
        adult = adult[facts.index]

    names = facts["Ingredient"].map(_normalize)
    run = names.ne(names.shift()).cumsum()
    column = facts.groupby(run).cumcount()
    run_length = column.groupby(run).transform("max") + 1
    repeated = run_length > 1
    if not repeated.any():
        return facts

    adult_rows = adult[repeated].groupby(column[repeated]).sum()
    chosen = int(adult_rows.idxmax()) if adult_rows.max() > 0 else 0
    # A shorter run (an ingredient only some columns list) keeps its last row
    keep = ~repeated | (column == run_length.clip(upper=chosen + 1) - 1)
    return facts[keep]


def _is_generic(name, nutrient):
    """True for a label row naming the nutrient itself ("Vitamin A"), not a form."""
    nutrient = nutrient.lower()
    return name in (nutrient, f"vitamin {nutrient}")


def product_doses(facts, aliases):
    """
    One row per Supplement Facts row that links to a compound with an adult
    reference: the amount per serving in the compound's unit, or why it
    isn't counted. Where a label gives a compound's total ("Vitamin A") and
    also its forms ("Beta-Carotene") only the total is counted.
    """
    facts = choose_label_column(facts)
    rows = []
    columns = ["Ingredient", "Amount Per Serving", "Amount Per Serving Unit"]
    for ingredient, amount, unit in facts[columns].itertuples(index=False, name=None):
        name = _normalize(ingredient)
        compound = aliases.get(name)
        if compound is None:
            continue
        group = STACK_GROUPS.get(compound, compound)
        if adult_reference(group) is None:
            continue
        label = " ".join(str(v).strip() for v in (amount, unit) if isinstance(v, str))
        row = {"nutrient": group, "compound": compound, "ingredient": ingredient,
               "label_amount": label, "dose": None, "ul_dose": None,
               "estimate": False, "not_counted": "", "generic": _is_generic(name, group)}
        dose = normalize_amount(amount, unit, compound, ingredient)
        if compound in SALT_WEIGHT and SALT_NAME.search(ingredient):
            row["not_counted"] = "Weight of the whole salt"
        elif dose is None:
            row["not_counted"] = "No amount on the label"
        elif dose.unit != target_unit(group):
            row["not_counted"] = f"Unit doesn't convert ({dose.unit})"
        elif looks_like_unit_error(compound, dose.value):
            row["not_counted"] = "Likely a unit error on the label"
        else:
            row["dose"] = dose.value
            beta_carotene = compound == "Vitamin A" and is_beta_carotene(ingredient)
            row["ul_dose"] = 0.0 if beta_carotene else dose.value
            row["estimate"] = bool(dose.note)
        rows.append(row)

    doses = pd.DataFrame(rows, columns=["nutrient", "compound", "ingredient", "label_amount",
                                        "dose", "ul_dose", "estimate", "not_counted", "generic"])
    if doses.empty:
        return doses
    # A form listed under the compound's total is already in that total
    has_total = doses.groupby("nutrient")["generic"].transform(
        lambda g: g.any() and not g.all())
    within_total = has_total & ~doses["generic"] & doses["not_counted"].eq("")
    doses.loc[within_total, "not_counted"] = "Part of the total above it"
    doses.loc[within_total, ["dose", "ul_dose"]] = None
    return doses


def stack_totals(products):
    """
    products: [(product name, servings per day, product_doses frame)].
    Returns (totals, not_counted): totals has one row per nutrient with the
    daily total, its unit, % of adult RDA, upper-limit status and where it
    comes from; not_counted lists the label rows left out and why.
    """
    counted, skipped = [], []
    for product, servings, doses in products:
        for r in doses.itertuples(index=False):
            if r.not_counted:
                skipped.append({"Product": product, "Ingredient": r.ingredient,
                                "Label amount": r.label_amount, "Why": r.not_counted})
            else:
                counted.append({"nutrient": r.nutrient, "product": product,
                                "servings": servings, "dose": r.dose * servings,
                                "ul_dose": r.ul_dose * servings, "estimate": r.estimate})

    not_counted = pd.DataFrame(skipped, columns=["Product", "Ingredient", "Label amount", "Why"])
    if not counted:
        return pd.DataFrame(), not_counted

    counted = pd.DataFrame(counted)
    totals = []
    for nutrient, group in counted.groupby("nutrient", sort=True):
        unit = target_unit(nutrient)
        total, ul_total = group["dose"].sum(), group["ul_dose"].sum()
        comparison = compare_amount(nutrient, total, ul_total, group["estimate"].any())
        by_product = group.groupby("product", sort=False)["dose"].sum()
        sources = "; ".join(f"{p}: {_fmt(v)} {unit}" for p, v in by_product.items())
        totals.append({
            "Nutrient": nutrient,
            "Total per day": f"{_fmt(total)} {unit}",
            "% of adult RDA": comparison.percent_of_rda,
            "Upper limit": comparison.upper_limit,
            "From": sources,
        })
    return pd.DataFrame(totals), not_counted


def _fmt(x):
    return f"{x:,.0f}" if x >= 10 else f"{x:,.2g}"

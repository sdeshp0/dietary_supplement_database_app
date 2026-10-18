"""
Compares a label's amount per serving with the NIH ODS recommended amount
(RDA or AI) and tolerable upper intake level (UL) for adults 19 and older.

Where the ODS tables give different values by sex or age within adulthood,
the comparison shows the range (for example calcium's RDA of 1,000–1,200 mg).
Pregnancy and breastfeeding rows are left out.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

import pandas as pd

from utils.units import (FOLIC_ACID_DFE_FACTOR, Amount, is_beta_carotene, normalize_amount,
                         target_unit)

METADATA_CSV = Path(__file__).parents[1] / "data" / "compound_metadata.csv"
CEILINGS_CSV = Path(__file__).parents[1] / "data" / "dose_ceilings.csv"

# The ODS "recommended amount" for omega-3 is for ALA, which says nothing
# about fish oil, EPA or DHA, so those compounds aren't compared
NO_COMPARISON = {"Omega-3", "Omega-3 (DHA)"}

MINERALS = {
    "Calcium", "Magnesium", "Zinc", "Iron", "Copper", "Manganese", "Chromium",
    "Selenium", "Potassium", "Iodine", "Boron", "Phosphorus", "Molybdenum",
}
# A mineral (or caffeine) named as a salt ("Magnesium Citrate 500 mg",
# "Caffeine Citrate") often gives the weight of the whole salt, not the
# nutrient, so it isn't compared
SALT_WEIGHT = MINERALS | {"Caffeine"}
SALT_NAME = re.compile(
    r"\b(citrate|oxide|glycinate|bisglycinate|malate|carbonate|gluconate|picolinate|"
    r"aspartate|chloride|sulfate|sulphate|chelate|orotate|taurate|lactate|hydroxide|"
    r"succinate|fumarate|phosphate|glycerophosphate|iodide|selenite|selenate|"
    r"methionine|bicarbonate|nicotinate|polynicotinate|acetate|molybdate)\b",
    re.IGNORECASE,
)

# An amount this many times the highest adult UL, or this many times the 99th
# percentile of DSLD labels (data/dose_ceilings.csv), is almost certainly a
# unit mistake on the label (vitamin D entered as 1,000 mg instead of IU)
IMPLAUSIBLE_TIMES_UL = 100
IMPLAUSIBLE_TIMES_P99 = 5

# Limits from other official sources, for compounds the ODS has no fact sheet
# for. FDA: "For healthy adults, the FDA has cited 400 milligrams a day ... as
# an amount not generally associated with dangerous, negative effects."
# https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much
OTHER_LIMITS = {
    "Caffeine": (400, "FDA: up to 400 mg a day for most healthy adults"),
}

AMOUNT = re.compile(r"([\d,]*\.?\d+)\s*(?:[–-]\s*([\d,]*\.?\d+))?\s*(mcg|mg|g)\b")


class Reference(NamedTuple):
    unit: str
    rda: Optional[tuple]  # (lowest, highest) across adult rows
    ul: Optional[tuple]
    ul_note: Optional[str] = None


class Comparison(NamedTuple):
    percent_of_rda: str  # "83–100%" or ""
    upper_limit: str     # status against the UL, or ""


def _is_adult(life_stage):
    stage = str(life_stage).lower()
    if any(w in stage for w in ("pregnan", "breastfeed", "lactat", "teen", "child",
                                "infant", "birth", "boys", "girls")):
        return False
    if re.search(r"\b(adults?|men|women|males?|females?)\b", stage):
        return True
    # "19+ years", "19 years and older", "51–70 years"
    return bool(re.search(r"\b(19|[2-9]\d)\b", stage)) and "14" not in stage


def _parse(text, unit):
    """(low, high) of an amount like "1,000 mg" or "400–420 mg" in unit, or None."""
    match = AMOUNT.search(str(text))
    if not match:
        return None
    low, high, found_unit = match.groups()
    low = float(low.replace(",", ""))
    high = float(high.replace(",", "")) if high else low
    factor = {"mcg": 1, "mg": 1000, "g": 1e6}
    scale = factor[found_unit] / factor[unit.split()[0]]
    return low * scale, high * scale


def _adult_range(table, value_prefix, unit):
    values = []
    for entry in table:
        stage = entry.get("Life Stage", entry.get("Ages"))
        if not _is_adult(stage):
            continue
        for key, value in entry.items():
            if key.startswith(value_prefix) and isinstance(value, str):
                parsed = _parse(value, unit)
                if parsed:
                    values.extend(parsed)
    return (min(values), max(values)) if values else None


@lru_cache(maxsize=1)
def _metadata():
    return pd.read_csv(METADATA_CSV).set_index("compound")


@lru_cache(maxsize=1)
def _ceilings():
    if not CEILINGS_CSV.exists():
        return {}
    ceilings = pd.read_csv(CEILINGS_CSV)
    return dict(zip(ceilings["compound"], ceilings["p99"]))


def looks_like_unit_error(compound, dose):
    """True when an amount (in the compound's unit) is far beyond any real label."""
    reference = adult_reference(compound)
    if reference and reference.ul and dose > IMPLAUSIBLE_TIMES_UL * reference.ul[1]:
        return True
    p99 = _ceilings().get(compound)
    return bool(p99) and dose > IMPLAUSIBLE_TIMES_P99 * p99


@lru_cache(maxsize=None)
def adult_reference(compound):
    """The compound's adult RDA and UL ranges in its target unit, or None."""
    if compound in OTHER_LIMITS:
        limit, note = OTHER_LIMITS[compound]
        return Reference(target_unit(compound), None, (limit, limit), note)
    if compound in NO_COMPARISON or compound not in _metadata().index:
        return None
    row = _metadata().loc[compound]
    unit = target_unit(compound)

    def table(col):
        text = row.get(col)
        return json.loads(text) if isinstance(text, str) and text.strip() else []

    rda = _adult_range(table("rda_json"), "Recommended Amount", unit)
    ul = _adult_range(table("ul_json"), "Upper Limit", unit)
    ul_note = None
    if ul and compound == "Folate":
        # The folate UL is for folic acid; labels are compared in mcg DFE
        ul = (ul[0] * FOLIC_ACID_DFE_FACTOR, ul[1] * FOLIC_ACID_DFE_FACTOR)
        ul_note = "the upper limit applies to folic acid"
    if not rda and not ul:
        return None
    return Reference(unit, rda, ul, ul_note)


def _format_range(low, high, suffix=""):
    def fmt(x):
        return f"{x:,.0f}" if x >= 10 else f"{x:,.2g}"
    return f"{fmt(low)}{suffix}" if round(low) == round(high) else f"{fmt(low)}–{fmt(high)}{suffix}"


def compare_dose(compound, ingredient, amount, unit):
    """
    How the label amount per serving compares with the adult RDA and UL,
    as a Comparison of display strings, or None when it can't be compared.
    """
    if not isinstance(compound, str):
        return None
    reference = adult_reference(compound)
    if reference is None:
        return None
    if compound in SALT_WEIGHT and SALT_NAME.search(ingredient or ""):
        return Comparison("", "Not compared (salt weight)")
    dose = normalize_amount(amount, unit, compound, ingredient)
    if not isinstance(dose, Amount) or dose.unit != reference.unit:
        return None

    if looks_like_unit_error(compound, dose.value):
        return Comparison("", "Check label (unit error?)")
    # The vitamin A upper limit is for preformed vitamin A (retinol), not
    # beta-carotene
    counts_toward_ul = not (compound == "Vitamin A" and is_beta_carotene(ingredient))
    return compare_amount(compound, dose.value, dose.value if counts_toward_ul else 0,
                          estimate=bool(dose.note))


def compare_amount(compound, amount, ul_amount=None, estimate=False):
    """
    How an amount in the compound's target unit compares with the adult RDA
    and UL. ul_amount is the part of it the upper limit applies to (all of
    it unless given). Returns None when the compound has no reference.
    """
    reference = adult_reference(compound)
    if reference is None:
        return None
    ul_amount = amount if ul_amount is None else ul_amount

    percent = ""
    if reference.rda and reference.rda[0] > 0:
        low, high = reference.rda
        percent = _format_range(100 * amount / high, 100 * amount / low, "%")

    status = ""
    if reference.ul:
        low, high = reference.ul
        if ul_amount > high:
            status = "Over the limit"
        elif ul_amount > low:
            status = "Over for some adults"
    if estimate:
        # The label didn't settle the form, so the conversion is an estimate
        percent = f"{percent} (estimate)" if percent else percent
        status = f"{status} (estimate)" if status else status
    return Comparison(percent, status)


def comparable_dose(compound, ingredient, amount, unit):
    """
    The label amount in the compound's target unit, for sorting products by
    dose, or None when it isn't comparable: a mineral named as a salt, a unit
    that doesn't convert (CFU, mL), or an amount that looks like a unit error.
    """
    if not isinstance(compound, str):
        return None
    if compound in SALT_WEIGHT and SALT_NAME.search(ingredient or ""):
        return None
    dose = normalize_amount(amount, unit, compound, ingredient)
    if dose is None or dose.unit != target_unit(compound):
        return None
    if looks_like_unit_error(compound, dose.value):
        return None
    return dose

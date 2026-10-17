"""
Converts Supplement Facts amounts to one unit per compound, so a label's dose
can be compared with the NIH ODS recommended amounts and upper limits
(stage 4) and with other products (stage 5).

Conversion factors are the ones the NIH Office of Dietary Supplements gives
in its fact sheets.
"""

import re
from typing import NamedTuple, Optional

# The unit each compound is compared in: the unit of its ODS recommended
# amount. Compounds not listed are compared in mg.
TARGET_UNITS = {
    "Vitamin A": "mcg RAE",
    "Folate": "mcg DFE",
    "Vitamin D": "mcg",
    "B12": "mcg",
    "Biotin": "mcg",
    "B7": "mcg",
    "Chromium": "mcg",
    "Copper": "mcg",
    "Iodine": "mcg",
    "Selenium": "mcg",
    "Vitamin K2": "mcg",
    "Omega-3": "g",
    "Omega-3 (DHA)": "g",
    "Fiber": "g",
    "Soluble fiber": "g",
}

# Mass units as DSLD writes them, in micrograms
MASS_UNITS = {
    "ng": 0.001,
    "mcg": 1.0,
    "ug": 1.0,
    "mg": 1000.0,
    "g": 1e6,
    "gram(s)": 1e6,
    "grams": 1e6,
}

# Mass units with a nutrient basis ("mcg DFE"). For preformed niacin,
# alpha-tocopherol and retinol, mg NE, mg alpha-TE and mcg RE equal plain
# mass, so only DFE and RAE are kept as a basis.
BASIS_UNIT = re.compile(r"^(ng|mcg|ug|mg|g)\s+(dfe|rae|re|ne|\{alpha\}-te)$")

# IU conversions from the ODS fact sheets
VITAMIN_D_MCG_PER_IU = 0.025
VITAMIN_A_RAE_MCG_PER_IU = 0.3       # retinol and its esters
VITAMIN_E_MG_PER_IU_NATURAL = 0.67   # d-alpha-tocopherol
VITAMIN_E_MG_PER_IU_SYNTHETIC = 0.45 # dl-alpha-tocopherol
# A label's folic acid counts 1.7 times in mcg DFE
FOLIC_ACID_DFE_FACTOR = 1.7


class Amount(NamedTuple):
    value: float
    unit: str
    # Set when the conversion rests on an assumption the label doesn't settle
    note: Optional[str] = None


def target_unit(compound):
    return TARGET_UNITS.get(compound, "mg")


def parse_amount(text):
    """The label amount as a number, or None for blanks and "<1"-style amounts."""
    if text is None:
        return None
    try:
        value = float(str(text).replace(",", "").strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def _iu_to_target(value, compound, ingredient):
    name = (ingredient or "").lower()
    if compound == "Vitamin D":
        return Amount(value * VITAMIN_D_MCG_PER_IU, "mcg")
    if compound == "Vitamin A":
        return Amount(value * VITAMIN_A_RAE_MCG_PER_IU, "mcg RAE",
                      None if "retin" in name else "assumes retinol, not beta-carotene")
    if compound == "Vitamin E":
        if re.search(r"\bdl-", name):
            return Amount(value * VITAMIN_E_MG_PER_IU_SYNTHETIC, "mg")
        if re.search(r"\bd-|natural", name):
            return Amount(value * VITAMIN_E_MG_PER_IU_NATURAL, "mg")
        # The label doesn't say which form; the natural factor gives the
        # higher amount, so an upper limit is never understated
        return Amount(value * VITAMIN_E_MG_PER_IU_NATURAL, "mg",
                      "form not stated; assumes natural vitamin E")
    return None


def normalize_amount(amount, unit, compound, ingredient=""):
    """
    The label amount in the compound's target unit, as an Amount.

    Units that can't be converted to it (CFU, enzyme activity units, mL,
    a %) come back unchanged. Returns None when there is no usable amount.
    """
    value = parse_amount(amount)
    if value is None or not isinstance(unit, str) or not unit.strip():
        return None
    raw_unit = unit.strip()
    key = raw_unit.lower()
    target = target_unit(compound)

    if key == "iu":
        return _iu_to_target(value, compound, ingredient) or Amount(value, raw_unit)

    basis = None
    match = BASIS_UNIT.match(key)
    if match:
        key, basis = match.group(1), match.group(2)
        basis = basis if basis in ("dfe", "rae") else None
    if key not in MASS_UNITS:
        return Amount(value, raw_unit)

    mcg = value * MASS_UNITS[key]
    note = None
    if target == "mcg DFE" and basis != "dfe":
        # Older labels give folate as mcg of folic acid (or methylfolate,
        # which labels convert with the same factor)
        mcg *= FOLIC_ACID_DFE_FACTOR
        if "folic" not in (ingredient or "").lower():
            note = "assumes the amount is folic acid"

    target_mass = target.split()[0]
    return Amount(mcg / MASS_UNITS[target_mass], target, note)

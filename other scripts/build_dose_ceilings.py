"""
Writes data/dose_ceilings.csv: for each compound, the 99th percentile of the
amounts per serving on DSLD labels, in the compound's unit (utils/units.py).

The app treats an amount more than 5 times this as a likely unit mistake on
the label (vitamin C entered as 90 g instead of 90 mg), so it doesn't top
"highest dose" lists or trigger upper-limit warnings. Rerun after changing
data/ingredient_aliases.csv or rebuilding the database.

Usage:
    python "other scripts/build_dose_ceilings.py"
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from utils.units import normalize_amount, target_unit  # noqa: E402

DATA_DIR = Path(__file__).parents[1] / "data"


def main():
    aliases = pd.read_csv(DATA_DIR / "ingredient_aliases.csv")
    con = duckdb.connect(str(DATA_DIR / "dsld.duckdb"), read_only=True)
    con.register("aliases", aliases)
    rows = con.execute("""
        SELECT a.compound, f."Ingredient", f."Amount Per Serving", f."Amount Per Serving Unit"
        FROM supplement_facts f
        JOIN aliases a
          ON a.dsld_name = lower(trim(regexp_replace(f."Ingredient", '\\s+', ' ', 'g')))
    """).fetchall()

    doses = {}
    for compound, ingredient, amount, unit in rows:
        dose = normalize_amount(amount, unit, compound, ingredient)
        if dose and dose.unit == target_unit(compound):
            doses.setdefault(compound, []).append(dose.value)

    ceilings = pd.DataFrame(
        [(c, target_unit(c), len(v), pd.Series(v).quantile(0.99)) for c, v in sorted(doses.items())],
        columns=["compound", "unit", "label_rows", "p99"],
    )
    ceilings["p99"] = ceilings["p99"].round(4)
    ceilings.to_csv(DATA_DIR / "dose_ceilings.csv", index=False, lineterminator="\n")
    print(f"Wrote dose_ceilings.csv for {len(ceilings)} compounds")


if __name__ == "__main__":
    main()

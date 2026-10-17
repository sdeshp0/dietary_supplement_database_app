"""
Reports how much of the DSLD label data data/ingredient_aliases.csv maps to
an ontology compound, and lists the most common ingredient names it misses.

Usage:
    python "other scripts/ingredient_mapping_report.py" [number of names to list]
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from utils.units import normalize_amount, target_unit  # noqa: E402

DATA_DIR = Path(__file__).parents[1] / "data"


def main(top_n=50):
    aliases = pd.read_csv(DATA_DIR / "ingredient_aliases.csv")
    ontology = set(pd.read_csv(DATA_DIR / "supplement_ontology.csv")["compound"])

    unknown = sorted(set(aliases["compound"]) - ontology)
    if unknown:
        sys.exit(f"Aliases point at compounds missing from the ontology: {unknown}")
    duplicated = aliases[aliases["dsld_name"].duplicated(keep=False)]
    if not duplicated.empty:
        sys.exit(f"Names mapped more than once:\n{duplicated}")

    con = duckdb.connect(str(DATA_DIR / "dsld.duckdb"), read_only=True)
    con.register("aliases", aliases)
    names = con.execute("""
        SELECT lower(trim(regexp_replace(f."Ingredient", '\\s+', ' ', 'g'))) AS name,
               count(*) AS label_rows,
               count(DISTINCT f."DSLD ID") AS products,
               any_value(a.compound) AS compound
        FROM supplement_facts f
        LEFT JOIN aliases a
          ON a.dsld_name = lower(trim(regexp_replace(f."Ingredient", '\\s+', ' ', 'g')))
        WHERE f."Ingredient" IS NOT NULL
        GROUP BY 1
    """).df()

    mapped = names["compound"].notna()
    print(f"Mapped {mapped.sum():,} of {len(names):,} distinct ingredient names, "
          f"covering {names.loc[mapped, 'label_rows'].sum() / names['label_rows'].sum():.1%} "
          "of Supplement Facts rows.")
    print(f"Compounds with at least one alias: {aliases['compound'].nunique()} of {len(ontology)}")

    # How many linked rows have an amount in the unit their compound is compared in
    amounts = con.execute("""
        SELECT a.compound, f."Ingredient", f."Amount Per Serving", f."Amount Per Serving Unit"
        FROM supplement_facts f
        JOIN aliases a
          ON a.dsld_name = lower(trim(regexp_replace(f."Ingredient", '\\s+', ' ', 'g')))
    """).fetchall()
    converted = [normalize_amount(amt, unit, compound, ingredient)
                 for compound, ingredient, amt, unit in amounts]
    with_amount = [c for c in converted if c]
    in_target = sum(c.unit == target_unit(compound)
                    for c, (compound, *_) in zip(converted, amounts) if c)
    print(f"Linked rows with an amount: {len(with_amount):,}; "
          f"{in_target / max(len(with_amount), 1):.1%} of them convert to the compound's unit.")

    print(f"\nMost common unmapped names (top {top_n} by product count):")
    missing = names[~mapped].sort_values("products", ascending=False).head(top_n)
    for r in missing.itertuples():
        print(f"  {r.products:>7,}  {r.name}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 50)

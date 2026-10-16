"""
Suggests new rows for data/ingredient_aliases.csv from DSLD ingredient names
that are variants of names it already maps: salts and chelates
("magnesium citrate"), forms ("creatine hcl"), descriptors ("organic turmeric",
"holy basil leaf extract") and probiotic strains.

Suggestions go to data/ingredient_alias_candidates.csv for review:
  approve = yes  the rule is safe; the row is added on --apply
  approve = (blank)  needs a person, for example "magnesium ascorbate"
                    is both Magnesium and Vitamin C
Set approve to yes or no (and fix suggested_compound if needed), then run
with --apply to add the approved rows to the aliases file. Decisions already
in the candidates file are kept when it is regenerated.

Usage:
    python "other scripts/suggest_ingredient_aliases.py" [--min-products N]
    python "other scripts/suggest_ingredient_aliases.py" --apply
"""

import argparse
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).parents[1] / "data"
ALIASES_CSV = DATA_DIR / "ingredient_aliases.csv"
CANDIDATES_CSV = DATA_DIR / "ingredient_alias_candidates.csv"
ONTOLOGY_CSV = DATA_DIR / "supplement_ontology.csv"

# ---------------------------------------------------------
# RULES
# ---------------------------------------------------------
PROBIOTIC = re.compile(
    r"^(lactobacillus|bifidobacterium|bacillus coagulans|bacillus subtilis|"
    r"bacillus clausii|bacillus licheniformis|saccharomyces boulardii|"
    r"streptococcus thermophilus|streptococcus salivarius|lactococcus|"
    r"lacticaseibacillus|lactiplantibacillus|limosilactobacillus|ligilactobacillus|"
    r"latilactobacillus|levilactobacillus|enterococcus faecium|pediococcus|"
    r"leuconostoc|[lb]\. ?[a-z])"
)

# Additives that happen to start with a mineral name; never mapped
# and names that only share a word with a compound ("silicon dioxide", "copper chlorophyllin")
EXCIPIENT = re.compile(
    r"stearate|sorbate|benzoate|edta|caseinate|silicate|alginate|dioxide|chlorophyllin"
)

# Words that describe the form of an ingredient rather than what it is.
# Removed before matching against the existing aliases.
DESCRIPTOR_WORDS = {
    "organic", "natural", "pure", "micronized", "instantized", "extract",
    "standardized", "supercritical", "hydroethanolic", "liquid", "powder",
    "powdered", "complex", "concentrate", "concentrated", "purified", "dry",
    "dried", "raw", "whole", "fermented", "hydrolyzed", "hydrolysate", "aged",
    "odorless", "deodorized", "odor-controlled", "decaffeinated", "elemental",
    "base", "brand", "(tm)", "wild", "bovine", "marine", "trans", "phytosome",
    # plant parts
    "root", "leaf", "seed", "fruit", "bark", "rhizome", "herb", "bulb", "clove",
    "mushroom", "fruiting", "body",
    # enzyme sources
    "fungal", "bacterial", "neutral", "alkaline", "stable",
    # trademarked forms of a compound
    "sensoril", "ksm-66", "meriva", "bcm-95", "resvida", "theapure", "kaneka",
    "creapure", "pharmapure", "q-sorb", "megasorb", "longvida", "curcuwin",
    "bioresponse", "verisol", "optimsm", "betapower", "bioenergy",
}
# Activity grades and numbering, as in "protease 4.5" or "protease ii"
GRADE = re.compile(r"^([\d.]+|i|ii|iii|iv)$")

# Salt, chelate and hydrate words. "magnesium citrate" is Magnesium.
SALT_WORDS = {
    "citrate", "oxide", "glycinate", "bisglycinate", "diglycinate", "malate",
    "carbonate", "bicarbonate", "gluconate", "picolinate",
    "aspartate", "chloride", "sulfate", "sulphate", "chelate",
    "amino", "acid", "orotate", "taurate", "lactate", "hydroxide", "succinate",
    "fumarate", "glutarate", "hcl", "hydrochloride", "nitrate",
    "anhydrous", "monohydrate", "dihydrate", "pentahydrate", "heptahydrate",
    "tartrate", "selenate", "selenite", "acetate", "arginate",
    "mono-l-methionine", "methionine", "l-methionine", "pidolate", "lysinate",
}

# Salt words that are themselves an ontology compound. A name with one of
# these always goes to review: "calcium ascorbate" is Calcium and Vitamin C.
COMPOUND_ANIONS = {
    "ascorbate": "Vitamin C",
    "folinate": "Folate",
    "iodide": "Iodine",
    "iodate": "Iodine",
    "phosphate": "Phosphorus",
    "glycerophosphate": "Phosphorus",
    "pantothenate": "B5",
    "hexanicotinate": "Niacin",
    "hexaniacinate": "Niacin",
    "nicotinate": "Niacin",
    "polynicotinate": "Niacin",
}
# In these combinations the anion is what the label is about
# ("potassium iodide" is listed as the iodine source), so it is suggested first
PREFERRED_ANIONS = {"Vitamin C", "Folate", "Iodine"}

# Combinations that are all one compound family
FAMILIES = {frozenset({"Omega-3", "Omega-3 (DHA)"}): "Omega-3"}

# Mineral salts whose name doesn't start with the mineral
MINERAL_STEMS = {
    "ferrous": "iron", "ferric": "iron", "cupric": "copper",
    "sodium selenite": "selenium", "sodium selenate": "selenium",
    "l-selenomethionine": "selenium", "selenomethionine": "selenium",
}


def clean(name):
    """The name with parentheticals, trademark marks and ';' removed."""
    # Only parentheticals after a space, so "(6s)-5-methyltetrahydrofolate" stays whole
    core = re.sub(r"\s+\([^()]*\)", " ", name)
    core = re.sub(r"[®™]", "", core).replace(";", " ").strip()
    core = re.sub(r"^r-(?=alpha)", "", core)
    for stem, mineral in MINERAL_STEMS.items():
        if core.startswith(stem + " ") or core == stem:
            core = mineral + core[len(stem):]
    return " ".join(core.split())


def suggest(name, alias_map, alias_pattern):
    """(compound, rule, note, approve) for one unmapped name, or None."""
    if PROBIOTIC.match(name):
        return "Probiotics", "probiotic strain", "", "yes"
    if re.match(r"^(s\. ?cerevisiae|saccharomyces cerevisiae)", name):
        return "Probiotics", "probiotic strain", "may be nutritional or brewer's yeast", ""
    if EXCIPIENT.search(name):
        return None

    core = clean(name)
    words = core.split()
    kept = [w for w in words
            if w not in DESCRIPTOR_WORDS | SALT_WORDS | set(COMPOUND_ANIONS) and not GRADE.match(w)]
    salts = [w for w in words if w in SALT_WORDS]
    anions = [COMPOUND_ANIONS[w] for w in words if w in COMPOUND_ANIONS]
    base = " ".join(kept)

    if base in alias_map:
        compound = alias_map[base]
        if anions:
            found = [compound] + [a for a in anions if a != compound]
            return combination(found)
        rule = "salt or form" if salts else "descriptor"
        return compound, rule, "", "yes"

    # Contains a mapped name: "magnesium creatine chelate", "zinc l-carnosine"
    found = []
    for m in alias_pattern.finditer(core):
        compound = alias_map[m.group(0)]
        if compound not in found:
            found.append(compound)
    for compound in anions:
        if compound not in found:
            found.append(compound)
    if len(found) > 1:
        return combination(found)
    if found:
        return found[0], "contains", "contains a mapped name", ""
    return None


def combination(found):
    """Suggestion for a name that holds more than one compound."""
    if len(found) == 1:
        return found[0], "salt or form", "", "yes"
    family = FAMILIES.get(frozenset(found))
    if family:
        return family, "combination", "one compound family", "yes"
    found = sorted(found, key=lambda c: c not in PREFERRED_ANIONS)
    return found[0], "combination", "also " + ", ".join(found[1:]), ""


# ---------------------------------------------------------
# DATA
# ---------------------------------------------------------
def load_aliases():
    return pd.read_csv(ALIASES_CSV, dtype=str)


def unmapped_names(aliases, min_products):
    con = duckdb.connect(str(DATA_DIR / "dsld.duckdb"), read_only=True)
    names = con.execute("""
        SELECT lower(trim(regexp_replace("Ingredient", '\\s+', ' ', 'g'))) AS dsld_name,
               count(DISTINCT "DSLD ID") AS products
        FROM supplement_facts
        WHERE "Ingredient" IS NOT NULL
        GROUP BY 1
        HAVING count(DISTINCT "DSLD ID") >= ?
    """, [min_products]).df()
    con.close()
    return names[~names["dsld_name"].isin(set(aliases["dsld_name"]))]


def generate(min_products):
    aliases = load_aliases()
    alias_map = dict(zip(aliases["dsld_name"], aliases["compound"]))
    # Longest names first, so "magnesium l-threonate" wins over "magnesium"
    alternatives = sorted(alias_map, key=len, reverse=True)
    alias_pattern = re.compile(
        r"(?<![\w-])(" + "|".join(re.escape(a) for a in alternatives) + r")(?![\w-])"
    )

    rows = []
    for r in unmapped_names(aliases, min_products).itertuples():
        s = suggest(r.dsld_name, alias_map, alias_pattern)
        if s:
            rows.append((r.dsld_name, r.products, *s))
    candidates = pd.DataFrame(
        rows, columns=["dsld_name", "products", "suggested_compound", "rule", "note", "approve"]
    )

    # Keep decisions made in an earlier copy of the file
    if CANDIDATES_CSV.exists():
        previous = pd.read_csv(CANDIDATES_CSV, dtype=str, keep_default_na=False)
        previous = previous.set_index("dsld_name")[["suggested_compound", "approve"]]
        known = candidates["dsld_name"].isin(previous.index)
        for col in ["suggested_compound", "approve"]:
            candidates.loc[known, col] = candidates.loc[known, "dsld_name"].map(previous[col])

    # Rows needing a decision first, then the rest; most common names first
    candidates["undecided"] = candidates["approve"] == ""
    candidates = candidates.sort_values(
        ["undecided", "products"], ascending=[False, False]
    ).drop(columns="undecided")
    candidates.to_csv(CANDIDATES_CSV, index=False, lineterminator="\n")

    print(f"Wrote {len(candidates)} suggestions to {CANDIDATES_CSV.name}")
    print(candidates.groupby(["rule", "approve"], dropna=False)["products"]
          .agg(["count", "sum"]).rename(columns={"count": "names", "sum": "products"}))


def apply():
    aliases = load_aliases()
    ontology = set(pd.read_csv(ONTOLOGY_CSV)["compound"])
    candidates = pd.read_csv(CANDIDATES_CSV, dtype=str, keep_default_na=False)
    approved = candidates[candidates["approve"].str.strip().str.lower() == "yes"]

    unknown = sorted(set(approved["suggested_compound"]) - ontology)
    if unknown:
        sys.exit(f"Approved rows name compounds missing from the ontology: {unknown}")

    new = approved.loc[~approved["dsld_name"].isin(set(aliases["dsld_name"])),
                       ["dsld_name", "suggested_compound"]]
    new = new.rename(columns={"suggested_compound": "compound"})
    merged = pd.concat([aliases, new], ignore_index=True)
    merged = merged.sort_values(["compound", "dsld_name"], key=lambda s: s.str.lower())
    merged.to_csv(ALIASES_CSV, index=False, lineterminator="\n")

    # Applied rows are mapped now; the file keeps only rows still to decide or rejected
    candidates[~candidates["dsld_name"].isin(set(merged["dsld_name"]))].to_csv(
        CANDIDATES_CSV, index=False, lineterminator="\n"
    )
    print(f"Added {len(new)} aliases to {ALIASES_CSV.name} ({len(merged)} in total)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="add the approved candidates to the aliases file")
    parser.add_argument("--min-products", type=int, default=10,
                        help="only suggest names on at least this many products")
    args = parser.parse_args()
    apply() if args.apply else generate(args.min_products)

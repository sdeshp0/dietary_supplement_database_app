"""
Checks data/ingredient_aliases.csv against FDA's Global Substance Registration
System (GSRS, https://gsrs.ncats.nih.gov), the registry behind FDA's UNII codes.

GSRS records each substance's active moiety, the part that does the work:
magnesium citrate's is magnesium. For every alias that GSRS knows as a chemical,
the script compares its active moieties with those of the compound's most common
names. An alias whose moieties share nothing with its compound's is flagged.

Names on the review list (blank rows in data/ingredient_alias_candidates.csv)
are checked too, and the report lists which compounds each one matches, which
helps decide names like "calcium ascorbate".

Botanicals and probiotic strains are not chemicals in GSRS, so they are skipped.

Writes data/ingredient_alias_gsrs_check.csv. GSRS replies are cached in
data/.gsrs_cache.json, so a second run only looks up new names.

Usage:
    python "other scripts/check_aliases_gsrs.py"
"""

import json
import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

DATA_DIR = Path(__file__).parents[1] / "data"
ALIASES_CSV = DATA_DIR / "ingredient_aliases.csv"
CANDIDATES_CSV = DATA_DIR / "ingredient_alias_candidates.csv"
REPORT_CSV = DATA_DIR / "ingredient_alias_gsrs_check.csv"
CACHE_JSON = DATA_DIR / ".gsrs_cache.json"

GSRS_API = "https://gsrs.ncats.nih.gov/api/v1"
REQUEST_DELAY_S = 0.5
HEADERS = {
    "User-Agent": (
        "dietary-supplement-database-app/1.0 "
        "(+https://github.com/sdeshp0/dietary_supplement_database_app)"
    ),
    "Accept": "application/json",
}

# How many of a compound's most common names define what it should match
ANCHORS_PER_COMPOUND = 5

# Charge words GSRS adds to ions: "MAGNESIUM CATION" is the same moiety as "MAGNESIUM"
ION_WORDS = re.compile(r"\b(CATION|ANION|ION)\b|\([+-]?\d*[+-]?\)")
# Ion names for an element: "CHROMIC CATION" is chromium
ION_ELEMENTS = {
    "CHROMIC": "CHROMIUM", "CHROMOUS": "CHROMIUM", "CUPRIC": "COPPER", "CUPROUS": "COPPER",
    "FERRIC": "IRON", "FERROUS": "IRON", "MANGANOUS": "MANGANESE", "MANGANIC": "MANGANESE",
    "IODIDE": "IODINE", "SELENITE": "SELENIUM", "SELENATE": "SELENIUM",
}

session = requests.Session()
session.headers.update(HEADERS)


# ---------------------------------------------------------
# GSRS
# ---------------------------------------------------------
def get_json(path, params=None):
    time.sleep(REQUEST_DELAY_S)
    r = session.get(f"{GSRS_API}/{path}", params=params, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def gsrs_name(dsld_name):
    """DSLD writes ',' as ';' ("3;3'-diindolylmethane"); GSRS names are upper case."""
    return dsld_name.replace(";", ",").upper()


def lookup(dsld_name):
    """
    The GSRS substance named exactly dsld_name, as
    {name, unii, substance_class, moieties}, or {} when GSRS has none.
    """
    name = gsrs_name(dsld_name)
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    hits = get_json("substances/search", {"q": f'root_names_name:"^{escaped}$"', "top": 5})
    for hit in (hits or {}).get("content", []):
        full = get_json(f"substances({hit['uuid']})", {"view": "full"})
        if not full:
            continue
        # The search is fuzzy at the edges; keep only an exact name match
        if name not in {n.get("name", "").upper() for n in full.get("names", [])}:
            continue
        moieties = [
            rel["relatedSubstance"].get("refPname") or rel["relatedSubstance"].get("name")
            for rel in full.get("relationships", [])
            if "ACTIVE MOIETY" in rel.get("type", "").upper() and rel.get("relatedSubstance")
        ]
        return {
            "name": full.get("_name", ""),
            "unii": full.get("approvalID", ""),
            "substance_class": full.get("substanceClass", ""),
            # A substance with no active moiety listed is its own moiety
            "moieties": sorted({m for m in moieties if m}) or [full.get("_name", "")],
        }
    return {}


def normalize_moiety(moiety):
    moiety = " ".join(ION_WORDS.sub(" ", moiety.upper()).split())
    return ION_ELEMENTS.get(moiety, moiety)


def lookup_all(names):
    cache = json.loads(CACHE_JSON.read_text()) if CACHE_JSON.exists() else {}
    todo = [n for n in names if n not in cache]
    print(f"Looking up {len(todo)} names in GSRS ({len(names) - len(todo)} cached)")
    for i, name in enumerate(todo, 1):
        try:
            cache[name] = lookup(name)
        except requests.RequestException as e:
            print(f"  {name}: {e}")  # not cached, so the next run retries it
            continue
        if i % 50 == 0 or i == len(todo):
            CACHE_JSON.write_text(json.dumps(cache, indent=1, sort_keys=True))
            print(f"  {i}/{len(todo)}")
    return cache


# ---------------------------------------------------------
# CHECK
# ---------------------------------------------------------
def product_counts():
    con = duckdb.connect(str(DATA_DIR / "dsld.duckdb"), read_only=True)
    counts = con.execute("""
        SELECT lower(trim(regexp_replace("Ingredient", '\\s+', ' ', 'g'))) AS dsld_name,
               count(DISTINCT "DSLD ID") AS products
        FROM supplement_facts
        WHERE "Ingredient" IS NOT NULL
        GROUP BY 1
    """).df()
    con.close()
    return dict(zip(counts["dsld_name"], counts["products"]))


def is_chemical(record):
    return bool(record) and record["substance_class"].lower() in {"chemical", "mixture"}


def moiety_set(record):
    return {normalize_moiety(m) for m in record["moieties"]}


def lists_moiety(record):
    """False when GSRS gives no active moiety, so the substance stands for itself."""
    return record["moieties"] != [record["name"]]


def main():
    aliases = pd.read_csv(ALIASES_CSV, dtype=str)
    aliases = aliases[aliases["compound"] != "Probiotics"]
    candidates = pd.read_csv(CANDIDATES_CSV, dtype=str, keep_default_na=False)
    candidates = candidates[candidates["approve"] == ""]

    results = lookup_all(sorted(set(aliases["dsld_name"]) | set(candidates["dsld_name"])))
    products = product_counts()

    # Each compound's names that GSRS knows as a chemical with one moiety, most
    # common first. Salts with two moieties are left out: calcium pantothenate
    # would otherwise make every calcium salt match B5.
    aliases["products"] = aliases["dsld_name"].map(products).fillna(0)
    anchors = {}
    for compound, group in aliases.sort_values("products", ascending=False).groupby("compound"):
        anchors[compound] = [
            n for n in group["dsld_name"]
            if is_chemical(results.get(n)) and len(moiety_set(results[n])) == 1
        ]

    def reference(compound, dsld_name):
        """What the compound should match: the moieties of its most common
        names, leaving out the name being checked so it can't vouch for itself."""
        others = [n for n in anchors.get(compound, []) if n != dsld_name]
        return set().union(*(moiety_set(results[n]) for n in others[:ANCHORS_PER_COMPOUND]))

    def matches(record, dsld_name):
        found = moiety_set(record)
        return sorted(c for c in anchors if reference(c, dsld_name) & found)

    rows = []
    checks = [(r.dsld_name, r.compound, "alias") for r in aliases.itertuples()]
    checks += [(r.dsld_name, r.suggested_compound, "review list") for r in candidates.itertuples()]
    for dsld_name, compound, source in checks:
        record = results.get(dsld_name)
        if record is None:
            verdict = "lookup failed"
        elif not record:
            verdict = "not in GSRS"
        elif not is_chemical(record):
            verdict = "not a chemical"
        elif not reference(compound, dsld_name):
            verdict = "no reference for compound"
        elif reference(compound, dsld_name) & moiety_set(record):
            verdict = "agrees"
        elif not lists_moiety(record):
            verdict = "no active moiety in GSRS"
        else:
            verdict = "differs"
        rows.append({
            "dsld_name": dsld_name,
            "compound": compound,
            "source": source,
            "products": int(products.get(dsld_name, 0)),
            "verdict": verdict,
            "gsrs_name": (record or {}).get("name", ""),
            "unii": (record or {}).get("unii", ""),
            "active_moieties": "; ".join((record or {}).get("moieties", [])),
            "gsrs_matches": "; ".join(matches(record, dsld_name)) if is_chemical(record) else "",
        })

    # Aliases before the review list; disagreements first, then agreements, then the rest
    report = pd.DataFrame(rows)
    report["rank"] = report["verdict"].map({"differs": 0, "agrees": 1}).fillna(2)
    report = report.sort_values(["source", "rank", "products"], ascending=[True, True, False])
    report = report.drop(columns="rank")
    report.to_csv(REPORT_CSV, index=False, lineterminator="\n")

    print(f"\nWrote {REPORT_CSV.name}")
    print(report.groupby(["source", "verdict"]).size().to_string())
    differs = report[(report["source"] == "alias") & (report["verdict"] == "differs")]
    if not differs.empty:
        print("\nAliases GSRS disagrees with:")
        for r in differs.head(30).itertuples():
            print(f"  {r.dsld_name} -> {r.compound}: GSRS says {r.active_moieties}")


if __name__ == "__main__":
    main()

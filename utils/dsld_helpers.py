import re
from pathlib import Path
import duckdb
import pandas as pd
import requests
import streamlit as st
import fitz  # PyMuPDF

from utils.dose import comparable_dose, compare_dose
from utils.units import target_unit


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
DB_PATH = DATA_DIR / "dsld.duckdb"
ALIASES_CSV = DATA_DIR / "ingredient_aliases.csv"

FORM_COL = "Supplement Form [LanguaL]"
SEARCH_LIMIT = 50


# ---------------------------------------------------------
# DATABASE ACCESS
# ---------------------------------------------------------
def normalize_barcode(val):
    """
    Reduces a UPC/EAN to its digits without leading zeros, so that
    "0 74312 70640 0", "074312706400" and "74312706400" all match.
    The database stores the same form in "Bar Code (normalized)".
    """
    if not isinstance(val, str):
        return ""
    return re.sub(r"\D", "", val).lstrip("0")


def parse_dsld_id(val):
    """
    DSLD IDs are integers; returns None for anything else (e.g. a bad URL parameter).
    """
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


@st.cache_resource
def get_connection():
    """
    One read-only connection to data/dsld.duckdb, shared by all sessions.
    Queries read only the rows they need, so the app never holds the
    full DSLD tables in memory.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DSLD database not found at {DB_PATH}. "
            'Run python "other scripts/build_dsld_database.py" to build it.'
        )
    return duckdb.connect(
        str(DB_PATH), read_only=True, config={"memory_limit": "256MB", "threads": 2}
    )


def query(sql, params=None):
    """
    Runs a query and returns a DataFrame. Each call uses its own cursor,
    because Streamlit runs sessions on separate threads.
    """
    return get_connection().cursor().execute(sql, params or []).df()


def get_product(product_id):
    """
    The product's overview row as a Series, or None.
    """
    df = query('SELECT * FROM products WHERE "DSLD ID" = ?', [product_id])
    return None if df.empty else df.iloc[0]


def get_product_by_barcode(barcode_digits):
    """
    The first product whose normalized barcode matches, or None.
    """
    df = query(
        'SELECT * FROM products WHERE "Bar Code (normalized)" = ? ORDER BY "DSLD ID" LIMIT 1',
        [barcode_digits],
    )
    return None if df.empty else df.iloc[0]


@st.cache_data(show_spinner=False)
def list_values(column):
    """
    Sorted distinct values of a products column, for filter dropdowns.
    """
    df = query(
        f'SELECT DISTINCT "{column}" AS v FROM products WHERE "{column}" IS NOT NULL ORDER BY v'
    )
    return df["v"].tolist()


def search_products(name="", brand=None, form=None, limit=SEARCH_LIMIT):
    """
    Products whose name contains `name` (case-insensitive), optionally
    filtered by brand and supplement form.
    """
    conditions, params = [], []
    if name:
        conditions.append('contains(lower("Product Name"), lower(?))')
        params.append(name)
    if brand:
        conditions.append('"Brand Name" = ?')
        params.append(brand)
    if form:
        conditions.append(f'"{FORM_COL}" = ?')
        params.append(form)

    where = " AND ".join(conditions) or "TRUE"
    return query(
        f'SELECT "DSLD ID", "Product Name", "Brand Name" FROM products '
        f'WHERE {where} ORDER BY "Product Name" LIMIT {int(limit)}',
        params,
    )


# ---------------------------------------------------------
# INGREDIENT TO COMPOUND MAPPING
# ---------------------------------------------------------
def normalize_ingredient_name(name):
    """
    Lowercase, trimmed, single-spaced form used as the key in ingredient_aliases.csv.
    """
    if not isinstance(name, str):
        return ""
    return " ".join(name.lower().split())


@st.cache_data(show_spinner=False)
def load_ingredient_aliases():
    """
    {normalized DSLD ingredient name: ontology compound}, from data/ingredient_aliases.csv.
    """
    aliases = pd.read_csv(ALIASES_CSV)
    return dict(zip(aliases["dsld_name"], aliases["compound"]))


def match_compound(name):
    """
    The ontology compound a DSLD ingredient name maps to, or None.
    """
    return load_ingredient_aliases().get(normalize_ingredient_name(name))


@st.cache_data(show_spinner="Finding products…", max_entries=20)
def products_with_compound(compound):
    """
    One row per product whose Supplement Facts list the compound under any of
    its aliases: the label's name and amount, the dose in the compound's unit
    (for sorting; empty when not comparable) and how it compares with the
    adult RDA and upper limit. Where a product lists the compound more than
    once (folate and folic acid), the row with the highest dose is kept.
    """
    names = [n for n, c in load_ingredient_aliases().items() if c == compound]
    if not names:
        return pd.DataFrame()
    rows = query(
        """
        SELECT f."DSLD ID", p."Product Name", p."Brand Name", p."Market Status",
               f."Ingredient", f."Amount Per Serving", f."Amount Per Serving Unit"
        FROM supplement_facts f
        JOIN products p USING ("DSLD ID")
        WHERE lower(trim(regexp_replace(f."Ingredient", '\\s+', ' ', 'g'))) IN (SELECT unnest(?))
        """,
        [names],
    )
    if rows.empty:
        return rows

    doses, percents, limits = [], [], []
    for ingredient, amount, unit in zip(
        rows["Ingredient"], rows["Amount Per Serving"], rows["Amount Per Serving Unit"]
    ):
        dose = comparable_dose(compound, ingredient, amount, unit)
        comparison = compare_dose(compound, ingredient, amount, unit)
        doses.append(dose.value if dose else None)
        percents.append(comparison.percent_of_rda if comparison else "")
        limits.append(comparison.upper_limit if comparison else "")

    label_amount = (
        rows["Amount Per Serving"].fillna("").str.strip()
        + " " + rows["Amount Per Serving Unit"].fillna("").str.strip()
    ).str.strip()
    result = pd.DataFrame({
        "DSLD ID": rows["DSLD ID"],
        "Product": rows["Product Name"],
        "Brand": rows["Brand Name"],
        "Market Status": rows["Market Status"],
        "Listed as": rows["Ingredient"],
        "Label amount": label_amount,
        "Dose": pd.to_numeric(pd.Series(doses, dtype="float64")),
        "% of adult RDA": percents,
        "Upper limit": limits,
    })
    result = result.sort_values("Dose", ascending=False, na_position="last")
    return result.drop_duplicates("DSLD ID").reset_index(drop=True)


def dose_unit(compound):
    return target_unit(compound)


# ---------------------------------------------------------
# PRODUCT OVERVIEW EXTRACTION
# ---------------------------------------------------------
def extract_overview_fields(row):
    """
    Extracts curated fields from the ProductOverview table.
    """
    # Clean barcode so NaN becomes empty string
    barcode = row.get("Bar Code")
    if pd.isna(barcode):
        barcode = ""

    fields = {
        "URL": row.get("URL", f"https://dsld.od.nih.gov/label/{row.get('DSLD ID', '')}"),
        "DSLD ID": str(row.get("DSLD ID")),  # text, like every other value in the table
        "Bar Code": barcode,   # <-- CLEANED
        "Product Name": row.get("Product Name"),
        "Brand Name": row.get("Brand Name"),
        "Supplement Form": row.get("Supplement Form [LanguaL]"),
        "Net Contents": row.get("Net Contents"),
        "Serving Size": row.get("Serving Size"),
        "Suggested Use": row.get("Suggested Use"),
        "Market Status": row.get("Market Status"),
    }

    clean = {k: v for k, v in fields.items() if pd.notna(v) and v != ""}
    return clean


# ---------------------------------------------------------
# FACTSHEET EXTRACTION
# ---------------------------------------------------------
def get_supplement_facts(product_id):
    """
    The product's Supplement Facts rows, in label order.
    """
    return query(
        'SELECT * FROM supplement_facts WHERE "DSLD ID" = ? ORDER BY "Row Order"', [product_id]
    )


def extract_factsheet_fields(subset):
    """
    Pulls Ingredients, Ingredient Categories, and Daily Value Target Group
    from the product's Supplement Facts rows.
    """

    if subset.empty:
        return {}

    ingredients = sorted(set(subset["Ingredient"].dropna()))
    categories = sorted(set(subset["DSLD Ingredient Categories"].dropna()))
    dv_groups = sorted(set(subset["Daily Value Target Group"].dropna()))

    return {
        "Ingredients": ", ".join(ingredients) if ingredients else None,
        "Ingredient Categories": ", ".join(categories) if categories else None,
        "Daily Value Target Group": ", ".join(dv_groups) if dv_groups else None,
    }


def build_supplement_facts_table(subset):
    """
    Returns the label's Supplement Facts rows: ingredient, amount per serving,
    % Daily Value, how the amount compares with the adult RDA and upper limit,
    and the ontology compound it maps to (or None), in label order.
    """

    if subset.empty:
        return pd.DataFrame()

    amount = (
        subset["Amount Per Serving"].fillna("").str.strip()
        + " "
        + subset["Amount Per Serving Unit"].fillna("").str.strip()
    ).str.strip()

    daily_value = subset["% Daily Value per Serving"].fillna("").str.strip()
    daily_value = daily_value.where(
        ~daily_value.str.fullmatch(r"<?[\d.]+"), daily_value + "%"
    )

    compounds = subset["Ingredient"].map(match_compound)
    comparisons = [
        compare_dose(compound, ingredient, amt, unit)
        for compound, ingredient, amt, unit in zip(
            compounds, subset["Ingredient"], subset["Amount Per Serving"],
            subset["Amount Per Serving Unit"],
        )
    ]

    return pd.DataFrame({
        "Ingredient": subset["Ingredient"].fillna("").values,
        "Amount per serving": amount.values,
        "% Daily Value": daily_value.values,
        "% of adult RDA": [c.percent_of_rda if c else "" for c in comparisons],
        "Upper limit": [c.upper_limit if c else "" for c in comparisons],
        "Compound": compounds.values,
    })


# ---------------------------------------------------------
# OTHER INGREDIENTS EXTRACTION
# ---------------------------------------------------------
def extract_other_ingredients(product_id):
    """
    Pulls Other Ingredients from the other_ingredients table.
    """
    subset = query(
        'SELECT "Other Ingredients" FROM other_ingredients WHERE "DSLD ID" = ?', [product_id]
    )

    if subset.empty:
        return None

    items = sorted(set(subset["Other Ingredients"].dropna()))
    return ", ".join(items) if items else None


# ---------------------------------------------------------
# BRAND INFORMATION EXTRACTION
# ---------------------------------------------------------
def normalize_bool(val):
    """
    Converts DSLD Yes/No/Y/N/True/False into a Python boolean.
    """
    if isinstance(val, str):
        return val.strip().lower() in ["yes", "y", "true", "1"]
    return False


def extract_brand_fields(product_id):
    """
    Extracts company name + boolean role flags for a given DSLD ID.
    """
    # A product can have several company rows, and some have no name
    subset = query(
        'SELECT * FROM companies WHERE "DSLD ID" = ? AND "Company Name" IS NOT NULL '
        'ORDER BY "Row Order"',
        [product_id],
    )

    if subset.empty:
        return None

    row = subset.iloc[0]

    fields = {
        "Company Name": row.get("Company Name"),
        "Manufacturer": normalize_bool(row.get("Manufacturer")),
        "Distributor": normalize_bool(row.get("Distributor")),
        "Packager": normalize_bool(row.get("Packager")),
        "Reseller": normalize_bool(row.get("Reseller")),
        "Other": normalize_bool(row.get("Other")),
    }

    return fields


# ---------------------------------------------------------
# RELATED PRODUCT SIMILARITY
# ---------------------------------------------------------
def name_tokens(name):
    """
    Lowercased word tokens of a product name.
    """
    if not isinstance(name, str):
        return set()
    return set(re.sub(r"[^a-z0-9 ]", " ", name.lower()).split())


def find_related_products(product_id, on_market_only=False):
    """
    Returns up to 5 related products from the same company or companies, ranked by how
    many ingredients they share with the current product (Jaccard overlap),
    with shared words in the product name as a tie-breaker.
    """

    # All other products from the companies on this product
    # (a product can list several companies)
    market_filter = "AND trim(p.\"Market Status\") = 'On Market'" if on_market_only else ""
    candidates = query(
        f"""
        WITH names AS (
            SELECT DISTINCT "Company Name" FROM companies
            WHERE "DSLD ID" = $id AND "Company Name" IS NOT NULL
        )
        SELECT p."DSLD ID", p."Product Name"
        FROM products p
        WHERE p."DSLD ID" IN (
            SELECT c."DSLD ID" FROM companies c JOIN names USING ("Company Name")
        )
        AND p."DSLD ID" <> $id {market_filter}
        """,
        {"id": product_id},
    )

    if candidates.empty:
        return []

    # Ingredient sets for the current product and every candidate
    facts = query(
        """
        SELECT "DSLD ID", lower(trim("Ingredient")) AS ingredient
        FROM supplement_facts
        WHERE "Ingredient" IS NOT NULL
          AND "DSLD ID" IN (SELECT unnest($ids))
        """,
        {"ids": candidates["DSLD ID"].tolist() + [product_id]},
    )
    ingredients = facts.groupby("DSLD ID")["ingredient"].agg(set)
    current_ings = ingredients.get(product_id, set())

    current = get_product(product_id)
    current_tokens = name_tokens(current["Product Name"] if current is not None else "")

    def score(r):
        ings = ingredients.get(r["DSLD ID"], set())
        union = current_ings | ings
        overlap = len(current_ings & ings) / len(union) if union else 0.0
        return (overlap, len(current_tokens & name_tokens(r["Product Name"])))

    candidates = candidates.copy()
    candidates["score"] = candidates.apply(score, axis=1)
    # Ties go to the newest DSLD entry, so the list is stable between visits
    candidates = candidates.sort_values(["score", "DSLD ID"], ascending=False).head(5)

    return [
        {
            "DSLD ID": r["DSLD ID"],
            "Product Name": r["Product Name"],
            "URL": f"https://dsld.od.nih.gov/label/{r['DSLD ID']}",
        }
        for _, r in candidates.iterrows()
    ]


# ---------------------------------------------------------
# PDF LABEL RENDERING
# ---------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=200)
def fetch_label_image(dsld_id):
    """
    Downloads and renders the first page of the DSLD PDF label.
    Returns PNG bytes or None.
    """
    url = f"https://api.ods.od.nih.gov/dsld/s3/pdf/{dsld_id}.pdf"

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        doc = fitz.open(stream=response.content, filetype="pdf")
    except Exception:
        return None

    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        img = pix.tobytes("png")
        return img
    except Exception:
        return None

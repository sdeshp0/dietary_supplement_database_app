import re
import pickle
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
import fitz  # PyMuPDF


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
PICKLE_PATH = DATA_DIR / "dsld_tables.pkl"


# ---------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------
def normalize_barcode(val):
    """
    Reduces a UPC/EAN to its digits without leading zeros, so that
    "0 74312 70640 0", "074312706400" and "74312706400" all match.
    """
    if not isinstance(val, str):
        return ""
    return re.sub(r"\D", "", val).lstrip("0")


@st.cache_resource
def load_dsld_tables():
    """
    Loads the preprocessed DSLD tables from a pickle file.
    This is the ONLY data-loading entry point for the DSLD app.

    Cached as a resource so the ~1.6 GB of tables is loaded once and shared,
    rather than copied on every rerun. Callers must not mutate the tables.
    """
    if not PICKLE_PATH.exists():
        raise FileNotFoundError(
            f"DSLD pickle not found at {PICKLE_PATH}. "
            "Please generate dsld_tables.pkl before running the app."
        )

    with open(PICKLE_PATH, "rb") as f:
        tables = pickle.load(f)

    for name in ["productOverview", "companyInformation", "dietarySupplementFacts", "otherIngredients"]:
        tables[name]["DSLD ID"] = tables[name]["DSLD ID"].astype(str)

    product_df = tables["productOverview"]
    product_df["Bar Code"] = product_df["Bar Code"].fillna("").astype(str).str.strip()
    product_df["Bar Code (normalized)"] = product_df["Bar Code"].map(normalize_barcode)

    return tables


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
        "DSLD ID": row.get("DSLD ID"),
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
def extract_factsheet_fields(facts_df, product_id):
    """
    Pulls Ingredients, Ingredient Categories, and Daily Value Target Group
    from the DietarySupplementFacts table.
    """
    subset = facts_df[facts_df["DSLD ID"] == product_id]

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


def build_supplement_facts_table(facts_df, product_id):
    """
    Returns the label's Supplement Facts rows: ingredient, amount per serving
    and % Daily Value, in label order.
    """
    subset = facts_df[facts_df["DSLD ID"] == product_id]

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

    return pd.DataFrame({
        "Ingredient": subset["Ingredient"].fillna("").values,
        "Amount per serving": amount.values,
        "% Daily Value": daily_value.values,
    })


# ---------------------------------------------------------
# OTHER INGREDIENTS EXTRACTION
# ---------------------------------------------------------
def extract_other_ingredients(other_df, product_id):
    """
    Pulls Other Ingredients from the OtherIngredients table.
    """
    subset = other_df[other_df["DSLD ID"] == product_id]

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


def extract_brand_fields(df, product_id):
    """
    Extracts company name + boolean role flags for a given DSLD ID.
    """
    # A product can have several company rows, and some have no name
    subset = df[df["DSLD ID"] == product_id].dropna(subset=["Company Name"])

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


def find_related_products(product_df, company_info_df, facts_df, product_id, on_market_only=False):
    """
    Returns up to 5 related products from the same company or companies, ranked by how
    many ingredients they share with the current product (Jaccard overlap),
    with shared words in the product name as a tie-breaker.
    """

    # Company names on this product (a product can list several companies)
    company_names = set(
        company_info_df.loc[company_info_df["DSLD ID"] == product_id, "Company Name"].dropna()
    )
    if not company_names:
        return []

    # All other products from these companies
    candidate_ids = set(
        company_info_df.loc[company_info_df["Company Name"].isin(company_names), "DSLD ID"]
    )
    candidate_ids.discard(product_id)

    candidates = product_df[product_df["DSLD ID"].isin(candidate_ids)]

    if on_market_only:
        candidates = candidates[candidates["Market Status"].str.strip() == "On Market"]

    if candidates.empty:
        return []

    # Ingredient sets for the current product and every candidate
    facts = facts_df.loc[
        facts_df["DSLD ID"].isin(set(candidates["DSLD ID"]) | {product_id}),
        ["DSLD ID", "Ingredient"],
    ].dropna()
    ingredients = facts.groupby("DSLD ID")["Ingredient"].agg(
        lambda s: set(s.str.strip().str.lower())
    )
    current_ings = ingredients.get(product_id, set())

    current_name = product_df.loc[product_df["DSLD ID"] == product_id, "Product Name"]
    current_tokens = name_tokens(current_name.iloc[0] if not current_name.empty else "")

    def score(r):
        ings = ingredients.get(r["DSLD ID"], set())
        union = current_ings | ings
        overlap = len(current_ings & ings) / len(union) if union else 0.0
        return (overlap, len(current_tokens & name_tokens(r["Product Name"])))

    candidates = candidates.copy()
    candidates["score"] = candidates.apply(score, axis=1)
    candidates = candidates.sort_values("score", ascending=False).head(5)

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

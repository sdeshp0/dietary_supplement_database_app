import re
import pickle
from pathlib import Path
import pandas as pd
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
@st.cache_data
def load_dsld_tables():
    """
    Loads the preprocessed DSLD tables from a pickle file.
    This is the ONLY data-loading entry point for the DSLD app.
    """
    if not PICKLE_PATH.exists():
        raise FileNotFoundError(
            f"DSLD pickle not found at {PICKLE_PATH}. "
            "Please generate dsld_tables.pkl before running the app."
        )

    with open(PICKLE_PATH, "rb") as f:
        tables = pickle.load(f)

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
        "Contents": row.get("Contents"),
        "Serving Size": row.get("Serving Size"),
        "Suggested Use": row.get("Suggested Use"),
        "Primary Ingredient(s)": row.get("Primary Ingredient(s)"),
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
    subset = df[df["DSLD ID"] == product_id]

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
def compute_similarity(name_a, name_b):
    """
    Lightweight similarity scoring for product names.
    Higher score = more similar.
    """
    if not isinstance(name_a, str) or not isinstance(name_b, str):
        return 0

    # Normalize
    a = re.sub(r"[^a-z0-9 ]", " ", name_a.lower())
    b = re.sub(r"[^a-z0-9 ]", " ", name_b.lower())

    tokens_a = set(a.split())
    tokens_b = set(b.split())

    overlap = len(tokens_a & tokens_b)

    # Category-like keywords
    vitamin_keywords = ["vitamin", "d", "c", "b", "b12", "b6", "k", "e"]
    mineral_keywords = ["calcium", "magnesium", "zinc", "iron"]

    bonus = 0
    if any(k in a for k in vitamin_keywords) and any(k in b for k in vitamin_keywords):
        bonus += 2
    if any(k in a for k in mineral_keywords) and any(k in b for k in mineral_keywords):
        bonus += 2

    # Partial substring match
    if a in b or b in a:
        bonus += 3

    return overlap + bonus


def find_related_products(product_df, company_info_df, product_id, on_market_only=False):
    """
    Returns up to 5 related products from the same company,
    ranked by similarity to the current product name.
    """

    # Find company name
    row = company_info_df[company_info_df["DSLD ID"] == product_id]
    if row.empty:
        return []

    company_name = row.iloc[0].get("Company Name")
    if not company_name:
        return []

    # All products from this company
    related = company_info_df[company_info_df["Company Name"] == company_name]

    # Merge with product overview to get product names
    merged = related.merge(product_df, on="DSLD ID", suffixes=("_ci", "_po"))

    # Exclude current product
    merged = merged[merged["DSLD ID"] != product_id]

    # Filter by market status
    if on_market_only and "Market Status" in merged.columns:
        merged = merged[merged["Market Status"].str.strip() == "On Market"]

    if merged.empty:
        return []

    # Current product name
    current_name = (
        product_df.loc[product_df["DSLD ID"] == product_id, "Product Name"]
        .fillna("")
        .values[0]
    )

    # Defensive fill
    merged = merged.copy()
    merged["Product Name_po"] = merged["Product Name_po"].fillna("")

    # Compute similarity
    merged["similarity"] = merged["Product Name_po"].apply(
        lambda x: compute_similarity(current_name, x)
    )

    # Sort + limit
    merged = merged.sort_values("similarity", ascending=False).head(5)

    # Build results
    results = []
    for _, r in merged.iterrows():
        results.append({
            "DSLD ID": r["DSLD ID"],
            "Product Name": r["Product Name_po"],
            "URL": f"https://dsld.od.nih.gov/label/{r['DSLD ID']}",
        })

    return results



# ---------------------------------------------------------
# PDF LABEL RENDERING
# ---------------------------------------------------------
def fetch_label_image(dsld_id):
    """
    Downloads and renders the first page of the DSLD PDF label.
    Returns a PIL image or None.
    """
    url = f"https://api.ods.od.nih.gov/dsld/s3/pdf/{dsld_id}.pdf"

    try:
        doc = fitz.open(stream=Path(url).read_bytes(), filetype="pdf")
    except Exception:
        return None

    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        img = pix.tobytes("png")
        return img
    except Exception:
        return None

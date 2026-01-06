import streamlit as st
import fitz
from PIL import Image
import io
import requests
import pandas as pd
import glob
import os
import pickle
import re


st.set_page_config(page_title="DSLD Barcode Lookup", layout="wide")

# -------------------------------------------------
# Load all DSLD CSVs
# -------------------------------------------------


@st.cache_data
def load_data():

    if len(glob.glob("data/*.pkl")) > 0:

        with open("data/tables.pkl", 'rb') as f:
            tables = pickle.load(f)

    else:
        st.info('Reading data from files')
        files = glob.glob("data/*.csv")
        tables = {}

        po = []
        ci = []
        dsf = []
        ls = []
        oi = []

        for f in files:
            fname = os.path.basename(f)

            # Skip readme and malformed LabelStatements files
            if fname.lower().startswith("readme") or fname.startswith("LabelStatements_"):
                continue

            df = pd.read_csv(f, dtype=str)

            if fname.startswith("ProductOverview_"):
                po.append(df)

            elif fname.startswith("CompanyInformation_"):
                ci.append(df)

            elif fname.startswith("DietarySupplementFacts_"):
                dsf.append(df)

            elif fname.startswith("OtherIngredients_"):
                oi.append(df)

        tables["productOverview"] = pd.concat(po, ignore_index=True)
        tables["companyInformation"] = pd.concat(ci, ignore_index=True)
        tables["dietarySupplementFacts"] = pd.concat(dsf, ignore_index=True)
        tables["labelStatements"] = pd.DataFrame()  # empty placeholder
        tables["otherIngredients"] = pd.concat(oi, ignore_index=True)

        st.info('saving data to pickle file')

        with open("data/tables.pkl", 'wb') as f:
            pickle.dump(tables, f)

    return tables


@st.cache_data
def fetch_label_image(product_id):
    pdf_url = f"https://api.ods.od.nih.gov/dsld/s3/pdf/{product_id}.pdf"
    print(pdf_url)

    try:
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()

        # Load PDF from bytes
        doc = fitz.open(stream=response.content, filetype="pdf")

        # Render first page
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)

        # Convert to PIL image
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img

    except Exception as e:
        print(f"Error: {e}")
        return None


tables = load_data()
product_df = tables["productOverview"]
st.info('Loaded DSLD Database')


# Check if a DSLD ID was passed in the URL
preselected_id = st.query_params.get("dsld_id")
# -------------------------------------------------
# Helper Functions
# -------------------------------------------------


def extract_overview_fields(row):
    fields = {
        "URL": row.get("URL", f"https://dsld.od.nih.gov/label/{row.get('DSLD ID', '')}"),
        "DSLD ID": row.get("DSLD ID"),
        "Product Name": row.get("Product Name"),
        "Brand Name": row.get("Brand Name"),
        "Contents": row.get("Contents"),
        "Product Type": row.get("Product Type [LanguaL]"),
        "Supplement Form": row.get("Supplement Form [LanguaL]"),
        "Serving Size": row.get("Serving Size"),
        "Suggested Use": row.get("Suggested Use"),
        "Primary Ingredient(s)": row.get("Primary Ingredient(s)"),
        "Market Status": row.get("Market Status")
    }

    # Remove empty or NaN fields
    clean = {k: v for k, v in fields.items() if pd.notna(v) and v != ""}
    return clean


def extract_factsheet_fields(facts_df, product_id):
    subset = facts_df[facts_df["DSLD ID"] == product_id]

    if subset.empty:
        return {}

    # Collect unique values (some products have multiple rows)
    ingredients = sorted(set(subset["Ingredient"].dropna()))
    categories = sorted(set(subset["DSLD Ingredient Categories"].dropna()))
    dv_groups = sorted(set(subset["Daily Value Target Group"].dropna()))

    return {
        "Ingredients": ", ".join(ingredients) if ingredients else None,
        "Ingredient Categories": ", ".join(categories) if categories else None,
        "Daily Value Target Group": ", ".join(dv_groups) if dv_groups else None
    }


def extract_other_ingredients(other_df, product_id):
    subset = other_df[other_df["DSLD ID"] == product_id]

    if subset.empty:
        return None

    # Combine all rows into a single comma-separated string
    items = sorted(set(subset["Other Ingredients"].dropna()))
    return ", ".join(items) if items else None


def compute_similarity(name_a, name_b):
    """
    Returns a similarity score between two product names.
    Higher = more similar.
    """

    if not isinstance(name_a, str) or not isinstance(name_b, str):
        return 0

    # Normalize
    a = re.sub(r"[^a-z0-9 ]", " ", name_a.lower())
    b = re.sub(r"[^a-z0-9 ]", " ", name_b.lower())

    tokens_a = set(a.split())
    tokens_b = set(b.split())

    # Token overlap score
    overlap = len(tokens_a & tokens_b)

    # Bonus for vitamin/mineral category similarity
    vitamin_keywords = ["vitamin", "d", "c", "b", "b12", "b6", "k", "e"]
    mineral_keywords = ["calcium", "magnesium", "zinc", "iron"]

    bonus = 0
    if any(k in a for k in vitamin_keywords) and any(k in b for k in vitamin_keywords):
        bonus += 2
    if any(k in a for k in mineral_keywords) and any(k in b for k in mineral_keywords):
        bonus += 2

    # Partial substring match bonus
    if a in b or b in a:
        bonus += 3

    return overlap + bonus


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
        "Manufacturer": row.get("Manufacturer"),
        "Distributor": row.get("Distributor"),
        "Packager": row.get("Packager"),
        "Reseller": row.get("Reseller"),
        "Other": row.get("Other")
    }

    # Normalize booleans: DSLD often uses "Yes"/"No" or "Y"/"N"
    def normalize_bool(val):
        if isinstance(val, str):
            return val.strip().lower() in ["yes", "y", "true", "1"]
        return False

    bool_fields = {k: normalize_bool(v) for k, v in fields.items() if k != "Company Name"}

    return {
        "Company Name": fields["Company Name"],
        "Roles": bool_fields
    }


def find_related_products(product_df, company_info_df, product_id, on_market_only=False):
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
        merged = merged[merged["Market Status"] == "On Market"]

    if merged.empty:
        return []

    # Get current product name
    current_name = product_df.loc[product_df["DSLD ID"] == product_id, "Product Name"].values[0]

    # Compute similarity scores
    merged["similarity"] = merged["Product Name_po"].apply(lambda x: compute_similarity(current_name, x))

    # Sort by similarity descending
    merged = merged.sort_values("similarity", ascending=False)

    # Limit to top 5
    merged = merged.head(5)

    # Build results
    results = []
    for _, r in merged.iterrows():
        results.append({
            "DSLD ID": r["DSLD ID"],
            "Product Name": r["Product Name_po"],
            "URL": f"https://dsld.od.nih.gov/label/{r['DSLD ID']}"
        })

    return results

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("🔍 Dietary Supplement Barcode Lookup")

st.write('This app allows you to search for dietary supplements by their UPC Barcodes in the NIH Dietary Supplement '
         'Label Database')
st.write('https://ods.od.nih.gov/Research/Dietary_Supplement_Label_Database.aspx')

barcode = st.text_input("Enter a barcode (UPC):", "")

selected_product = None
name = None
product_id = None

# If URL contains a DSLD ID, load that product immediately
if preselected_id:
    match = product_df[product_df["DSLD ID"] == preselected_id]
    if not match.empty:
        selected_product = match.iloc[0]
        name = selected_product["Product Name"]
        product_id = selected_product["DSLD ID"]
        st.success(f"Loaded product: {name} (via link)")
    else:
        st.error("Invalid DSLD ID in URL.")

# Otherwise fall back to barcode search
elif barcode:
    barcode = barcode.strip()
    match = product_df[product_df["Bar Code"] == barcode]

    if match.empty:
        st.warning("No product found for this barcode.")
    else:
        selected_product = match.iloc[0]
        name = selected_product["Product Name"]
        product_id = selected_product["DSLD ID"]
        st.success(f"Found product: {name}")

# -------------------------------------------------
# Tabs (only show if a product is selected)
# -------------------------------------------------
if selected_product is not None:
    t1, t2 = st.tabs(
        ["Product Overview", "Brand Information"]
    )

    # -------------------------
    # TAB 1: Product Overview
    # -------------------------
    with t1:
        st.subheader(f"Product Overview for {name}")

        # Toggle for product label image
        with st.expander("Show Product Label (PDF Image)", expanded=False):
            img = fetch_label_image(product_id)
            if img:
                st.image(img, caption="Product Label")
            else:
                st.info("No label image available for this product.")

        st.write("### Product Summary")

        overview_data = extract_overview_fields(selected_product)

        facts_df = tables["dietarySupplementFacts"]
        facts_info = extract_factsheet_fields(facts_df, product_id)

        for key, value in facts_info.items():
            if value:
                overview_data[key] = value

        other_df = tables["otherIngredients"]
        other_ings = extract_other_ingredients(other_df, product_id)

        if other_ings:
            overview_data["Other Ingredients"] = other_ings

        # Highlight On Market status
        if overview_data.get("Market Status", "").lower() == "on market":
            st.success("This product is currently **on the market**.")
        elif overview_data.get("Market Status", "").lower() == "off market":
            st.error("This product is **not currently on the market**.")
        else:
            st.info("Market status unknown.")

        # Display curated table
        summary_df = pd.DataFrame.from_dict(overview_data, orient="index", columns=["Value"])
        st.table(summary_df)

    # -------------------------
    # TAB 2: Brand / Company Info
    # -------------------------
    with t2:
        st.subheader("Brand / Company Information")

        df = tables["companyInformation"]
        info = extract_brand_fields(df, product_id)

        if info is None:
            st.info("No company information found for this product.")
        else:
            st.write(f"### {info['Company Name']}")

            st.write("#### Company Roles")

            # Display checkboxes for each boolean role
            cols = st.columns(3)

            role_items = list(info["Roles"].items())

            for i, (role, value) in enumerate(role_items):
                with cols[i % 3]:
                    st.checkbox(role, value=value, disabled=True)

        st.write("### Related Products by This Company")

        # Filter toggle
        on_market_only = st.checkbox("Show only products currently on market", value=False)

        related = find_related_products(product_df, df, product_id, on_market_only)

        if not related:
            st.info("No related products found.")
        else:
            for item in related:
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(
                        f"**{item['Product Name']}**  \n"
                        f"DSLD ID: `{item['DSLD ID']}`  \n"
                        f"[View on DSLD]({item['URL']})"
                    )

                with col2:
                    if st.button("View in App", key=f"view_{item['DSLD ID']}"):
                        st.query_params.dsld_id=item["DSLD ID"]
                        st.rerun()

import streamlit as st
import fitz
from PIL import Image
import io
import requests
import pandas as pd
import glob
import os
import pickle

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
# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("🔍 Dietary Supplement Barcode Lookup")

st.write('This app allows you to search for dietary supplements by their UPC Barcodes in the NIH Dietary Supplement Label Database')
st.write('https://ods.od.nih.gov/Research/Dietary_Supplement_Label_Database.aspx')

barcode = st.text_input("Enter a barcode (UPC):", "")

selected_product = None
name = None
product_id = None

if barcode:
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
    t1, t2, t3, t4 = st.tabs(
        ["Product Overview", "Brand Information", "Factsheet", "Other"]
    )

    # -------------------------
    # TAB 1: Product Overview
    # -------------------------
    with t1:
        st.subheader(f"Product Overview for {name}")
        img = fetch_label_image(product_id)
        if img:
            st.image(img, caption="Product Label")
        else:
            st.info("No label image available for this product.")

        st.dataframe(selected_product.to_frame().rename(columns={0: "Value"}), use_container_width=True)

    # -------------------------
    # TAB 2: Brand / Company Info
    # -------------------------
    with t2:
        st.subheader("Brand / Company Information")
        df = tables["companyInformation"]
        subset = df[df["DSLD ID"] == product_id].transpose()
        st.dataframe(subset if not subset.empty else "No company info found.", use_container_width=True)

    # -------------------------
    # TAB 3: Supplement Facts
    # -------------------------
    with t3:
        st.subheader("Supplement Facts")
        df = tables["dietarySupplementFacts"]
        subset = df[df["DSLD ID"] == product_id]
        st.dataframe(subset if not subset.empty else "No factsheet data found.", hide_index=True, use_container_width=True)

    # -------------------------
    # TAB 4: Other Ingredients + Label Statements
    # -------------------------
    with t4:
        st.subheader("Other Ingredients")
        df = tables["otherIngredients"]
        subset = df[df["DSLD ID"] == product_id]
        st.dataframe(subset if not subset.empty else "No other ingredients found.", hide_index=True, use_container_width=True)
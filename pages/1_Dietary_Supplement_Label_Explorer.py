import streamlit as st
import pandas as pd

from utils.dsld_helpers import (
    load_dsld_tables,
    extract_overview_fields,
    extract_factsheet_fields,
    extract_other_ingredients,
    extract_brand_fields,
    find_related_products,
    fetch_label_image,
    normalize_barcode,
    build_supplement_facts_table,
)

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="DSLD Dietary Supplement Explorer",
    layout="wide",
)

st.title("📦 DSLD Dietary Supplement Explorer")
st.write(
    "Explore products from the NIH Dietary Supplement Label Database (DSLD) "
    "by searching product names, brands, supplement forms, or scanning barcodes."
)
st.caption(
    "For information only, not medical advice. Label data comes from the NIH DSLD "
    "and may not match the product currently on sale. Talk to a doctor or pharmacist "
    "before starting a supplement."
)

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
tables = load_dsld_tables()

product_df = tables["productOverview"]
company_df = tables["companyInformation"]
facts_df = tables["dietarySupplementFacts"]
other_df = tables["otherIngredients"]

# Identify supplement form column (DSLD calls it "Supplement Form [LanguaL]")
FORM_COL = None
for c in product_df.columns:
    if c.lower().startswith(("supplement form", "dosage form")) or c.lower() == "form":
        FORM_COL = c
        break

# ---------------------------------------------------------
# READ QUERY PARAMS
# ---------------------------------------------------------
preselected_id = st.query_params.get("dsld_id")

# ---------------------------------------------------------
# SIDEBAR: PRODUCT LOOKUP MODES
# ---------------------------------------------------------
st.sidebar.header("Product Lookup")

lookup_mode = st.sidebar.radio(
    "Choose lookup mode:",
    ["Search", "Barcode"],
    index=0,
)

selected_product = None
product_id = None
product_name = None

# ---------------------------------------------------------
# 1) DEEP LINKING ALWAYS TAKES PRIORITY
# ---------------------------------------------------------
if preselected_id:
    match = product_df[product_df["DSLD ID"] == preselected_id]
    if not match.empty:
        selected_product = match.iloc[0]
        product_id = selected_product["DSLD ID"]
        product_name = selected_product.get("Product Name", "")
        st.sidebar.success(f"Loaded via link: {product_name}")
    else:
        st.sidebar.error("No product found for DSLD ID from URL.")
        preselected_id = None

# ---------------------------------------------------------
# 2) SEARCH MODE — ALWAYS AVAILABLE
# ---------------------------------------------------------
if lookup_mode == "Search":

    st.sidebar.subheader("🔎 Search Products")

    search_name = st.sidebar.text_input("Search by product name:", "")

    brands = sorted(product_df["Brand Name"].dropna().unique())
    brand_filter = st.sidebar.selectbox("Filter by brand:", ["All"] + brands)

    if FORM_COL:
        forms = sorted(product_df[FORM_COL].dropna().unique())
        form_filter = st.sidebar.selectbox("Filter by supplement form:", ["All"] + forms)
    else:
        form_filter = "All"

    # Apply filters
    results = product_df.copy()

    if search_name:
        results = results[
            results["Product Name"].str.contains(search_name, case=False, na=False)
        ]

    if brand_filter != "All":
        results = results[results["Brand Name"] == brand_filter]

    if form_filter != "All" and FORM_COL:
        results = results[results[FORM_COL] == form_filter]

    # Display results
    if search_name or brand_filter != "All" or form_filter != "All":
        st.sidebar.markdown("### Results")

        if results.empty:
            st.sidebar.info("No products match your search.")
        else:
            for _, row in results.head(50).iterrows():
                label = f"{row['Product Name']} ({row['Brand Name']})"
                if st.sidebar.button(label, key=f"search_{row['DSLD ID']}"):
                    st.query_params.dsld_id = row["DSLD ID"]
                    st.rerun()

# ---------------------------------------------------------
# 3) BARCODE MODE — ALWAYS AVAILABLE
# ---------------------------------------------------------
if lookup_mode == "Barcode":

    st.sidebar.subheader("Scan or Enter Barcode")

    barcode_input = st.sidebar.text_input("Enter barcode (UPC):", "")

    barcode_digits = normalize_barcode(barcode_input)

    if barcode_input and not barcode_digits:
        st.sidebar.warning("A barcode should contain digits.")
    elif barcode_digits:
        match = product_df[product_df["Bar Code (normalized)"] == barcode_digits]
        if match.empty:
            st.sidebar.warning("No product found for this barcode.")
        else:
            selected_product = match.iloc[0]
            product_id = selected_product["DSLD ID"]
            product_name = selected_product.get("Product Name", "")
            st.sidebar.success(f"Found product: {product_name}")

# ---------------------------------------------------------
# STOP IF NO PRODUCT SELECTED
# ---------------------------------------------------------
if selected_product is None:
    st.info("Use the sidebar to search for a product by Name and Brand or by UPC Barcode")
    st.stop()

# ---------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------
t1, t2 = st.tabs(["Product Overview", "Brand Information"])

# ---------------------------------------------------------
# TAB 1: PRODUCT OVERVIEW
# ---------------------------------------------------------
with t1:
    st.subheader("Product Overview")

    overview_data = extract_overview_fields(selected_product)

    # Factsheet fields
    facts_info = extract_factsheet_fields(facts_df, product_id)
    for key, value in facts_info.items():
        if value:
            overview_data[key] = value

    # Other ingredients
    other_ings = extract_other_ingredients(other_df, product_id)
    if other_ings:
        overview_data["Other Ingredients"] = other_ings

    # Market status badge
    market_status = overview_data.get("Market Status", "")
    if market_status == "On Market":
        st.markdown("**Market Status:** 🟢 On Market")
    elif market_status:
        st.markdown(f"**Market Status:** ⚠️ {market_status}")
    else:
        st.markdown("**Market Status:** Unknown")

    # Summary table
    summary_df = pd.DataFrame.from_dict(
        overview_data, orient="index", columns=["Value"]
    )
    st.table(summary_df)

    # Supplement Facts panel
    st.markdown("### Supplement Facts")
    facts_table = build_supplement_facts_table(facts_df, product_id)
    if facts_table.empty:
        st.info("No Supplement Facts data for this product.")
    else:
        serving = overview_data.get("Serving Size")
        if serving:
            st.caption(f"Per serving: {serving}")
        st.dataframe(facts_table, hide_index=True, width="stretch")

    # Label PDF preview
    st.markdown("---")
    with st.expander("Product Label", expanded=False):
        img_bytes = fetch_label_image(product_id)

        if img_bytes:
            st.image(img_bytes, caption="Product Label Preview", width="stretch")
        else:
            st.info("Label preview unavailable. You can still open the PDF below.")

        url = f"https://api.ods.od.nih.gov/dsld/s3/pdf/{product_id}.pdf"
        if url:
            st.markdown(f"[Open full DSLD Label PDF]({url})")

# ---------------------------------------------------------
# TAB 2: BRAND INFORMATION
# ---------------------------------------------------------
with t2:
    st.subheader("Brand / Company Information")

    brand_info = extract_brand_fields(company_df, product_id)
    if not brand_info:
        st.info("No company information available for this product.")
    else:
        st.markdown(f"### {brand_info['Company Name']}")

        st.markdown("#### Company Roles")
        c1, c2, c3 = st.columns(3)

        with c1:
            st.checkbox("Manufacturer", value=brand_info["Manufacturer"], disabled=True)
            st.checkbox("Distributor", value=brand_info["Distributor"], disabled=True)

        with c2:
            st.checkbox("Packager", value=brand_info["Packager"], disabled=True)
            st.checkbox("Reseller", value=brand_info["Reseller"], disabled=True)

        with c3:
            st.checkbox("Other", value=brand_info["Other"], disabled=True)

        st.markdown("---")
        st.markdown("### Related Products by This Company")

        on_market_only = st.checkbox(
            "Show only products currently on market", value=False
        )

        related = find_related_products(
            product_df=product_df,
            company_info_df=company_df,
            facts_df=facts_df,
            product_id=product_id,
            on_market_only=on_market_only,
        )

        if not related:
            st.info("No related products found for this company with current filters.")
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
                    if st.button("View", key=f"view_{item['DSLD ID']}"):
                        st.query_params.dsld_id = item["DSLD ID"]
                        st.rerun()

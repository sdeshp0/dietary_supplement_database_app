import re
from urllib.parse import quote

import streamlit as st
import pandas as pd

from utils.dsld_helpers import (
    FORM_COL,
    get_product,
    get_product_by_barcode,
    get_supplement_facts,
    count_products,
    parse_dsld_id,
    search_facet,
    search_products,
    extract_overview_fields,
    extract_factsheet_fields,
    extract_other_ingredients,
    extract_brand_fields,
    find_related_products,
    fetch_label_image,
    normalize_barcode,
    build_supplement_facts_table,
)
from utils.stack_state import add_to_stack, in_stack, open_stack

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
# READ QUERY PARAMS
# ---------------------------------------------------------
# The open product (dsld_id) and the search (q, brand, form, market) are kept
# in the page link, so "Back to results" and a shared link restore both
preselected_id = st.query_params.get("dsld_id")

SEARCH_PARAMS = {"q": "search_q", "brand": "search_brand", "form": "search_form"}
for param, key in SEARCH_PARAMS.items():
    if key not in st.session_state:
        st.session_state[key] = st.query_params.get(param, "")
if "search_market" not in st.session_state:
    st.session_state["search_market"] = st.query_params.get("market") == "1"


def sync_search_params():
    """Mirrors the search widgets in the page link."""
    for param, key in SEARCH_PARAMS.items():
        value = st.session_state[key]
        if value:
            st.query_params[param] = value
        elif param in st.query_params:
            del st.query_params[param]
    if st.session_state["search_market"]:
        st.query_params["market"] = "1"
    elif "market" in st.query_params:
        del st.query_params["market"]


def open_product(dsld_id):
    st.query_params["dsld_id"] = str(dsld_id)
    st.rerun()


def short_form(form):
    """'Capsule [E0159]' -> 'Capsule' (drops the LanguaL code)."""
    return re.sub(r"\s*\[[^\]]*\]$", "", form) if isinstance(form, str) else form


def facet_select(label, column, key, all_label, **search):
    """
    A filter dropdown listing only the values that give results, with
    counts. The counts are part of each option's label, and a selectbox
    loses its value when its labels change, so the widget gets a new key
    whenever the counts do and the choice itself is kept under `key`.
    """
    counts = search_facet(column, **search)
    current = st.session_state[key]
    if current and current not in counts:
        counts = {current: 0, **counts}
    options = [""] + list(counts)
    widget_key = f"{key}_{hash(tuple(counts.items()))}"

    def remember():
        st.session_state[key] = st.session_state[widget_key]

    st.sidebar.selectbox(
        label,
        options,
        index=options.index(current),
        key=widget_key,
        on_change=remember,
        format_func=lambda v: f"{short_form(v)} ({counts[v]:,})" if v else all_label,
        help="Lists only the values with products that match the rest of your search",
    )


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
    match = get_product(parse_dsld_id(preselected_id))
    if match is not None:
        selected_product = match
        product_id = int(selected_product["DSLD ID"])
        product_name = selected_product.get("Product Name", "")
    else:
        st.sidebar.error("No product found for DSLD ID from URL.")
        preselected_id = None

# ---------------------------------------------------------
# 2) SEARCH MODE: filters in the sidebar, results in the main area
# ---------------------------------------------------------
search = {}
if lookup_mode == "Search":

    st.sidebar.subheader("🔎 Search Products")

    st.sidebar.text_input("Search by product name:", key="search_q")
    st.sidebar.checkbox("On the market only", key="search_market")
    search = {
        "name": st.session_state["search_q"].strip(),
        "brand": st.session_state["search_brand"] or None,
        "form": st.session_state["search_form"] or None,
        "on_market": st.session_state["search_market"],
    }
    facet_select("Filter by brand:", "Brand Name", "search_brand", "All brands", **search)
    facet_select("Filter by supplement form:", FORM_COL, "search_form", "All forms", **search)
    sync_search_params()

    # Changing the search while a product is open goes back to the results
    previous = st.session_state.get("last_search")
    st.session_state["last_search"] = search
    if previous is not None and previous != search and selected_product is not None:
        del st.query_params["dsld_id"]
        selected_product = product_id = product_name = preselected_id = None

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
        match = get_product_by_barcode(barcode_digits)
        if match is None:
            st.sidebar.warning("No product found for this barcode.")
        else:
            selected_product = match
            product_id = int(selected_product["DSLD ID"])
            product_name = selected_product.get("Product Name", "")
            st.sidebar.success(f"Found product: {product_name}")

searching = any(v for k, v in search.items() if k != "on_market")

# ---------------------------------------------------------
# NO PRODUCT OPEN: SEARCH RESULTS
# ---------------------------------------------------------
if selected_product is None:
    if not searching:
        st.info(
            "Search by product name, or pick a brand or supplement form in the sidebar, "
            "to list products. You can also look a product up by its UPC barcode."
        )
        st.stop()

    total = count_products(**search)
    results = search_products(**search)
    if results.empty:
        st.info("No products match your search.")
        st.stop()

    st.markdown("### Products")
    more = " Narrow your search to see the rest." if total > len(results) else ""
    st.caption(
        f"Showing {len(results):,} of {total:,} products, by name.{more} "
        "Tick a product to open it or add it to your stack."
    )
    results["Form"] = results["Form"].map(short_form)
    columns = ["Product Name", "Brand Name", "Form", "Market Status"]
    if search["on_market"]:
        columns.remove("Market Status")
    selection = st.dataframe(
        results[columns],
        hide_index=True,
        width="stretch",
        key=f"results_{sorted(search.items())}",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Product Name": st.column_config.TextColumn("Product", width="large"),
            "Brand Name": st.column_config.TextColumn("Brand", width="medium"),
        },
    )
    chosen = results.iloc[selection.selection.rows]
    col_open, col_add = st.columns(2)
    with col_open:
        if len(chosen) == 1:
            if st.button(f"Open {chosen['Product Name'].iloc[0]}", type="primary"):
                open_product(int(chosen["DSLD ID"].iloc[0]))
        else:
            st.button(
                "Open the ticked product" if not len(chosen) else "Tick one product to open it",
                disabled=True,
            )
    with col_add:
        if st.button(
            f"➕ Add {len(chosen)} selected to stack" if len(chosen)
            else "➕ Tick products to add them to your stack",
            disabled=chosen.empty,
            help="Adds the ticked products to the Supplement Stack Checker",
        ):
            add_to_stack(chosen["DSLD ID"].tolist())
    st.stop()

if searching and preselected_id:
    if st.button("← Back to results"):
        del st.query_params["dsld_id"]
        st.rerun()

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
    facts_rows = get_supplement_facts(product_id)
    facts_info = extract_factsheet_fields(facts_rows)
    for key, value in facts_info.items():
        if value:
            overview_data[key] = value

    # Other ingredients
    other_ings = extract_other_ingredients(product_id)
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
    col_title, col_stack = st.columns([3, 1], vertical_alignment="bottom")
    with col_title:
        st.markdown("### Supplement Facts")
    with col_stack:
        if in_stack(product_id):
            if st.button("✓ In your stack", help="Open the Supplement Stack Checker"):
                open_stack()
        elif st.button("➕ Add to stack", type="primary",
                       help="Add this product to the Supplement Stack Checker"):
            add_to_stack([product_id])
    facts_table = build_supplement_facts_table(facts_rows)
    if facts_table.empty:
        st.info("No Supplement Facts data for this product.")
    else:
        serving = overview_data.get("Serving Size")
        if serving:
            st.caption(f"Per serving: {serving}")
        if facts_table[["% of adult RDA", "Upper limit"]].ne("").any(axis=None):
            st.caption(
                "RDA and upper limit are NIH Office of Dietary Supplements values for "
                "adults 19 and older, not pregnant or breastfeeding. A range covers the "
                "differences between men and women and between age groups. The "
                "comparison is for one serving; check the label for servings per day. "
                "Caffeine is compared with the FDA's 400 mg a day for most healthy adults."
            )
        # Link each ingredient that maps to an ontology compound to its
        # entry in the Ingredient Metadata Explorer
        facts_table["Compound"] = facts_table["Compound"].map(
            lambda c: f"Ingredient_Metadata_Explorer?compound={quote(c)}" if isinstance(c, str) else ""
        )
        st.dataframe(
            facts_table,
            hide_index=True,
            width="stretch",
            column_config={
                "% of adult RDA": st.column_config.TextColumn(
                    help="Amount per serving as a share of the recommended amount for adults",
                ),
                "Upper limit": st.column_config.TextColumn(
                    help="Whether one serving goes over the adult tolerable upper intake level. "
                    "\"Salt weight\": a mineral or caffeine named as a salt, such as magnesium citrate, "
                    "may list the weight of the whole salt, so it isn't compared.",
                    width="medium",
                ),
                "Compound": st.column_config.LinkColumn(
                    "Ingredient details",
                    help="Opens this ingredient in the Ingredient Metadata Explorer",
                    display_text=r"compound=(.*)$",
                ),
            },
        )

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

    brand_info = extract_brand_fields(product_id)
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

        related = find_related_products(product_id, on_market_only=on_market_only)

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
                        st.query_params.dsld_id = str(item["DSLD ID"])
                        st.rerun()

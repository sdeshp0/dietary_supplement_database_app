import streamlit as st

st.set_page_config(
    page_title="Home – Supplement Explorer",
    layout="wide",
)

st.title("🧭 Supplement Data Explorer")
st.divider()

# ---------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------
st.header("📘 What you can do in this app")

st.subheader("1. DSLD Dietary Supplement Explorer")
st.write(
    """
    Explore products from the **NIH Dietary Supplement Label Database (DSLD)**.
    You can:
    - Search by product name  
    - Filter by brand and supplement form  
    - Look up products by barcode  
    - View product labels, factsheets, and ingredient lists  
    - Explore related products from the same brand  
    """
)

st.subheader("2. Ingredient Metadata Explorer")
st.write(
    """
    Dive into ingredient-level information sourced from the **NIH Office of Dietary Supplements (ODS)**.
    You can:
    - Explore ingredients by health goal  
    - Filter by mechanism and category  
    - Visualize mechanism → compound networks  
    - Read safety, interaction, and RDA/UL summaries  
    """
)

st.markdown("---")

# ---------------------------------------------------------
# DATA SOURCES
# ---------------------------------------------------------
st.header("🔗 Primary Data Sources")

st.markdown(
    """
    **NIH Dietary Supplement Label Database (DSLD)**  
    A comprehensive repository of dietary supplement labels sold in the U.S.  
    [https://dsld.od.nih.gov](https://dsld.od.nih.gov)

    **NIH Office of Dietary Supplements (ODS)**  
    Evidence-based fact sheets and ingredient metadata.  
    [https://ods.od.nih.gov](https://ods.od.nih.gov)
    """
)

st.markdown("---")

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.caption(
    "For information only, not medical advice. Talk to a doctor or pharmacist "
    "before starting a supplement."
)
st.caption(
    "This app integrates DSLD product data and ODS ingredient metadata to provide a unified, "
    "interactive exploration experience for supplements and their components."
)

import streamlit as st

st.set_page_config(
    page_title="Home – Supplement Explorer",
    layout="wide",
)

st.title("🧭 Supplement Data Explorer")

st.warning(
    """
    **For information only, not medical advice.** This app doesn't diagnose, treat or
    prevent any condition, and it can't tell you whether a supplement is safe or right
    for you. Talk to a doctor or pharmacist before starting, stopping or combining
    supplements, especially if you are pregnant or breastfeeding, take prescription
    medicines, have a health condition or are having surgery. Some herbs, such as
    St. John's wort, change how medicines work.

    - The FDA doesn't approve dietary supplements for safety or effectiveness before
      they are sold.
    - Label data comes from the NIH Dietary Supplement Label Database as companies
      submitted it, and can contain entry errors. Check the product's own label.
    - Stack totals count supplements only, not food, and compare them with adult
      reference amounts that may not apply to you.
    - Ingredient details are short summaries of public sources and can leave out
      risks. Each one links to its full source.

    This app isn't affiliated with or endorsed by the NIH, the FDA or Health Canada.
    """,
    icon="⚠️",
)
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
    - Search by product name and browse the matching products in a table  
    - Filter by brand and supplement form (only the ones that match your search)  
    - Look up products by barcode  
    - View product labels, factsheets, and ingredient lists  
    - Explore related products from the same brand  
    """
)

st.subheader("2. Ingredient Metadata Explorer")
st.write(
    """
    Dive into ingredient-level information from official sources: the **NIH Office of
    Dietary Supplements (ODS)**, the **NIH National Center for Complementary and Integrative
    Health (NCCIH)** and **Health Canada** natural health product monographs.
    You can:
    - Explore ingredients by health goal  
    - Filter by mechanism and category  
    - Visualize mechanism → compound networks  
    - Read safety, interaction, and RDA/UL summaries  
    """
)

st.subheader("3. Supplement Stack Checker")
st.write(
    """
    Add up the vitamins and minerals in the supplements you take.
    You can:
    - Build a stack of products and set servings per day  
    - Add products from the Label Explorer or an ingredient's product list  
    - See each nutrient's daily total against the adult RDA and upper limit  
    - Bookmark or share the stack with its link  
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
    Evidence-based fact sheets, recommended amounts and upper limits.  
    [https://ods.od.nih.gov](https://ods.od.nih.gov)

    **NIH National Center for Complementary and Integrative Health (NCCIH)**  
    Fact sheets on herbs and other complementary products.  
    [https://www.nccih.nih.gov/health/herbsataglance](https://www.nccih.nih.gov/health/herbsataglance)

    **Health Canada Natural Health Product monographs**  
    Approved uses, doses and warnings for natural health products.  
    [https://webprod.hc-sc.gc.ca/nhpid-bdipsn/monosReq?lang=eng](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/monosReq?lang=eng)

    A few ingredients use the Linus Pauling Institute at Oregon State University or
    Memorial Sloan Kettering's About Herbs instead.
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
    "This app integrates DSLD product data and ingredient metadata from official sources to provide a unified, "
    "interactive exploration experience for supplements and their components."
)

from urllib.parse import quote

import streamlit as st
import pandas as pd
from streamlit_echarts import st_echarts

from utils.dsld_helpers import dose_unit, products_with_compound
from utils.stack_state import add_to_stack


from utils.ingredient_helpers import (
    load_ontology,
    load_metadata,
    load_mechanism_metadata,
    safe_str,
    safe_json,
    CATEGORY_COLORS,
    extract_all_health_goals,
    mechanisms_for_goal,
    build_echarts_graph

)

SOURCE_LABELS = {
    "ODS": "NIH Office of Dietary Supplements fact sheet",
    "ODS_GROUP": "NIH Office of Dietary Supplements fact sheet",
    "NCCIH": "NIH National Center for Complementary and Integrative Health",
    "HEALTH_CANADA": "Health Canada monograph",
    "LPI": "Linus Pauling Institute, Oregon State University",
    "MSK": "Memorial Sloan Kettering, About Herbs",
}

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Ingredient Metadata Explorer",
    layout="wide",
)

st.title("🧬 Supplement Ingredient Metadata Explorer")
st.write(
    "Explore mechanisms, categories, health goals, and NIH ODS metadata for "
    "common dietary supplement ingredients."
)
st.caption(
    "Ingredient details come from NIH (ODS and NCCIH), Health Canada monographs, "
    "the Linus Pauling Institute at Oregon State University, and Memorial Sloan "
    "Kettering. Some ingredients have no official or credible summary yet."
)
st.caption(
    "For information only, not medical advice. Talk to a doctor or pharmacist "
    "before starting a supplement."
)

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
ontology = load_ontology()
metadata = load_metadata()
mech_meta = load_mechanism_metadata()

# Merge mechanism metadata into ontology
ontology = ontology.merge(mech_meta, on="mechanism", how="left")

# A compound linked from the label explorer (?compound=...)
linked_compound = st.query_params.get("compound")
if linked_compound not in set(ontology["compound"]):
    linked_compound = None
elif linked_compound:
    st.info(f"Showing **{linked_compound}**. Scroll down to Compound Details.")

# ---------------------------------------------------------
# TOP‑LEVEL FILTER: HEALTH GOAL
# ---------------------------------------------------------
st.markdown("## 🎯 Filter by Health Goal")

selected_goals = st.multiselect(
    "Select one or more health goals:",
    extract_all_health_goals(ontology),
    default=[],
)

if not selected_goals:
    goal_filtered = ontology.copy()
else:
    mech_sets = [mechanisms_for_goal(ontology, g) for g in selected_goals]
    combined_mechs = set().union(*mech_sets)
    goal_filtered = ontology[ontology["mechanism"].isin(combined_mechs)]

# ---------------------------------------------------------
# SECONDARY FILTERS: CATEGORY + MECHANISM
# ---------------------------------------------------------
st.markdown("## 🔍 Refine by Category and Mechanism")

col1, col2 = st.columns(2)

with col1:
    categories = sorted(goal_filtered["category"].unique())
    selected_categories = st.multiselect(
        "Category",
        categories,
        default=categories,
    )

with col2:
    mechanisms = sorted(goal_filtered["mechanism"].unique())
    selected_mechanisms = st.multiselect(
        "Mechanism",
        mechanisms,
    )

filtered = goal_filtered.copy()

if selected_categories:
    filtered = filtered[filtered["category"].isin(selected_categories)]

if selected_mechanisms:
    filtered = filtered[filtered["mechanism"].isin(selected_mechanisms)]

if filtered.empty:
    st.warning("No results for the selected filters.")
    st.stop()

# Merge with metadata
merged = filtered.merge(metadata, on=["compound", "category"], how="left")

# Table
with st.expander("View Filtered Results"):
    table = merged[["mechanism", "category", "compound"]].drop_duplicates()
    st.dataframe(table, width="stretch", hide_index=True)

# ECharts Graph
with st.expander("Mechanism → Compound Graph"):
    st.subheader("Mechanism → Compound Graph")
    # Legend
    st.markdown("### Legend")
    legend_cols = st.columns(4)
    for i, (cat, color) in enumerate(CATEGORY_COLORS.items()):
        with legend_cols[i % 4]:
            st.markdown(
                f"""
                    <div style="display:flex;align-items:center;margin-bottom:6px;">
                        <div style="width:16px;height:16px;background:{color};
                                    border-radius:3px;margin-right:8px;"></div>
                        <span>{cat}</span>
                    </div>
                    """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Build ECharts graph data
    nodes, links = build_echarts_graph(filtered, CATEGORY_COLORS)

    if not nodes or not links:
        st.warning("No graph data available for the selected filters.")
    else:
        options = {
            "tooltip": {
            "show": True,
            "formatter": "{b}<br/>{c}"
            },
            "series": [
                {
                    "type": "graph",
                    "layout": "force",
                    "roam": True,
                    "draggable": True,
                    "focusNodeAdjacency": True,
                    "force": {"repulsion": 200, "edgeLength": 120},
                    "label": {"show": True, "position": "right"},
                    "data": nodes,
                    "links": links,
                    "categories": [
                        {"name": "Mechanisms"},
                        {"name": "Compounds"},
                    ],
                }
            ],
        }

        st_echarts(options=options, height="650px")

# ---------------------------------------------------------
# Show Compound Details
# ---------------------------------------------------------

st.subheader("Compound Details")

compounds = sorted(merged["compound"].unique())
selected = st.selectbox(
    "Select a compound",
    compounds,
    index=compounds.index(linked_compound) if linked_compound in compounds else 0,
)

row = merged[merged["compound"] == selected].iloc[0]

tab_overview, tab_safety, tab_interactions, tab_rda = st.tabs(
    ["Overview", "Safety", "Interactions", "RDA / UL"]
)

# ---------------------------------------------------------
# OVERVIEW TAB
# ---------------------------------------------------------
with tab_overview:
    st.markdown(f"### {selected}")
    st.markdown(f"**Category:** {row['category']}")

    # Mechanisms & descriptions
    compound_mechs = merged[merged["compound"] == selected][
        ["mechanism", "description", "group", "health_goals"]
    ].drop_duplicates()

    if not compound_mechs.empty:
        st.markdown("### Mechanisms & Functionality")
        for _, mech_row in compound_mechs.iterrows():
            mech = mech_row["mechanism"]
            desc = safe_str(mech_row["description"])
            group = safe_str(mech_row["group"])
            goals = safe_str(mech_row["health_goals"])

            st.markdown(f"- **{mech}** — {desc}")
            if group:
                st.caption(f"Group: {group}")
            if goals:
                st.caption(f"Health goals: {goals}")

    # Source metadata
    pf = safe_str(row.get("primary_functions"))
    if pf:
        st.markdown(f"**Primary functions:** {pf}")

    fs = safe_str(row.get("food_sources"))
    if fs:
        st.markdown(f"**Food sources:** {fs}")

    url = safe_str(row.get("source_url"))
    source = safe_str(row.get("source_type"))

    dose = safe_str(row.get("typical_supplement_range"))
    if dose:
        st.markdown(f"**Dose ({SOURCE_LABELS.get(source, 'source')}):** {dose}")
    if url.startswith("http"):
        label = SOURCE_LABELS.get(source, "Source")
        st.markdown(f"Source: [{label}]({url})")
    elif not pf:
        st.info("No official or credible summary found for this ingredient yet.")

# ---------------------------------------------------------
# SAFETY TAB
# ---------------------------------------------------------
with tab_safety:
    safety = safe_str(row.get("safety_overview"))
    st.markdown(safety or "No safety data available.")

# ---------------------------------------------------------
# INTERACTIONS TAB
# ---------------------------------------------------------
with tab_interactions:
    inter = safe_str(row.get("interactions_summary"))
    st.markdown(inter or "No interaction data available.")

# ---------------------------------------------------------
# RDA / UL TAB
# ---------------------------------------------------------
with tab_rda:
    rda = safe_json(row.get("rda_json"))
    ul = safe_json(row.get("ul_json"))

    if rda:
        st.markdown("#### RDA / AI")
        st.table(pd.DataFrame(rda))
    else:
        st.info("No RDA / AI data.")

    if ul:
        st.markdown("#### UL")
        st.table(pd.DataFrame(ul))
    else:
        st.info(
            "No upper limit (UL) in this dataset. Some nutrients have no UL, "
            "and others were not captured; check the fact sheet linked in the Overview tab."
        )

    if rda or ul:
        st.caption("Values from NIH ODS fact sheets.")

# ---------------------------------------------------------
# PRODUCTS WITH THIS COMPOUND
# ---------------------------------------------------------
PRODUCT_LIMIT = 100

st.markdown(f"### Products with {selected}")
products = products_with_compound(selected)
if products.empty:
    st.info("No products in the label database list this ingredient under a name we recognise yet.")
else:
    col_market, col_sort = st.columns(2)
    with col_market:
        on_market = st.checkbox("On the market only", value=True)
    with col_sort:
        sort_by = st.radio(
            "Sort by", ["Highest dose", "Lowest dose", "Product name"], horizontal=True
        )

    shown = products[products["Market Status"] == "On Market"] if on_market else products

    # Brands that sell this ingredient, biggest first. The counts are part
    # of each option's label and a multiselect loses its value when its
    # labels change, so the widget's key follows the counts and the choice
    # is kept under its own key.
    brand_counts = shown["Brand"].value_counts()
    choice_key = f"brands_{selected}"
    chosen_brands = [b for b in st.session_state.get(choice_key, []) if b in brand_counts]
    widget_key = f"{choice_key}_{on_market}"

    def remember_brands():
        st.session_state[choice_key] = st.session_state[widget_key]

    st.multiselect(
        "Brands",
        list(brand_counts.index),
        default=chosen_brands,
        key=widget_key,
        on_change=remember_brands,
        format_func=lambda b: f"{b} ({brand_counts[b]:,})",
        placeholder=f"All {len(brand_counts):,} brands",
        help="Show only these brands' products. Brands are listed by how many "
        "products they sell with this ingredient.",
    )
    if chosen_brands:
        shown = shown[shown["Brand"].isin(chosen_brands)]
    if sort_by == "Lowest dose":
        shown = shown.sort_values("Dose", ascending=True, na_position="last")
    elif sort_by == "Product name":
        shown = shown.sort_values("Product", key=lambda s: s.str.lower())
    total = len(shown)
    shown = shown.head(PRODUCT_LIMIT).copy()

    unit = dose_unit(selected)
    st.caption(
        f"Showing {len(shown):,} of {total:,} products. Dose is the amount per serving "
        f"in {unit}; it is left blank when the label's unit doesn't convert, when a "
        "mineral is named as a salt (the amount may be the whole salt), or when the "
        "amount looks like a unit error on the label. Label data comes from the NIH DSLD "
        "and can contain entry errors, so check the label before relying on a number."
    )
    shown["Label"] = shown["DSLD ID"].map(
        lambda i: f"Dietary_Supplement_Label_Explorer?dsld_id={quote(str(i))}"
    )
    columns = ["Label", "Product", "Brand", "Listed as", "Label amount", "Dose",
               "% of adult RDA", "Upper limit"]
    if not on_market:
        columns.insert(3, "Market Status")
    if not (shown["% of adult RDA"].ne("").any() or shown["Upper limit"].ne("").any()):
        columns = [c for c in columns if c not in ("% of adult RDA", "Upper limit")]
    selection = st.dataframe(
        shown[columns],
        hide_index=True,
        width="stretch",
        key=f"products_{selected}_{on_market}_{sort_by}_{chosen_brands}",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Label": st.column_config.LinkColumn(
                "Label", help="Opens the product in the Label Explorer", display_text="Open",
                width="small",
            ),
            "Product": st.column_config.TextColumn(width="medium"),
            "Dose": st.column_config.NumberColumn(f"Dose ({unit})", format="localized"),
            "% of adult RDA": st.column_config.TextColumn(
                help="Amount per serving as a share of the NIH recommended amount for adults 19+",
            ),
            "Upper limit": st.column_config.TextColumn(
                help="Whether one serving goes over the NIH upper limit for adults 19+",
            ),
        },
    )
    chosen = shown["DSLD ID"].iloc[selection.selection.rows].tolist()
    if st.button(
        f"➕ Add {len(chosen)} selected to stack" if chosen
        else "➕ Tick products in the table to add them to your stack",
        disabled=not chosen,
        help="Select products with the boxes at the left of the table, then add them "
        "to the Supplement Stack Checker",
    ):
        add_to_stack(chosen)

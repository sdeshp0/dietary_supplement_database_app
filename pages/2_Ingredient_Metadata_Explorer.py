import streamlit as st
import pandas as pd
from pathlib import Path
from streamlit.components.v1 import html

from utils.ingredient_helpers import (
    load_ontology,
    load_metadata,
    load_mechanism_metadata,
    build_graph,
    safe_str,
    safe_json,
    CATEGORY_COLORS,
    extract_all_health_goals,
    mechanisms_for_goal,
)

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
st.caption("*Note that detailed information is currently only available for Vitamins and Minerals")

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
ontology = load_ontology()
metadata = load_metadata()
mech_meta = load_mechanism_metadata()

# Merge mechanism metadata into ontology
ontology = ontology.merge(mech_meta, on="mechanism", how="left")

# ---------------------------------------------------------
# TOP‑LEVEL FILTER: HEALTH GOAL
# ---------------------------------------------------------
st.markdown("## 🎯 Filter by Health Goal")

all_goals = ["All"] + extract_all_health_goals(ontology)

selected_goal = st.selectbox(
    "Select a health goal to explore:",
    all_goals,
    index=0,
)

# Apply health‑goal filter
if selected_goal == "All":
    goal_filtered = ontology.copy()
else:
    goal_mechs = mechanisms_for_goal(ontology, selected_goal)
    goal_filtered = ontology[ontology["mechanism"].isin(goal_mechs)]

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
    st.dataframe(table, use_container_width=True, hide_index=True)

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

    # Graph
    net = build_graph(filtered)
    out = Path("ingredient_graph.html")
    net.write_html(str(out))
    html(out.read_text(), height=650)

# ---------------------------------------------------------
# Show Compound Details
# ---------------------------------------------------------

st.subheader("Compound Details")

compounds = sorted(merged["compound"].unique())
selected = st.selectbox("Select a compound", compounds)

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

    # ODS metadata
    pf = safe_str(row.get("primary_functions"))
    if pf:
        st.markdown(f"**Primary functions:** {pf}")

    fs = safe_str(row.get("food_sources"))
    if fs:
        st.markdown(f"**Food sources:** {fs}")

    tsr = safe_str(row.get("typical_supplement_range"))
    if tsr:
        st.markdown(f"**Typical supplement-related values:** {tsr}")

    url = safe_str(row.get("ods_url"))
    if url.startswith("http"):
        st.markdown(f"[ODS Fact Sheet]({url})")

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
        st.info("No UL data.")

    st.caption("Values from NIH ODS fact sheets.")

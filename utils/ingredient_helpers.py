import json
from pathlib import Path
import pandas as pd
import streamlit as st


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"

ONTOLOGY_CSV = DATA_DIR / "supplement_ontology.csv"
METADATA_CSV = DATA_DIR / "compound_metadata.csv"
MECHANISM_META_CSV = DATA_DIR / "mechanism_metadata.csv"


# ---------------------------------------------------------
# CATEGORY COLORS (shared legend)
# ---------------------------------------------------------
CATEGORY_COLORS = {
    "Vitamin": "#FF9800",
    "Mineral": "#03A9F4",
    "Amino acid": "#9C27B0",
    "Fatty acid": "#009688",
    "Macronutrient": "#795548",
    "Herb": "#8BC34A",
    "Bioactive": "#E91E63",
    "Enzyme": "#607D8B",
    "Other": "#9E9E9E",
}


# ---------------------------------------------------------
# SAFE HELPERS
# ---------------------------------------------------------
def safe_str(x):
    """
    Converts a value into a clean string, removing NaN/None/null.
    """
    if x is None:
        return ""
    if isinstance(x, float):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def safe_json(x):
    """
    Safely loads JSON from a string field.
    Returns None if parsing fails.
    """
    s = safe_str(x)
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


# ---------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------
@st.cache_data
def load_ontology():
    """
    Loads supplement_ontology.csv and normalizes key columns.
    """
    df = pd.read_csv(ONTOLOGY_CSV, encoding="utf-8")
    for col in ["mechanism", "category", "compound"]:
        df[col] = df[col].astype(str).str.strip()
    return df


@st.cache_data
def load_metadata():
    """
    Loads compound_metadata.csv and strips whitespace.
    """
    df = pd.read_csv(METADATA_CSV, encoding="utf-8")
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    return df


@st.cache_data
def load_mechanism_metadata():
    """
    Loads mechanism_metadata.csv and normalizes mechanism names.
    """
    df = pd.read_csv(MECHANISM_META_CSV, encoding="utf-8")
    df["mechanism"] = df["mechanism"].astype(str).str.strip()
    return df


# ---------------------------------------------------------
# HEALTH GOAL UTILITIES
# ---------------------------------------------------------
def extract_all_health_goals(ontology_df):
    """
    Extracts all unique health goals from the ontology table.
    """
    goals = set()

    for val in ontology_df["health_goals"].dropna():
        parts = [g.strip() for g in val.split(",") if g.strip()]
        goals.update(parts)

    return sorted(goals)


def mechanisms_for_goal(ontology_df, goal):
    """
    Returns all mechanisms associated with a given health goal.
    """
    mask = ontology_df["health_goals"].str.contains(goal, na=False)
    return sorted(ontology_df[mask]["mechanism"].unique())


def compounds_for_mechanisms(ontology_df, mechanisms):
    """
    Returns all compounds linked to a list of mechanisms.
    """
    return sorted(
        ontology_df[ontology_df["mechanism"].isin(mechanisms)]["compound"].unique()
    )


# ---------------------------------------------------------
# ECHARTS GRAPH BUILDER
# ---------------------------------------------------------
def build_echarts_graph(df, category_colors):
    """
    Build node and link structures for an ECharts force-directed graph.
    Includes mechanism descriptions for hover tooltips.
    """
    nodes = []
    links = []

    # Mechanism nodes
    for mech in df["mechanism"].dropna().unique():
        mech = str(mech)
        desc = df.loc[df["mechanism"] == mech, "description"].dropna().unique()
        desc = desc[0] if len(desc) else "No description available."

        nodes.append({
            "name": mech,
            "category": 0,
            "symbolSize": 40,
            "itemStyle": {"color": "#4C72B0"},
            "value": desc,   # <-- tooltip content
        })

    # Compound nodes
    for comp in df["compound"].dropna().unique():
        comp = str(comp)
        cat = df.loc[df["compound"] == comp, "category"].iloc[0]
        color = category_colors.get(cat, "#DD8452")

        nodes.append({
            "name": comp,
            "category": 1,
            "symbolSize": 25,
            "itemStyle": {"color": color},
            #"value": f"Compound: {comp}",  # simple tooltip
        })

    # Edges
    for _, row in df.iterrows():
        mech = row.get("mechanism")
        comp = row.get("compound")
        if pd.notna(mech) and pd.notna(comp):
            links.append({
                "source": str(mech),
                "target": str(comp),
            })

    return nodes, links


from urllib.parse import quote

import pandas as pd
import streamlit as st

from utils.dsld_helpers import search_products, stack_product
from utils.stack import (MAX_SERVINGS, StackItem, format_stack, parse_stack,
                         stack_other_ingredients, stack_totals)
from utils.stack_state import current_stack, remember_stack

SEARCH_RESULTS = 20


def details_link(compound):
    """Link to the compound's entry in the Ingredient Metadata Explorer."""
    return f"Ingredient_Metadata_Explorer?compound={quote(compound)}"


DETAILS_COLUMN = st.column_config.LinkColumn(
    "Ingredient details",
    help="Opens this ingredient in the Ingredient Metadata Explorer",
    display_text="Details",
)

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Supplement Stack Checker",
    layout="wide",
)

st.title("🧮 Supplement Stack Checker")
st.write(
    "Add the supplements you take to see how much of each vitamin and mineral they "
    "add up to per day, compared with the NIH recommended amount and upper limit for adults."
)
st.caption(
    "For information only, not medical advice. Talk to a doctor or pharmacist "
    "before starting a supplement."
)


# ---------------------------------------------------------
# THE STACK, KEPT IN THE PAGE LINK (?stack=ID:servings,...)
# ---------------------------------------------------------
def save_stack(items):
    remember_stack(items)
    if items:
        st.query_params["stack"] = format_stack(items)
    elif "stack" in st.query_params:
        del st.query_params["stack"]
    st.rerun()


# The link wins; without one (opened from the menu) the stack built earlier
# in this visit is restored
if "stack" in st.query_params:
    stack = parse_stack(st.query_params["stack"])
else:
    stack = current_stack()
stack = [item for item in stack if stack_product(item.dsld_id) is not None]
remember_stack(stack)
if stack and st.query_params.get("stack") != format_stack(stack):
    st.query_params["stack"] = format_stack(stack)

# ---------------------------------------------------------
# SIDEBAR: ADD A PRODUCT
# ---------------------------------------------------------
st.sidebar.subheader("➕ Add a product")
search_name = st.sidebar.text_input("Search by product name:", "")
if search_name:
    results = search_products(name=search_name, limit=SEARCH_RESULTS)
    if results.empty:
        st.sidebar.info("No products match your search.")
    in_stack = {item.dsld_id for item in stack}
    for _, row in results.iterrows():
        dsld_id = int(row["DSLD ID"])
        label = f"{row['Product Name']} ({row['Brand Name']})"
        if dsld_id in in_stack:
            st.sidebar.caption(f"✓ {label}")
        elif st.sidebar.button(label, key=f"add_{dsld_id}"):
            save_stack(stack + [StackItem(dsld_id, 1.0)])

if not stack:
    st.info("Search for a product in the sidebar to start your stack.")
    st.stop()

# ---------------------------------------------------------
# PRODUCTS IN THE STACK
# ---------------------------------------------------------
st.markdown("### Your stack")
products = {item.dsld_id: stack_product(item.dsld_id) for item in stack}
stack_table = pd.DataFrame({
    "Label": [f"Dietary_Supplement_Label_Explorer?dsld_id={quote(str(i.dsld_id))}" for i in stack],
    "Product": [products[i.dsld_id]["name"] for i in stack],
    "Brand": [products[i.dsld_id]["brand"] for i in stack],
    "One serving": [products[i.dsld_id]["serving"] for i in stack],
    "Servings per day": [i.servings for i in stack],
    "Remove": [False] * len(stack),
})
edited = st.data_editor(
    stack_table,
    # A new key whenever the stack changes, so edits never carry over to a different stack
    key=f"stack_{format_stack(stack)}",
    hide_index=True,
    width="stretch",
    disabled=["Label", "Product", "Brand", "One serving"],
    column_config={
        "Label": st.column_config.LinkColumn(display_text="Open", width="small"),
        "Product": st.column_config.TextColumn(width="medium"),
        "One serving": st.column_config.TextColumn(
            help="The serving the label's amounts are for. Where a label gives amounts "
            "for several serving sizes, the one for adults is used.",
        ),
        "Servings per day": st.column_config.NumberColumn(
            help="For a weekly dose, such as 50,000 IU of vitamin D once a week, use 0.14",
            min_value=0.1, max_value=MAX_SERVINGS, step=0.01, format="%.2g",
        ),
    },
)
new_stack = [
    StackItem(item.dsld_id, float(servings))
    for item, servings, remove in zip(stack, edited["Servings per day"], edited["Remove"])
    if not remove and pd.notna(servings)
]
if new_stack != stack:
    save_stack(new_stack)

st.caption("The link to this page keeps your stack, so you can bookmark or share it.")

# ---------------------------------------------------------
# TOTALS PER DAY
# ---------------------------------------------------------
totals, not_counted = stack_totals(
    [(products[i.dsld_id]["name"], i.servings, products[i.dsld_id]["doses"]) for i in stack]
)

st.markdown("### Total per day")
if totals.empty:
    st.info(
        "None of these products list a vitamin or mineral with an NIH recommended "
        "amount or upper limit that we can add up."
    )
else:
    over = totals[totals["Upper limit"].str.startswith("Over the limit")]
    some = totals[totals["Upper limit"].str.startswith("Over for some")]
    if not over.empty:
        st.warning(
            "Over the adult upper limit: " + ", ".join(over["Nutrient"]) + ". "
            "Check with a doctor or pharmacist before taking these together."
        )
    elif not some.empty:
        st.warning("Over the upper limit for some adults: " + ", ".join(some["Nutrient"]) + ".")
    else:
        st.success("No nutrient in this stack goes over the adult upper limit.")

    # Over-the-limit nutrients first, then by name
    rank = totals["Upper limit"].map(
        lambda s: 0 if s.startswith("Over the limit") else 1 if s.startswith("Over") else 2
    )
    totals = totals.assign(_rank=rank).sort_values(["_rank", "Nutrient"]).drop(columns="_rank")
    totals.insert(1, "Details", totals["Nutrient"].map(details_link))
    st.dataframe(
        totals,
        hide_index=True,
        width="stretch",
        column_config={
            "Details": DETAILS_COLUMN,
            "% of adult RDA": st.column_config.TextColumn(
                help="Daily total as a share of the recommended amount for adults",
            ),
            "Upper limit": st.column_config.TextColumn(
                help="Whether the daily total goes over the adult tolerable upper intake level",
                width="medium",
            ),
            "From": st.column_config.TextColumn(
                help="Each product's share of the daily total", width="large",
            ),
        },
    )
    st.caption(
        "RDA and upper limit are NIH Office of Dietary Supplements values for adults 19 "
        "and older, not pregnant or breastfeeding; a range covers the differences between "
        "men and women and between age groups. Totals count these supplements only, not "
        "food. Beta-carotene counts toward vitamin A but not toward its upper limit. "
        "Caffeine is compared with the FDA's 400 mg a day for most healthy adults. Label "
        "data comes from the NIH DSLD and can contain entry errors."
    )

# ---------------------------------------------------------
# OTHER INGREDIENTS (no RDA or upper limit to add up against)
# ---------------------------------------------------------
others = stack_other_ingredients(
    [(products[i.dsld_id]["name"], products[i.dsld_id]["other"]) for i in stack]
)
if not others.empty:
    st.markdown("### Other ingredients")
    st.caption(
        "Herbs and other ingredients with no NIH recommended amount or upper limit, "
        "so they aren't added up. Amounts are per serving, as on the label."
    )
    others.insert(1, "Details", others["Ingredient"].map(details_link))
    st.dataframe(
        others,
        hide_index=True,
        width="stretch",
        column_config={
            "Details": DETAILS_COLUMN,
            "From": st.column_config.TextColumn(
                help="Each product's label rows for this ingredient", width="large",
            ),
        },
    )

if not not_counted.empty:
    with st.expander(f"Not counted ({len(not_counted)} label rows)"):
        st.dataframe(not_counted, hide_index=True, width="stretch")
        st.caption(
            "\"Weight of the whole salt\": a mineral or caffeine named as a salt, such as "
            "magnesium citrate, may list "
            "the weight of the whole salt, so it isn't added. \"Part of the total above it\": "
            "the label lists a form (beta-carotene) under its total (vitamin A), which is "
            "counted instead."
        )

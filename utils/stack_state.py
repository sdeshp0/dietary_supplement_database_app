"""
Keeps a visitor's supplement stack while they move between pages, so the
Label Explorer and Ingredient Explorer can add products to it. The Stack
Checker's link (?stack=...) stays the shareable copy.
"""

import streamlit as st

from utils.stack import StackItem, format_stack

STACK_PAGE = "pages/3_Supplement_Stack_Checker.py"


def current_stack():
    return list(st.session_state.get("stack", []))


def remember_stack(items):
    st.session_state["stack"] = list(items)


def in_stack(dsld_id):
    return any(item.dsld_id == dsld_id for item in current_stack())


def open_stack():
    st.switch_page(STACK_PAGE, query_params={"stack": format_stack(current_stack())})


def add_to_stack(dsld_ids):
    """Adds products (one serving a day) and opens the Stack Checker."""
    items = current_stack()
    present = {item.dsld_id for item in items}
    items += [StackItem(int(i), 1.0) for i in dict.fromkeys(dsld_ids) if int(i) not in present]
    remember_stack(items)
    open_stack()

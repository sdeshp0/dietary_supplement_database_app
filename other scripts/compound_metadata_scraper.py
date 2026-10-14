"""
Builds data/compound_metadata.csv from the sources in data/compound_sources.csv.

Run from anywhere:  python "other scripts/compound_metadata_scraper.py"

Sources:
- ODS: the official ODS Fact Sheet API (XML), not the HTML pages, which
  reject scripted requests with 403.
- NCCIH: "Herbs at a Glance" pages, split on their h2 sections.
- PUBCHEM: the PUG REST description endpoint (the compound web pages are
  rendered by JavaScript, so scraping them returned nothing).

MedlinePlus herb and supplement monographs were retired on 2025-07-29, so
those rows are skipped. If a compound fails to fetch, its previous row in
compound_metadata.csv is kept rather than overwritten with an error.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from urllib.parse import quote, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# GLOBAL HELPERS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"

HEADERS = {
    "User-Agent": (
        "dietary-supplement-database-app/1.0 "
        "(+https://github.com/sdeshp0/dietary_supplement_database_app)"
    ),
    "Accept": "text/html,application/xml,application/json;q=0.9,*/*;q=0.8",
}
REQUEST_DELAY_S = 1.0  # be polite: one request per second

ODS_API = "https://ods.od.nih.gov/api/index.aspx"
PUBCHEM_DESCRIPTION = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/description/JSON"

COLUMNS = [
    "compound", "category", "source_type", "source_url",
    "primary_functions", "food_sources", "safety_overview", "interactions_summary",
    "rda_json", "ul_json", "typical_supplement_range", "notes",
]

session = requests.Session()
session.headers.update(HEADERS)


def fetch(url, params=None):
    time.sleep(REQUEST_DELAY_S)
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r


def clean_space(text):
    return re.sub(r"\s+", " ", text).strip()


def empty_record(compound, category, source_type, url, notes):
    record = dict.fromkeys(COLUMNS)
    record.update(compound=compound, category=category, source_type=source_type,
                  source_url=url, notes=notes)
    return record


def extract_section(soup, keywords):
    """
    Text of the first h2/h3 section whose heading contains a keyword, up to
    the next h2/h3. Works whether the section's paragraphs are siblings of
    the heading or nested in wrappers.
    """
    for h in soup.find_all(["h2", "h3"]):
        if not any(k.lower() in h.get_text(" ", strip=True).lower() for k in keywords):
            continue
        content = []
        for el in h.find_all_next(["h2", "h3", "p", "ul", "ol"]):
            if el.name in ["h2", "h3"]:
                break
            if el.find_parent(["ul", "ol", "table"]):
                continue  # already included with its list, or part of a table
            content.append(el.get_text(" ", strip=True))
        if content:
            return clean_space(" ".join(content))
    return None


def extract_table(soup, header_keywords):
    """
    Records of the first table whose column headers contain a keyword.
    Matching on headers (not the whole table text) keeps "ul" in "Adults"
    from selecting the RDA table as the UL table.
    """
    for table in soup.find_all("table"):
        try:
            df = pd.read_html(StringIO(str(table)))[0]
        except Exception:
            continue
        df.columns = [clean_space(str(c)) for c in df.columns]
        headers = " ".join(df.columns).lower()
        if any(k.lower() in headers for k in header_keywords):
            return df.to_dict(orient="records")
    return None


def to_json(records):
    return json.dumps(records) if records else None


# ---------------------------------------------------------
# ODS (Vitamins, Minerals, a few botanicals) via the Fact Sheet API
# ---------------------------------------------------------
def ods_resource_name(url):
    """
    https://ods.od.nih.gov/factsheets/VitaminD-Consumer/ -> VitaminD
    """
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return re.sub(r"-(Consumer|HealthProfessional)$", "", slug, flags=re.I)


def scrape_ods(url, compound, category):
    resource = ods_resource_name(url)
    r = fetch(ODS_API, params={
        "resourcename": resource,
        "readinglevel": "Consumer",
        "outputformat": "XML",
    })

    root = ET.fromstring(r.content)
    error = root.find(".//{*}ErrorMessage")
    if error is not None and error.text:
        raise ValueError(f"ODS API error for {resource}: {error.text}")

    content = root.find(".//{*}Content")
    if content is None or not (content.text or "").strip():
        raise ValueError(f"ODS API returned no content for {resource}")

    soup = BeautifulSoup(content.text, "html.parser")

    record = empty_record(compound, category, "ODS", url,
                          f"ODS Fact Sheet API (resourcename={resource}, Consumer)")
    record.update(
        primary_functions=extract_section(soup, ["what is", "what does"]),
        food_sources=extract_section(soup, ["what foods", "food sources"]),
        safety_overview=extract_section(soup, ["harmful", "safety", "too much"]),
        interactions_summary=extract_section(soup, ["interact"]),
        rda_json=to_json(extract_table(soup, ["recommended amount", "adequate intake"])),
        ul_json=to_json(extract_table(soup, ["upper limit"])),
    )
    return record


# ---------------------------------------------------------
# NCCIH (Herbs, Botanicals, Mushrooms)
# ---------------------------------------------------------
def scrape_nccih(url, compound, category):
    soup = BeautifulSoup(fetch(url).text, "html.parser")

    record = empty_record(compound, category, "NCCIH", url, "NCCIH Herbs at a Glance")
    record.update(
        primary_functions=extract_section(soup, ["background", "what have we learned"]),
        safety_overview=extract_section(soup, ["safety"]),
        interactions_summary=extract_section(soup, ["keep in mind"]),
    )
    return record


# ---------------------------------------------------------
# PUBCHEM (fallback for single compounds) via PUG REST
# ---------------------------------------------------------
def scrape_pubchem(url, compound, category):
    name = urlparse(url).path.rstrip("/").split("/")[-1].replace("-", " ")
    data = fetch(PUBCHEM_DESCRIPTION.format(quote(name))).json()

    descriptions = [
        info["Description"]
        for info in data.get("InformationList", {}).get("Information", [])
        if info.get("Description")
    ]

    record = empty_record(compound, category, "PUBCHEM", url, "PubChem compound description")
    record["primary_functions"] = descriptions[0] if descriptions else None
    return record


# ---------------------------------------------------------
# ROUTER
# ---------------------------------------------------------
SCRAPERS = {
    "ODS": scrape_ods,
    "NCCIH": scrape_nccih,
    "PUBCHEM": scrape_pubchem,
}


def scrape_row(row):
    compound = row["compound"]
    category = row["category"]
    source_type = row["source_type"].upper()
    url = row["source_url"]

    scraper = SCRAPERS.get(source_type)
    if scraper is None:
        raise ValueError(f"No scraper for {source_type} (MedlinePlus monographs were retired)")

    print(f"Scraping {compound} ({category}) from {source_type} → {url}")
    return scraper(url, compound, category)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    ontology = pd.read_csv(DATA_DIR / "supplement_ontology.csv", encoding="utf-8")
    ontology["compound"] = ontology["compound"].astype(str).str.strip()
    ontology["category"] = ontology["category"].astype(str).str.strip()
    unique_compounds = ontology[["compound", "category"]].drop_duplicates()

    sources = pd.read_csv(DATA_DIR / "compound_sources.csv", encoding="utf-8")
    sources["compound"] = sources["compound"].astype(str).str.strip()
    sources["category"] = sources["category"].astype(str).str.strip()

    merged = unique_compounds.merge(sources, on=["compound", "category"], how="left")

    missing = merged[merged["source_type"].isna()]
    if not missing.empty:
        print("⚠️ Missing source mappings for:", ", ".join(missing["compound"]))

    to_scrape = merged.dropna(subset=["source_type", "source_url"])

    # Previous results, kept for any compound that fails this run
    metadata_path = DATA_DIR / "compound_metadata.csv"
    previous = {}
    if metadata_path.exists():
        prev_df = pd.read_csv(metadata_path, encoding="utf-8", dtype=str)
        previous = {
            (r["compound"], r["category"]): r.to_dict()
            for _, r in prev_df.iterrows()
        }

    results, failures = [], []
    for _, row in to_scrape.iterrows():
        key = (row["compound"], row["category"])
        try:
            results.append(scrape_row(row))
        except Exception as e:
            print(f"❌ {row['compound']}: {e}")
            failures.append(row["compound"])
            if key in previous:
                results.append(previous[key])
            else:
                results.append(empty_record(row["compound"], row["category"],
                                            row["source_type"], row["source_url"],
                                            f"Error: {e}"))

    meta_df = pd.DataFrame(results, columns=COLUMNS)
    meta_df.to_csv(metadata_path, index=False, encoding="utf-8")

    print(f"\nWrote {len(meta_df)} rows to {metadata_path}")
    print(f"Fetched {len(results) - len(failures)}, failed {len(failures)} (previous data kept)")


if __name__ == "__main__":
    main()

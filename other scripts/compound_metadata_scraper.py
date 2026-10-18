"""
Builds data/compound_metadata.csv from the sources in data/compound_sources.csv.

Run from anywhere:  python "other scripts/compound_metadata_scraper.py"

Sources (official or academic only):
- ODS:           NIH Office of Dietary Supplements Fact Sheet API (XML).
                 The HTML fact sheet pages reject scripted requests with 403.
- ODS_GROUP:     One ingredient's row in a group ODS fact sheet (Exercise and
                 Athletic Performance, Weight Loss), via the same API.
- NCCIH:         NIH National Center for Complementary and Integrative Health.
- HEALTH_CANADA: Health Canada Natural Health Product monographs.
- LPI:           Linus Pauling Institute Micronutrient Information Center
                 (Oregon State University).
- MSK:           Memorial Sloan Kettering "About Herbs" (patient section).
- NONE:          No official or credible monograph found; skipped.

MedlinePlus herb and supplement monographs were retired on 2025-07-29 and
are no longer used. If a compound fails to fetch, its previous row in
compound_metadata.csv is kept when it came from the same URL.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# GLOBAL HELPERS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; dietary-supplement-database-app/1.0; "
        "+https://github.com/sdeshp0/dietary_supplement_database_app)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}
REQUEST_DELAY_S = 1.0  # be polite: at most one request per second

ODS_API = "https://ods.od.nih.gov/api/index.aspx"

COLUMNS = [
    "compound", "category", "source_type", "source_url",
    "primary_functions", "food_sources", "safety_overview", "interactions_summary",
    "rda_json", "ul_json", "typical_supplement_range", "notes",
]

SOURCE_NAMES = {
    "ODS": "NIH Office of Dietary Supplements fact sheet",
    "ODS_GROUP": "NIH Office of Dietary Supplements fact sheet",
    "NCCIH": "NIH National Center for Complementary and Integrative Health",
    "HEALTH_CANADA": "Health Canada Natural Health Product monograph",
    "LPI": "Linus Pauling Institute, Oregon State University",
    "MSK": "Memorial Sloan Kettering Cancer Center, About Herbs",
}

session = requests.Session()
session.headers.update(HEADERS)
_page_cache = {}


def fetch(url, params=None):
    key = (url, tuple(sorted((params or {}).items())))
    if key not in _page_cache:
        time.sleep(REQUEST_DELAY_S)
        r = session.get(url, params=params, timeout=30)
        r.raise_for_status()
        _page_cache[key] = r.content
    return _page_cache[key]


def fetch_soup(url):
    return BeautifulSoup(fetch(url), "html.parser")


def clean_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def empty_record(compound, category, source_type, url, notes):
    record = dict.fromkeys(COLUMNS)
    record.update(compound=compound, category=category, source_type=source_type,
                  source_url=url, notes=notes)
    return record


def page_lines(soup):
    """
    The page's visible text, one block per line, without scripts and styles.
    """
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    lines = (clean_space(line) for line in soup.get_text("\n").split("\n"))
    return [line for line in lines if line]


def _is_heading(line, patterns):
    # Headings are short lines; this keeps a body sentence that happens to
    # start with "Safety ..." from being treated as one.
    return len(line) <= 90 and any(re.match(p, line, flags=re.I) for p in patterns)


def section_text(lines, start_patterns, stop_patterns, max_chars=2500):
    """
    Text between a line matching a start pattern and the next line matching
    a stop pattern. Start patterns are tried in order of preference.
    Patterns are regexes matched at line start. Works on the text, so it
    does not depend on h2/h3/strong markup.
    """
    for start in start_patterns:
        for i, line in enumerate(lines):
            if not _is_heading(line, [start]):
                continue
            body = []
            for nxt in lines[i + 1:]:
                if _is_heading(nxt, stop_patterns):
                    break
                body.append(nxt)
            text = clean_space(" ".join(body))
            if text:
                return text[:max_chars]
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
# ODS via the Fact Sheet API
# ---------------------------------------------------------
def ods_resource_name(url):
    """
    https://ods.od.nih.gov/factsheets/VitaminD-Consumer/ -> VitaminD
    """
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return re.sub(r"-(Consumer|HealthProfessional)$", "", slug, flags=re.I)


def ods_content(url):
    resource = ods_resource_name(url)
    root = ET.fromstring(fetch(ODS_API, params={
        "resourcename": resource,
        "readinglevel": "Consumer",
        "outputformat": "XML",
    }))

    error = root.find(".//{*}ErrorMessage")
    if error is not None and error.text:
        raise ValueError(f"ODS API error for {resource}: {error.text}")

    content = root.find(".//{*}Content")
    if content is None or not (content.text or "").strip():
        raise ValueError(f"ODS API returned no content for {resource}")

    return resource, BeautifulSoup(content.text, "html.parser")


def ods_heading_section(soup, keywords):
    """
    Text of the first h2/h3 section whose heading contains a keyword.
    """
    for h in soup.find_all(["h2", "h3"]):
        if not any(k in h.get_text(" ", strip=True).lower() for k in keywords):
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


def ods_prose_upper_limit(safety_text):
    """
    The adult upper limit when a fact sheet states it in a sentence instead
    of a table, as vitamin E's does ("the upper limit for adults is 1,000 mg/day").
    """
    match = re.search(r"upper limit for adults is ([\d,.]+\s*(?:mcg|mg|g))\b",
                      safety_text or "", flags=re.I)
    if not match:
        return None
    return [{"Ages": "Adults 19 years and older", "Upper Limit": match.group(1)}]


def scrape_ods(row):
    resource, soup = ods_content(row["source_url"])
    record = empty_record(row["compound"], row["category"], "ODS", row["source_url"],
                          f"ODS Fact Sheet API ({resource}, Consumer)")
    safety = ods_heading_section(soup, ["harmful", "safety", "too much"])
    record.update(
        primary_functions=ods_heading_section(soup, ["what is", "what are", "what does"]),
        food_sources=ods_heading_section(soup, ["what foods", "food sources"]),
        safety_overview=safety,
        interactions_summary=ods_heading_section(soup, ["interact"]),
        rda_json=to_json(extract_table(soup, ["recommended amount", "adequate intake"])),
        ul_json=to_json(extract_table(soup, ["upper limit"]) or ods_prose_upper_limit(safety)),
    )
    return record


def scrape_ods_group(row):
    """
    One ingredient's entry from the ingredient table of a group fact sheet.
    The table repeats each ingredient as a name-only row, a content row
    (columns such as "Does it work?", "Is it safe?", "Bottom line") and a
    "Bottom line" repeat, so the entry is the first row with content at or
    after the row whose first cell starts with source_section.
    """
    resource, soup = ods_content(row["source_url"])
    label = row["source_section"].lower()

    def cells_of(tr):
        return [clean_space(c.get_text(" ")) for c in tr.find_all(["th", "td"])]

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = cells_of(rows[0])

        for i, tr in enumerate(rows[1:], start=1):
            cells = cells_of(tr)
            if not cells or not cells[0].lower().startswith(label):
                continue

            content = next(
                (c for c in (cells_of(r) for r in rows[i:i + 3]) if sum(bool(x) for x in c) >= 2),
                None,
            )
            if content is None:
                continue

            primary, safety = [], []
            for col, cell in enumerate(content):
                if not cell:
                    continue
                header = headers[col] if col < len(headers) else ""
                if col == 0 or re.fullmatch(r"ingredients?", header, re.I):
                    primary.insert(0, cell)  # the ingredient's own description
                elif re.search(r"safe|side effect", header, re.I):
                    safety.append(cell)
                else:
                    primary.append(f"{header.capitalize()}: {cell}" if header else cell)

            record = empty_record(row["compound"], row["category"], "ODS_GROUP",
                                  row["source_url"],
                                  f"ODS Fact Sheet API ({resource}, entry: {row['source_section']})")
            record.update(
                primary_functions=" ".join(primary) or None,
                safety_overview=" ".join(safety) or None,
            )
            return record

    raise ValueError(f"No entry starting with '{row['source_section']}' in {resource}")


# ---------------------------------------------------------
# NCCIH
# ---------------------------------------------------------
NCCIH_STOPS = [
    r"how much do we know", r"what have we learned", r"what do we know about safety",
    r"keep in mind", r"for more information", r"key references", r"bottom line",
    r"safety$", r"is (it|\w+) safe", r"what are the side effects", r"tips to consider",
    r"what are the health benefits", r"other references", r"acknowledgments",
]


def scrape_nccih(row):
    lines = page_lines(fetch_soup(row["source_url"]))
    record = empty_record(row["compound"], row["category"], "NCCIH", row["source_url"],
                          SOURCE_NAMES["NCCIH"])
    record.update(
        primary_functions=section_text(
            lines,
            [r"background", r"bottom line", r"what is \w+", r"what are the health benefits"],
            NCCIH_STOPS,
        ),
        safety_overview=section_text(
            lines,
            [r"what do we know about safety", r"safety$", r"is (it|\w+) safe",
             r"what are the side effects"],
            NCCIH_STOPS,
        ),
        interactions_summary=section_text(lines, [r"keep in mind", r"tips to consider"], NCCIH_STOPS),
    )
    return record


# ---------------------------------------------------------
# HEALTH CANADA monographs
# ---------------------------------------------------------
HC_STOPS = [
    r"route of administration", r"dosage form", r"use\(s\)", r"dose\(s\)",
    r"direction\(s\) for use", r"duration\(s\) of use", r"risk information",
    r"caution\(s\) and warning\(s\)", r"contraindication", r"known adverse reaction",
    r"non-medicinal ingredients", r"storage conditions", r"specifications",
    r"references cited", r"references reviewed",
]


def scrape_health_canada(row):
    lines = page_lines(fetch_soup(row["source_url"]))

    risk = [
        section_text(lines, [r"caution\(s\) and warning\(s\)"], HC_STOPS),
        section_text(lines, [r"contraindication"], HC_STOPS),
        section_text(lines, [r"known adverse reaction"], HC_STOPS),
    ]

    record = empty_record(row["compound"], row["category"], "HEALTH_CANADA",
                          row["source_url"], SOURCE_NAMES["HEALTH_CANADA"])
    record.update(
        primary_functions=section_text(lines, [r"use\(s\)"], HC_STOPS),
        safety_overview=" ".join(r for r in risk if r) or None,
        # Some monographs have a "Dose(s)" heading, others start straight
        # with the population, e.g. "Adults 18 years and older"
        typical_supplement_range=section_text(
            lines, [r"dose\(s\)", r"adults \d+ years and older"],
            [p for p in HC_STOPS if p != r"dose\(s\)"],
        ),
    )
    return record


# ---------------------------------------------------------
# LINUS PAULING INSTITUTE (Oregon State University)
# ---------------------------------------------------------
LPI_STOPS = [
    r"summary$", r"introduction$", r"function$", r"metabolism", r"biological activit",
    r"deficiency$", r"disease prevention$", r"disease treatment$", r"sources$",
    r"safety$", r"drug interactions$", r"nutrient interactions$", r"authors and reviewers",
    r"references$", r"get updates from the institute", r"other articles",
    r"figure alternative text", r"intake recommendations",
]


def scrape_lpi(row):
    lines = page_lines(fetch_soup(row["source_url"]))
    record = empty_record(row["compound"], row["category"], "LPI", row["source_url"],
                          SOURCE_NAMES["LPI"])
    record.update(
        primary_functions=section_text(lines, [r"summary$"], LPI_STOPS),
        food_sources=section_text(lines, [r"sources$", r"food sources$"], LPI_STOPS),
        safety_overview=section_text(lines, [r"safety$"], LPI_STOPS),
        interactions_summary=section_text(lines, [r"drug interactions$"], LPI_STOPS),
    )
    return record


# ---------------------------------------------------------
# MEMORIAL SLOAN KETTERING, About Herbs (patient section)
# ---------------------------------------------------------
MSK_STOPS = [
    r"what is it\?", r"what are the potential uses and benefits\?",
    r"what are the side effects\?", r"what else do i need to know\?",
    r"for healthcare professionals", r"disclaimer",
]


def scrape_msk(row):
    lines = page_lines(fetch_soup(row["source_url"]))
    record = empty_record(row["compound"], row["category"], "MSK", row["source_url"],
                          SOURCE_NAMES["MSK"])
    record.update(
        primary_functions=section_text(
            lines, [r"what are the potential uses and benefits\?", r"what is it\?"], MSK_STOPS,
        ),
        safety_overview=section_text(lines, [r"what are the side effects\?"], MSK_STOPS),
        interactions_summary=section_text(lines, [r"what else do i need to know\?"], MSK_STOPS),
    )
    return record


# ---------------------------------------------------------
# ROUTER
# ---------------------------------------------------------
SCRAPERS = {
    "ODS": scrape_ods,
    "ODS_GROUP": scrape_ods_group,
    "NCCIH": scrape_nccih,
    "HEALTH_CANADA": scrape_health_canada,
    "LPI": scrape_lpi,
    "MSK": scrape_msk,
}


def scrape_row(row):
    source_type = row["source_type"].upper()
    print(f"Scraping {row['compound']} from {source_type} → {row['source_url']}")
    record = SCRAPERS[source_type](row)
    if not any(record[c] for c in ["primary_functions", "safety_overview", "rda_json"]):
        raise ValueError("page fetched but no sections were recognised")
    return record


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    ontology = pd.read_csv(DATA_DIR / "supplement_ontology.csv", encoding="utf-8")
    ontology["compound"] = ontology["compound"].astype(str).str.strip()
    ontology["category"] = ontology["category"].astype(str).str.strip()
    unique_compounds = ontology[["compound", "category"]].drop_duplicates()

    sources = pd.read_csv(DATA_DIR / "compound_sources.csv", encoding="utf-8",
                          dtype=str, keep_default_na=False)
    for col in ["compound", "category", "source_type"]:
        sources[col] = sources[col].str.strip()

    merged = unique_compounds.merge(sources, on=["compound", "category"], how="left")
    merged = merged.fillna("")

    missing = merged[merged["source_type"] == ""]
    if not missing.empty:
        print("⚠️ Missing source mappings for:", ", ".join(missing["compound"]))

    # Previous results, kept for a compound that fails this run (same URL only)
    metadata_path = DATA_DIR / "compound_metadata.csv"
    previous = {}
    if metadata_path.exists():
        prev_df = pd.read_csv(metadata_path, encoding="utf-8", dtype=str, keep_default_na=False)
        previous = {(r["compound"], r["source_url"]): r.to_dict() for _, r in prev_df.iterrows()}

    results, fetched, failed, skipped = [], 0, [], 0
    for _, row in merged.iterrows():
        source_type = row["source_type"].upper()
        if source_type not in SCRAPERS:
            skipped += 1
            results.append(empty_record(row["compound"], row["category"], "NONE", "",
                                        "No official or credible monograph found"))
            continue
        try:
            results.append(scrape_row(row))
            fetched += 1
        except Exception as e:
            print(f"❌ {row['compound']}: {e}")
            failed.append(row["compound"])
            kept = previous.get((row["compound"], row["source_url"]))
            results.append(kept or empty_record(row["compound"], row["category"], source_type,
                                                row["source_url"], f"Error: {e}"))

    meta_df = pd.DataFrame(results, columns=COLUMNS)
    meta_df.to_csv(metadata_path, index=False, encoding="utf-8")

    print(f"\nWrote {len(meta_df)} rows to {metadata_path}")
    print(f"Fetched {fetched}, failed {len(failed)}, no source {skipped}")
    if failed:
        print("Failed (previous data kept where it existed):", ", ".join(failed))


if __name__ == "__main__":
    main()

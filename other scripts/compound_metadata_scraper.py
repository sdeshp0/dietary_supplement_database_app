import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json

# ---------------------------------------------------------
# GLOBAL HELPERS
# ---------------------------------------------------------
HEADERS = {"User-Agent": "Mozilla/5.0"}

def safe_get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def clean_space(text):
    return re.sub(r"\s+", " ", text).strip()

def extract_dosage(text):
    if not text:
        return None
    text = text.lower()
    full = re.findall(r"\b\d{1,4}\s?(?:mg|mcg|iu)\b", text)
    if full:
        return ", ".join(sorted(set(full)))
    ranges = re.findall(r"\b\d{1,4}\s?-\s?\d{1,4}\b", text)
    if ranges:
        return ", ".join(sorted(set(ranges)))
    return None

# ---------------------------------------------------------
# ODS SCRAPER (Vitamins, Minerals, Omega-3)
# ---------------------------------------------------------
def scrape_ods(url, compound, category):
    soup = safe_get(url)
    text = clean_space(soup.get_text(" ", strip=True))

    def extract_section(keywords):
        headers = soup.find_all(["h2", "h3"])
        for h in headers:
            if any(k.lower() in h.get_text(strip=True).lower() for k in keywords):
                content = []
                for sib in h.find_next_siblings():
                    if sib.name in ["h2", "h3"]:
                        break
                    if sib.name in ["p", "ul", "ol"]:
                        content.append(sib.get_text(" ", strip=True))
                if content:
                    return clean_space(" ".join(content))
        return None

    def extract_table(keywords):
        tables = soup.find_all("table")
        for table in tables:
            if any(k.lower() in table.get_text().lower() for k in keywords):
                try:
                    df = pd.read_html(str(table))[0]
                    df.columns = [str(c).strip() for c in df.columns]
                    return df.to_dict(orient="records")
                except:
                    continue
        return None

    return {
        "compound": compound,
        "category": category,
        "source_type": "ODS",
        "source_url": url,
        "primary_functions": extract_section(["what is", "what does"]),
        "food_sources": extract_section(["what foods", "food sources"]),
        "safety_overview": extract_section(["harmful", "safety", "too much"]),
        "interactions_summary": extract_section(["interact", "interactions"]),
        "rda_json": json.dumps(extract_table(["recommended", "adequate", "rda"])),
        "ul_json": json.dumps(extract_table(["upper", "ul"])),
        "typical_supplement_range": extract_dosage(text),
        "notes": "Extracted from NIH ODS Consumer Fact Sheet"
    }

# ---------------------------------------------------------
# NCCIH SCRAPER (Herbs, Botanicals, Mushrooms)
# ---------------------------------------------------------
def scrape_nccih(url, compound, category):
    soup = safe_get(url)

    body = soup.find("div", class_="field--name-body")
    text = clean_space(body.get_text(" ", strip=True)) if body else ""

    def find_section(label):
        strong = soup.find("strong", string=lambda s: s and label.lower() in s.lower())
        if strong:
            parent = strong.parent
            return clean_space(parent.get_text(" ", strip=True))
        return None

    return {
        "compound": compound,
        "category": category,
        "source_type": "NCCIH",
        "source_url": url,
        "primary_functions": find_section("What"),
        "food_sources": None,
        "safety_overview": find_section("Safety"),
        "interactions_summary": find_section("Interaction"),
        "rda_json": None,
        "ul_json": None,
        "typical_supplement_range": extract_dosage(text),
        "notes": "Extracted from NCCIH herb monograph"
    }

# ---------------------------------------------------------
# MEDLINEPLUS SCRAPER (Bioactives, Amino Acids, Enzymes)
# ---------------------------------------------------------
def scrape_medlineplus(url, compound, category):
    soup = safe_get(url)

    summary = soup.find("p", class_="drug-summary")
    summary_text = clean_space(summary.get_text()) if summary else None

    sections = soup.find_all("div", class_="section")

    def find_section(label):
        for sec in sections:
            header = sec.find("h2")
            if header and label.lower() in header.get_text(strip=True).lower():
                return clean_space(sec.get_text(" ", strip=True))
        return None

    all_text = clean_space(soup.get_text(" ", strip=True))

    return {
        "compound": compound,
        "category": category,
        "source_type": "MEDLINEPLUS",
        "source_url": url,
        "primary_functions": summary_text or find_section("What"),
        "food_sources": None,
        "safety_overview": find_section("Side Effects") or find_section("Safety"),
        "interactions_summary": find_section("Interactions"),
        "rda_json": None,
        "ul_json": None,
        "typical_supplement_range": extract_dosage(all_text),
        "notes": "Extracted from MedlinePlus natural products database"
    }

# ---------------------------------------------------------
# PUBCHEM SCRAPER (Fallback)
# ---------------------------------------------------------
def scrape_pubchem(url, compound, category):
    soup = safe_get(url)

    summary = soup.find("section", {"id": "section-Overview"})
    summary_text = clean_space(summary.get_text(" ", strip=True)) if summary else None

    all_text = clean_space(soup.get_text(" ", strip=True))

    return {
        "compound": compound,
        "category": category,
        "source_type": "PUBCHEM",
        "source_url": url,
        "primary_functions": summary_text,
        "food_sources": None,
        "safety_overview": None,
        "interactions_summary": None,
        "rda_json": None,
        "ul_json": None,
        "typical_supplement_range": extract_dosage(all_text),
        "notes": "Extracted from PubChem compound summary"
    }

# ---------------------------------------------------------
# ROUTER
# ---------------------------------------------------------
def scrape_row(row):
    compound = row["compound"]
    category = row["category"]
    source_type = row["source_type"].upper()
    url = row["source_url"]

    print(f"Scraping {compound} ({category}) from {source_type} → {url}")

    if source_type == "ODS":
        return scrape_ods(url, compound, category)
    if source_type == "NCCIH":
        return scrape_nccih(url, compound, category)
    if source_type == "MEDLINEPLUS":
        return scrape_medlineplus(url, compound, category)
    if source_type == "PUBCHEM":
        return scrape_pubchem(url, compound, category)

    return {
        "compound": compound,
        "category": category,
        "source_type": source_type,
        "source_url": url,
        "primary_functions": None,
        "food_sources": None,
        "safety_overview": None,
        "interactions_summary": None,
        "rda_json": None,
        "ul_json": None,
        "typical_supplement_range": None,
        "notes": f"No scraper implemented for {source_type}"
    }

# ---------------------------------------------------------
# LOAD FILES
# ---------------------------------------------------------
ontology = pd.read_csv("data/supplement_ontology.csv")
ontology["compound"] = ontology["compound"].astype(str).str.strip()
ontology["category"] = ontology["category"].astype(str).str.strip()

unique_compounds = ontology[["compound", "category"]].drop_duplicates()

sources = pd.read_csv("compound_sources.csv")
sources["compound"] = sources["compound"].astype(str).str.strip()
sources["category"] = sources["category"].astype(str).str.strip()

merged = unique_compounds.merge(sources, on=["compound", "category"], how="left")

missing = merged[merged["source_type"].isna()]
if not missing.empty:
    print("⚠️ Missing source mappings for:")
    print(missing)

to_scrape = merged.dropna(subset=["source_type", "source_url"])

# ---------------------------------------------------------
# RUN SCRAPER
# ---------------------------------------------------------
results = []
for _, row in to_scrape.iterrows():
    try:
        results.append(scrape_row(row))
    except Exception as e:
        print(f"❌ ERROR scraping {row['compound']}: {e}")
        results.append({
            "compound": row["compound"],
            "category": row["category"],
            "source_type": row["source_type"],
            "source_url": row["source_url"],
            "primary_functions": None,
            "food_sources": None,
            "safety_overview": None,
            "interactions_summary": None,
            "rda_json": None,
            "ul_json": None,
            "typical_supplement_range": None,
            "notes": f"Error: {e}"
        })

meta_df = pd.DataFrame(results)
meta_df.to_csv("compound_metadata.csv", index=False)

meta_df.head()
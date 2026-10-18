## 🧬 Dietary Supplement Explorer

A multi‑page Streamlit application for exploring dietary supplement products, ingredients, mechanisms, and NIH ODS 
metadata.

This project brings together two complementary tools:
- **DSLD Product Explorer** — search, filter, and inspect dietary supplement products from the *NIH Dietary Supplement 
Label Database (DSLD)*
- **Ingredient Metadata Explorer** — explore mechanisms, categories, and compounds using curated metadata from the *NIH 
Office of Dietary Supplements (ODS)*

The app is designed with clarity in mind to help understand how a consumer might explore this kind of data as they look
for information about dietary supplements.

---

## 🚀 Features

### Home Page
- Overview of each page
- Links to primary data sources:
- NIH Dietary Supplement Label Database (DSLD)
- NIH Office of Dietary Supplements (ODS)
- Clean, user‑friendly landing page

### DSLD Product Explorer
- Search products by name
- Filter by brand and supplement form
- Barcode lookup
- Deep‑linking support (?dsld_id=...)
- Product overview including:
- Product name
- Brand
- Ingredients
- Other ingredients
- Market status
- Barcode
- Label PDF viewer (via NIH ODS PDF endpoint)
- Related product recommendations
- Cached data loading for fast performance

### Ingredient Metadata Explorer
- Filter ingredients by Health Goal (multi‑select)
- Refine results by Category and Mechanism
- Interactive Mechanism → Compound network graph using ECharts
- Category‑colored nodes for intuitive visual grouping
- Hover tooltips with mechanism descriptions
- Detailed compound information:
- Overview
- Safety
- Interactions
- RDA / UL tables
- ODS fact sheet links
- Expanders for clean, uncluttered navigation


## 📁 Project Structure
```
dietary_supplement_database_app/
│
├── Home.py
├── pages/
│   ├── 1_Dietary_Supplement_Label_Explorer.py
│   └── 2_Ingredient_Metadata_Explorer.py
│
├── utils/
│   ├── dsld_helpers.py
│   ├── ingredient_helpers.py
│
├── data/
│   └── dsld.duckdb   (DSLD products, tracked via Git LFS)
│
├── requirements.txt
└── README.md
```

---

## 📚 Data Sources
Products come from the NIH Dietary Supplement Label Database (DSLD), https://dsld.od.nih.gov,
stored in `data/dsld.duckdb`. The app opens it read-only and queries one product
at a time, so it never loads the full 2M-row label data into memory.

To refresh it, download the full database as CSV from the DSLD site (https://dsld.od.nih.gov),
unzip it into `data/raw_dsld/`, then run `python "other scripts/build_dsld_database.py"`
and commit the new `data/dsld.duckdb`.

Ingredient details (`data/compound_metadata.csv`) are built by
`other scripts/compound_metadata_scraper.py` from the source mapped to each
ingredient in `data/compound_sources.csv`:

| `source_type` | Source | Ingredients |
| --- | --- | --- |
| `ODS` | NIH Office of Dietary Supplements, via the [Fact Sheet API](https://ods.od.nih.gov/api/) | 33 (vitamins, minerals, a few botanicals) |
| `ODS_GROUP` | One row of an ODS group fact sheet (Exercise and Athletic Performance, Weight Loss) | 13 |
| `NCCIH` | NIH National Center for Complementary and Integrative Health | 11 |
| `HEALTH_CANADA` | [Health Canada Natural Health Product monographs](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/monosReq?lang=eng) | 17 |
| `LPI` | [Linus Pauling Institute](https://lpi.oregonstate.edu/mic), Oregon State University | 5 |
| `MSK` | [Memorial Sloan Kettering, About Herbs](https://www.mskcc.org/herbs) | 2 |
| `NONE` | No official or credible monograph found | 16 |

To refresh: `python "other scripts/compound_metadata_scraper.py"`. A compound
that fails to fetch keeps its previous data. Where an ODS fact sheet gives the
adult upper limit in a sentence rather than a table (vitamin E), the scraper
reads it from the sentence.

`data/ingredient_aliases.csv` maps DSLD ingredient names (lowercased, single
spaces) to ontology compounds, so a product's Supplement Facts can link each
ingredient to its details. Edit it by hand; `python "other scripts/ingredient_mapping_report.py"`
checks it and lists the most common names it doesn't cover yet. It gives
coverage both for all rows and for ingredient rows only, leaving out the
Nutrition Facts lines (calories, fat, sugar, protein) some labels repeat.

`python "other scripts/suggest_ingredient_aliases.py"` finds variants of names
already mapped (salts like "magnesium citrate", forms like "creatine hcl",
"organic turmeric", probiotic strains) and writes them to
`data/ingredient_alias_candidates.csv`. Safe rules are marked `approve = yes`;
names that hold two compounds, such as "calcium ascorbate", are left blank for
a person. Set `approve` to `yes` or `no` (correcting `suggested_compound` if
needed), then run it with `--apply` to add the approved rows to the aliases file.

`python "other scripts/check_aliases_gsrs.py"` checks the aliases against FDA's
[Global Substance Registration System](https://gsrs.ncats.nih.gov), which records
each substance's active moiety (magnesium citrate's is magnesium). It writes
`data/ingredient_alias_gsrs_check.csv`, flagging aliases whose active moiety
doesn't match their compound's, and lists which compounds each name on the
review list matches. The first run makes about 2,600 requests to GSRS; replies
are cached for later runs.

`utils/units.py` converts label amounts to the unit each compound's NIH ODS
recommended amount uses (mg, mcg, g, mcg DFE for folate, mcg RAE for vitamin A),
including the ODS IU conversions for vitamins A, D and E and for beta-carotene,
which counts toward vitamin A but not toward its upper limit. Where the label doesn't
say which form it is (vitamin E in IU, vitamin A in IU, folate in mcg), the
result carries a note naming the assumption. Tests: `python -m unittest discover tests`.

`utils/dose.py` compares each linked ingredient's amount per serving with the
ODS recommended amount and upper limit for adults 19 and older (pregnancy and
breastfeeding left out), showing a range where men, women and age groups
differ. Minerals named as a salt ("magnesium citrate") aren't compared, since
the amount may be the whole salt. Amounts over 100 times the upper limit,
or over 5 times the 99th percentile of
DSLD labels for that compound (`data/dose_ceilings.csv`, from
`python "other scripts/build_dose_ceilings.py"`), are flagged as a likely unit
error on the label.

The Ingredient Explorer lists the products that contain the selected
ingredient, sortable by dose, with links back to each label.

## 🛠 Tech Stack
- Python 3.10+
- Streamlit (multi‑page app framework)
- DuckDB (label database)
- Pandas (data processing)
- PyMuPDF (PDF → image extraction)
- ECharts via streamlit‑echarts (interactive network graph)
- Git LFS (large dataset storage)

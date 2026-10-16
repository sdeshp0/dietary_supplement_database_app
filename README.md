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
that fails to fetch keeps its previous data.

## 🛠 Tech Stack
- Python 3.10+
- Streamlit (multi‑page app framework)
- DuckDB (label database)
- Pandas (data processing)
- PyMuPDF (PDF → image extraction)
- ECharts via streamlit‑echarts (interactive network graph)
- Git LFS (large dataset storage)

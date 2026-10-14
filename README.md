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
│   └── dsld_tables.pkl   (tracked via Git LFS)
│
├── requirements.txt
└── README.md
```

---

## 📚 Data Sources
This app integrates authoritative data from:
- NIH Dietary Supplement Label Database (DSLD)
https://dsld.od.nih.gov
- NIH Office of Dietary Supplements (ODS)
https://ods.od.nih.gov 

These sources provide product labels, ingredient metadata, safety summaries, RDA/UL values, and more.

## 🛠 Tech Stack
- Python 3.10+
- Streamlit (multi‑page app framework)
- Pandas (data processing)
- PyMuPDF (PDF → image extraction)
- ECharts via streamlit‑echarts (interactive network graph)
- Git LFS (large dataset storage)

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
Products come from the NIH Dietary Supplement Label Database (DSLD), https://dsld.od.nih.gov

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

Health Canada's server answers 404 to scripts, so its monographs are read
from pages saved in a browser (File > Save Page As, "Webpage, HTML only")
into `data/raw/health_canada/` (not committed):

| Monograph | Save as |
| --- | --- |
| [5-HTP](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=5htp&lang=eng) | `5htp.html` |
| [Alpha-lipoic acid](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=alpha.lipoic.acid2&lang=eng) | `alpha.lipoic.acid2.html` |
| [Amylase, Lipase, Papain, Protease](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=enzyme.multi&lang=eng) | `enzyme.multi.html` |
| [Collagen peptides](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=hydrolized.collagen&lang=eng) | `hydrolized.collagen.html` |
| [DIM](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=diindolylmethane&lang=eng) | `diindolylmethane.html` |
| [Holy basil](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=ocimum.tenuliflorum.leaf.feuille2&lang=eng) | `ocimum.tenuliflorum.leaf.feuille2.html` |
| [L-theanine](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=l.theanine2&lang=eng) | `l.theanine2.html` |
| [MSM](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=msm2&lang=eng) | `msm2.html` |
| [NAC](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=n-acetyl-l-cysteine2&lang=eng) | `n-acetyl-l-cysteine2.html` |
| [Phosphatidylcholine](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=lecithin2&lang=eng) | `lecithin2.html` |
| [Phosphatidylserine](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=phosphatidylserine2&lang=eng) | `phosphatidylserine2.html` |
| [Plant sterols](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=free.plant.sterols.vegetaux&lang=eng) | `free.plant.sterols.vegetaux.html` |
| [Taurine](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=taurine2&lang=eng) | `taurine2.html` |
| [Tyrosine](https://webprod.hc-sc.gc.ca/nhpid-bdipsn/atReq.do?atid=l.tyrosine2&lang=eng) | `l.tyrosine2.html` |

## 🛠 Tech Stack
- Python 3.10+
- Streamlit (multi‑page app framework)
- Pandas (data processing)
- PyMuPDF (PDF → image extraction)
- ECharts via streamlit‑echarts (interactive network graph)
- Git LFS (large dataset storage)

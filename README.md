# DSLD Barcode Lookup App

A streamlined Streamlit application for exploring the **NIH Dietary Supplement Label Database (DSLD)** using locally 
downloaded CSV files.

The app provides a clean, consolidated view of supplement information based on a **barcode (UPC)** lookup, with 
intelligent related‑product suggestions and a polished product overview experience.

This project is designed for offline use and works entirely from the CSV files downloaded from the DSLD API Guide.

---

## 📁 Data Requirements
DSLD data can be downloaded from here: https://dsld.od.nih.gov/api-guide

Download and place all DSLD CSV files inside a folder named:
data/

The app currently supports the following file groups:

| Data Type | Expected Files | Status |
|----------|----------------|--------|
| Product Overview | `ProductOverview_*.csv` | **Loaded & merged** |
| Company Information | `CompanyInformation_*.csv` | **Loaded & merged** |
| Supplement Facts | `DietarySupplementFacts_*.csv` | **Loaded & merged** |
| Other Ingredients | `OtherIngredients_*.csv` | **Loaded & merged** |
| Label Statements | `LabelStatements_*.csv` | **Ignored (malformed)** |
| ReadMe files | `ReadMe*.csv` | **Ignored** |

All tables are merged by **DSLD ID**, which serves as the primary key across the dataset.

---

## 🔍 Current Features

### Barcode Lookup
Enter a barcode (UPC) to retrieve the matching product from the Product Overview table.

- Exact match on the `"Bar Code"` column  
- Displays product name and DSLD ID  
- Automatically loads all related data across tables  
- Supports deep‑linking via `?dsld_id=` query parameter  

---

### 🧩 Product Overview (Fully Consolidated)

The Product Overview tab now presents a **clean, human‑friendly summary** that merges information from multiple DSLD 
tables:

### **Included Fields**
- URL  
- DSLD ID  
- Product Name  
- Brand Name
- Product Type
- Supplement Form
- Contents  
- Serving Size  
- Suggested Use  
- Primary Ingredient(s)  
- Market Status (highlighted)  
- **Ingredients** (from Factsheet)  
- **Ingredient Categories** (from Factsheet)  
- **Daily Value Target Group** (from Factsheet)  
- **Other Ingredients** (from OtherIngredients)

### **Product Label Image**
A toggleable container (collapsed by default) displays the product label image rendered from the official DSLD PDF:
https://dsld.od.nih.gov/dsld/pdf/{DSLD_ID}.pdf

Rendering is handled via **PyMuPDF**, avoiding Poppler dependencies.

---

### 🏷️ Brand Information (Refined)

The Brand Information tab now shows only the fields that matter:

### **Company Name**

### **Company Roles** (read‑only checkboxes)
- Manufacturer  
- Distributor  
- Packager  
- Reseller  
- Other  

### **Related Products by This Company**
A curated list of **up to 5** related products, ranked by name similarity:

- Prefers products with similar names  
- Falls back to category‑adjacent items (e.g., other vitamins)  
- Only includes products from the same company  
- Optional filter: **Show only products currently on market**  
- Each product includes:
  - Product name  
  - DSLD ID  
  - Link to official DSLD page  
  - **“View in App”** button (reloads the app with that product preselected)

This transforms the Brand tab into a meaningful exploration tool rather than a raw data dump.

---

## 🛠️ Tech Stack

- Python  
- Streamlit  
- Pandas  
- PyMuPDF (fitz) for PDF → image conversion  
- Glob / OS for file discovery  

---

## ▶️ Running the App

Install dependencies:

```bash
pip install streamlit pandas pymupdf pillow
```

- Run the app:
```
streamlit run app.py
```

- Project Structure

```
project/
│
├── app.py
└── data/
    ├── ProductOverview_01.csv
    ├── ProductOverview_02.csv
    ├── CompanyInformation_01.csv
    ├── DietarySupplementFacts_01.csv
    ├── OtherIngredients_01.csv
    └── ...
```

## 📌 Known Limitations
- LabelStatements CSVs are malformed and currently skipped
- No name‑based search (disabled due to poor DSLD naming quality)
- Some products may not have a corresponding PDF
- Ingredient categories are only as good as DSLD’s metadata

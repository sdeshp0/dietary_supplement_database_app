# DSLD Barcode Lookup App
A lightweight Streamlit application for exploring the NIH Dietary Supplement Label Database (DSLD) using locally downloaded CSV files.
The app allows users to enter a barcode (UPC) and instantly view all available information about the corresponding dietary supplement product, including:
- Product overview
- Company/manufacturer information
- Supplement facts
- Other ingredients
- Product label image (rendered from the official DSLD PDF)

This project is designed for offline use and works entirely from the CSV files downloaded from the DSLD API Guide.

## 📁 Data Requirements
Download and place all DSLD CSV files inside a folder named:
data/


The app currently supports the following file groups:
- ProductOverview_*.csv 
- CompanyInformation_*.csv
- DietarySupplementFacts_*.csv
- OtherIngredients_*.csv
- LabelStatements_*.csv 
- ReadMe*.csv


All tables are merged by DSLD ID, which serves as the primary key across the dataset.

## 🔍 Current Features
1. Barcode Lookup: Enter a barcode (UPC) to retrieve the matching product from the Product Overview table.
   - Exact match on the "Bar Code" column
   - Displays product name and DSLD ID
   - Triggers loading of all related data across tables


2. Multi‑Tab Product View
   - Product Overview
     - Full row from the ProductOverview table
     - Embedded product label image (first page of the DSLD PDF)
   - Brand Information
     - Manufacturer and company details
     - Pulled from CompanyInformation tables
   - Factsheet
     - Supplement facts panel
     - Pulled from DietarySupplementFacts tables
   - Other
     - Other ingredients
     - Placeholder for future Label Statements integration


3. Product Label Image Rendering
   - The app fetches the official DSLD PDF for the product:
   https://dsld.od.nih.gov/dsld/pdf/{DSLD_ID}.pdf
   - It then renders the first page as an image using PyMuPDF (no Poppler required).

## 🚫 Temporarily Disabled Features
- Product Name Search
    - Product names in DSLD are not user‑friendly.
    - This feature has been removed until a better normalization or fuzzy‑matching strategy is developed.

## 🛠️ Tech Stack
- Python
- Streamlit
- Pandas
- PyMuPDF (fitz) for PDF → image conversion
- Glob / OS for file discovery

## ▶️ Running the App

- Install dependencies:
```
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
- No fuzzy search or name‑based lookup
- No caching of downloaded PDFs (fetched on demand)
- Some products may not have a corresponding PDF

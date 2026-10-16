"""
Builds data/dsld.duckdb, the database the label explorer reads.

Source, in order of preference:
  1. data/raw_dsld/: the full-database CSV download from the DSLD site
     (https://dsld.od.nih.gov), unzipped as it comes: ProductOverview_*.csv, CompanyInformation_*.csv,
     DietarySupplementFacts_*.csv, OtherIngredients_*.csv.
  2. data/dsld_tables.pkl: the pickle earlier versions of the app used.

Usage:
    python "other scripts/build_dsld_database.py"
"""

import pickle
from datetime import datetime, timezone
from pathlib import Path

import duckdb


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
RAW_DIR = DATA_DIR / "raw_dsld"
PICKLE_PATH = DATA_DIR / "dsld_tables.pkl"
DB_PATH = DATA_DIR / "dsld.duckdb"

# Database table -> (CSV file prefix, key in the old pickle)
TABLES = {
    "products": ("ProductOverview", "productOverview"),
    "companies": ("CompanyInformation", "companyInformation"),
    "supplement_facts": ("DietarySupplementFacts", "dietarySupplementFacts"),
    "other_ingredients": ("OtherIngredients", "otherIngredients"),
}

# Columns repeated from the product table in every other table
REPEATED_COLUMNS = ["URL", "Product Name"]


# ---------------------------------------------------------
# LOADING THE SOURCE
# ---------------------------------------------------------
def load_raw_csvs(con):
    for table, (prefix, _) in TABLES.items():
        files = sorted(RAW_DIR.glob(f"{prefix}_*.csv"))
        if not files:
            raise FileNotFoundError(f"No {prefix}_*.csv files in {RAW_DIR}")
        # A view can't take query parameters, so the file list is inlined
        file_list = ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in files)
        # The CSV dialect is set explicitly: auto-detection misreads some quoted fields
        con.execute(
            f"CREATE TEMP VIEW raw_{table} AS SELECT * FROM read_csv([{file_list}], "
            """header = true, delim = ',', quote = '"', escape = '"', """
            "all_varchar = true, union_by_name = true)"
        )
    return f"DSLD CSV export in {RAW_DIR.name}/"


def load_pickle(con):
    with open(PICKLE_PATH, "rb") as f:
        tables = pickle.load(f)
    for table, (_, key) in TABLES.items():
        con.register(f"raw_{table}", tables[key])
    return PICKLE_PATH.name


# ---------------------------------------------------------
# BUILD
# ---------------------------------------------------------
def build(con):
    # Rows are stored sorted by DSLD ID, so a lookup by product
    # reads only the few blocks that hold that product.
    con.execute("""
        CREATE TABLE products AS
        SELECT
            CAST("DSLD ID" AS INTEGER) AS "DSLD ID",
            * EXCLUDE ("DSLD ID", "Bar Code"),
            trim(coalesce("Bar Code", '')) AS "Bar Code",
            ltrim(regexp_replace(coalesce("Bar Code", ''), '\\D', '', 'g'), '0')
                AS "Bar Code (normalized)"
        FROM raw_products
        ORDER BY "DSLD ID"
    """)

    for table in ["companies", "supplement_facts", "other_ingredients"]:
        columns = con.execute(f"SELECT * FROM raw_{table} LIMIT 0").fetchdf().columns
        drop = ", ".join(f'"{c}"' for c in ["DSLD ID", *REPEATED_COLUMNS] if c in columns)
        # "Row Order" keeps each product's rows in the order they appear
        # on the label, since sorting by DSLD ID alone may reorder them
        con.execute(f"""
            CREATE TABLE {table} AS
            SELECT CAST("DSLD ID" AS INTEGER) AS "DSLD ID", * EXCLUDE ({drop})
            FROM (SELECT *, row_number() OVER () AS "Row Order" FROM raw_{table})
            ORDER BY "DSLD ID", "Row Order"
        """)

    con.execute('CREATE UNIQUE INDEX products_id ON products ("DSLD ID")')
    con.execute('CREATE INDEX products_barcode ON products ("Bar Code (normalized)")')


def main():
    tmp_path = DB_PATH.with_suffix(".duckdb.tmp")
    tmp_path.unlink(missing_ok=True)

    con = duckdb.connect(str(tmp_path))
    if RAW_DIR.is_dir():
        source = load_raw_csvs(con)
    elif PICKLE_PATH.exists():
        source = load_pickle(con)
    else:
        raise FileNotFoundError(
            f"Put the DSLD CSV export in {RAW_DIR} (see this script's docstring)."
        )

    print(f"Building {DB_PATH.name} from {source}")
    build(con)

    con.execute("CREATE TABLE build_info (source VARCHAR, built_at TIMESTAMPTZ)")
    con.execute("INSERT INTO build_info VALUES (?, ?)", [source, datetime.now(timezone.utc)])

    for table in TABLES:
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n:,} rows")
    con.close()

    # Replace the old database only once the new one is complete
    tmp_path.replace(DB_PATH)
    print(f"Wrote {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

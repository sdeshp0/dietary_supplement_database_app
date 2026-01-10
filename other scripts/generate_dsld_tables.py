import glob
import pickle
import os
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
DATA_DIR = Path(__file__).parents[1] / "data"
CSV_PATH = DATA_DIR / "raw_dsld"
PICKLE_PATH = DATA_DIR / "dsld_tables.pkl"

def load_data():

    if PICKLE_PATH.exists():

        print("Pickle DB exists")

    else:
        files = os.listdir(CSV_PATH)
        tables = {}

        po = []
        ci = []
        dsf = []
        ls = []
        oi = []

        for f in files:
            fname = os.path.basename(f)

            # Skip readme and malformed LabelStatements files
            if fname.lower().startswith("readme") or fname.startswith("LabelStatements_"):
                continue

            df = pd.read_csv(os.path.join(CSV_PATH, f), dtype=str)

            if fname.startswith("ProductOverview_"):
                po.append(df)

            elif fname.startswith("CompanyInformation_"):
                ci.append(df)

            elif fname.startswith("DietarySupplementFacts_"):
                dsf.append(df)

            elif fname.startswith("OtherIngredients_"):
                oi.append(df)

        tables["productOverview"] = pd.concat(po, ignore_index=True)
        tables["companyInformation"] = pd.concat(ci, ignore_index=True)
        tables["dietarySupplementFacts"] = pd.concat(dsf, ignore_index=True)
        tables["labelStatements"] = pd.DataFrame()  # empty placeholder
        tables["otherIngredients"] = pd.concat(oi, ignore_index=True)

        with open(PICKLE_PATH, 'wb') as f:
            pickle.dump(tables, f)

        print("Pickle DB generated")


if __name__ == "__main__":
    load_data()

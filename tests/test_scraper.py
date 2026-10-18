"""Run with: python -m unittest discover tests"""

import importlib.util
import unittest
from pathlib import Path

SCRAPER = Path(__file__).parents[1] / "other scripts" / "compound_metadata_scraper.py"
spec = importlib.util.spec_from_file_location("compound_metadata_scraper", SCRAPER)
scraper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scraper)


class ProseUpperLimit(unittest.TestCase):
    def test_vitamin_e_sentence(self):
        text = ("Because of this risk, the upper limit for adults is 1,000 mg/day for "
                "supplements of either natural or synthetic vitamin E.")
        self.assertEqual(scraper.ods_prose_upper_limit(text),
                         [{"Ages": "Adults 19 years and older", "Upper Limit": "1,000 mg"}])

    def test_no_limit_stated(self):
        self.assertIsNone(scraper.ods_prose_upper_limit("Vitamin K has not been shown to cause any harm."))
        self.assertIsNone(scraper.ods_prose_upper_limit(None))


if __name__ == "__main__":
    unittest.main()

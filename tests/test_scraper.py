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



class NccihSections(unittest.TestCase):
    LINES = [
        "What is osteoarthritis?", "A joint disease.",
        "What are glucosamine and chondroitin?", "Structural parts of cartilage.",
        "Are glucosamine and chondroitin helpful for symptoms of knee osteoarthritis?",
        "Mixed results.",
        "Are glucosamine and chondroitin safe?", "No serious side effects were found.",
        "For More Information", "Clearinghouse.",
    ]

    def setUp(self):
        self.fetch_soup, self.page_lines = scraper.fetch_soup, scraper.page_lines
        scraper.fetch_soup = lambda url: None
        scraper.page_lines = lambda soup: self.LINES

    def tearDown(self):
        scraper.fetch_soup, scraper.page_lines = self.fetch_soup, self.page_lines

    def test_page_about_several_ingredients(self):
        record = scraper.scrape_nccih({
            "compound": "Glucosamine", "category": "Bioactive", "source_url": "https://x",
            "source_section": "glucosamine and chondroitin",
        })
        self.assertEqual(record["primary_functions"], "Structural parts of cartilage.")
        self.assertEqual(record["safety_overview"], "No serious side effects were found.")


if __name__ == "__main__":
    unittest.main()

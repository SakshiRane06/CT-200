"""Checks for the structural quirks found in the supplied manual."""

import unittest
import tempfile
from pathlib import Path

from pypdf import PdfWriter

from app.parser import parse_pdf
from app.parser import UnsupportedPDFError


class ManualParserTests(unittest.TestCase):
    """Keep these checks focused on real cases from the CT-200 PDFs."""

    @classmethod
    def setUpClass(cls):
        cls.tree = parse_pdf("data/ct200_manual.pdf")
        cls.sections = {}
        cls._index_sections(cls.tree["sections"])

    @classmethod
    def _index_sections(cls, sections):
        """Make it easy for tests to look up a section by its number."""
        for section in sections:
            cls.sections[section["section_number"]] = section
            cls._index_sections(section["children"])

    def test_deep_heading_uses_closest_existing_parent(self):
        """2.1.1.1 has a numbering gap because 2.1.1 is missing."""
        section = self.sections["2.1.1.1"]
        self.assertEqual(section["parent_id"], self.sections["2.1"]["id"])
        self.assertEqual(section["level"], 4)

    def test_repeated_heading_text_keeps_distinct_section_ids(self):
        """The two Error Codes sections belong to different parents."""
        section_4 = self.sections["4.2"]
        section_7 = self.sections["7.1"]
        self.assertEqual(section_4["heading"], section_7["heading"])
        self.assertNotEqual(section_4["id"], section_7["id"])
        self.assertEqual(section_4["parent_id"], self.sections["4"]["id"])
        self.assertEqual(section_7["parent_id"], self.sections["7"]["id"])

    def test_classification_list_numbers_stay_in_section_body(self):
        """List items such as '1. Normal' must not become document sections."""
        result_section = self.sections["3.3"]
        self.assertIn("1. Normal:", result_section["body_text"])
        self.assertNotIn("1. Normal", self.sections)

    def test_out_of_order_siblings_keep_their_document_order(self):
        """Section 3.4 appears before 3.3 in the source manual."""
        operation_children = self.sections["3"]["children"]
        operation_numbers = [item["section_number"] for item in operation_children]
        self.assertLess(operation_numbers.index("3.4"), operation_numbers.index("3.3"))

    def test_pdf_without_text_fails_clearly_instead_of_returning_an_empty_tree(self):
        """A scanned image-only PDF needs OCR, which this version does not have."""
        with tempfile.TemporaryDirectory() as temp_folder:
            pdf_path = Path(temp_folder) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with pdf_path.open("wb") as pdf_file:
                writer.write(pdf_file)

            with self.assertRaisesRegex(UnsupportedPDFError, "does not run OCR"):
                parse_pdf(pdf_path)


if __name__ == "__main__":
    unittest.main()

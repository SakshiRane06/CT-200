"""Checks hash-based staleness reporting without a database or LLM call."""

import unittest

from app.staleness import classify_sources


class StalenessClassificationTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {
                "id": "section-2-1",
                "version": "v1",
                "content_hash": "old-hash",
            }
        ]

    def test_same_hash_is_current(self):
        result = classify_sources(self.sources, "v2", {"section-2-1": "old-hash"})

        self.assertEqual(result["status"], "current")
        self.assertEqual(result["sources"][0]["status"], "current")

    def test_changed_hash_is_stale(self):
        result = classify_sources(self.sources, "v2", {"section-2-1": "new-hash"})

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["sources"][0]["status"], "changed")

    def test_missing_section_is_reported_as_removed(self):
        result = classify_sources(self.sources, "v2", {})

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["sources"][0]["status"], "removed")

    def test_mix_of_changed_and_current_sources_is_partially_stale(self):
        sources = self.sources + [
            {"id": "section-4-1", "version": "v1", "content_hash": "same-hash"}
        ]
        current_hashes = {
            "section-2-1": "new-hash",
            "section-4-1": "same-hash",
        }

        result = classify_sources(sources, "v2", current_hashes)

        self.assertEqual(result["status"], "partially_stale")


if __name__ == "__main__":
    unittest.main()

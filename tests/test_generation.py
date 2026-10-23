"""Checks that malformed LLM output is repaired or rejected safely."""

import json
import os
import unittest
from unittest.mock import patch

from app.llm import InvalidLLMResponse, generate_test_cases


def make_valid_response():
    """Build a small example that follows the expected JSON shape."""
    return json.dumps(
        {
            "test_cases": [
                {
                    "title": f"Check behavior {number}",
                    "preconditions": ["The device is powered on"],
                    "steps": ["Start a measurement"],
                    "expected_result": "The device shows the expected result",
                    "source_node_ids": ["section-4-2"],
                }
                for number in range(1, 4)
            ]
        }
    )


class GenerationValidationTests(unittest.TestCase):
    """Use a fake provider so these checks never make a network request."""

    def setUp(self):
        self.selection = {
            "id": 12,
            "name": "Error handling",
            "version": "v1",
            "items": [
                {
                    "id": "section-4-2",
                    "version": "v1",
                    "content_hash": "abc123",
                    "text": "E3 means overpressure and the device auto-deflates.",
                }
            ],
        }
        self.env = patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "not-a-real-key",
                "LLM_BASE_URL": "https://provider.example/v1",
                "LLM_MODEL": "example-model",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    @patch("app.llm._call_provider")
    def test_bad_first_response_is_retried_and_valid_output_is_returned(self, call):
        call.side_effect = ["not json", make_valid_response()]

        cases = generate_test_cases(self.selection)

        self.assertEqual(len(cases), 3)
        self.assertEqual(call.call_count, 2)

    @patch("app.llm._call_provider")
    def test_second_invalid_response_fails_instead_of_returning_partial_cases(self, call):
        call.return_value = json.dumps({"test_cases": []})

        with self.assertRaises(InvalidLLMResponse):
            generate_test_cases(self.selection)

        self.assertEqual(call.call_count, 2)

    @patch("app.llm._call_provider")
    def test_case_cannot_claim_a_section_outside_the_selection(self, call):
        outside_source = make_valid_response().replace("section-4-2", "section-9-9")
        call.side_effect = [outside_source, make_valid_response()]

        cases = generate_test_cases(self.selection)

        self.assertEqual(len(cases), 3)
        self.assertTrue(all(case["source_node_ids"] == ["section-4-2"] for case in cases))


if __name__ == "__main__":
    unittest.main()

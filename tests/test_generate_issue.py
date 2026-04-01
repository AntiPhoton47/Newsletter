from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_issue  # noqa: E402


class GenerateIssueTests(unittest.TestCase):
    @mock.patch("generate_issue.fetch_yahoo_quote")
    def test_select_company_movers_prefers_largest_moves(self, mock_quote: mock.Mock) -> None:
        quotes = {
            "nvda.us": ("120.00", "up 3.10%"),
            "tsla.us": ("200.00", "down 6.20%"),
            "pltr.us": ("88.00", "up 1.70%"),
            "arm.us": ("140.00", "up 0.90%"),
        }

        def side_effect(symbol: str) -> tuple[str, str]:
            return quotes.get(symbol, ("data unavailable", "live quote unavailable"))

        mock_quote.side_effect = side_effect

        selected, failures = generate_issue.select_company_movers()

        self.assertEqual(
            [label for label, _price, _move in selected],
            ["Tesla (TSLA)", "NVIDIA (NVDA)", "Palantir (PLTR)"],
        )
        self.assertNotIn("ARM Holdings (ARM)", failures)

    @mock.patch("generate_issue.enrich_entries", side_effect=lambda entries: entries)
    def test_build_travel_section_renders_image_when_available(self, _mock_enrich: mock.Mock) -> None:
        lines = generate_issue.build_travel_section(
            [
                {
                    "title": "Alesund, Norway",
                    "summary": "A compact coastal city with sea access, mountain views, and easy spring walking.",
                    "publisher": "Lonely Planet",
                    "link": "https://example.com/alesund",
                    "image_url": "https://example.com/alesund.jpg",
                }
            ]
        )

        rendered = "\n".join(lines)
        self.assertIn("![Alesund, Norway](https://example.com/alesund.jpg)", rendered)
        self.assertIn("[Source: Lonely Planet](https://example.com/alesund)", rendered)

    def test_build_generic_section_can_rescue_from_related_sections(self) -> None:
        sections = {
            "Need To Know": [],
            "Research Watch": [
                {
                    "title": "Quantum networking milestone",
                    "summary": "A research result with enough detail to sustain a short write-up.",
                    "publisher": "Nature",
                    "link": "https://example.com/qn",
                }
            ],
            "AI": [
                {
                    "title": "Agent tooling improves evaluation",
                    "summary": "Another candidate that can support a short take without placeholders.",
                    "publisher": "GitHub",
                    "link": "https://example.com/agents",
                }
            ],
        }

        lines = generate_issue.build_generic_section(
            "Need To Know",
            [],
            sections=sections,
            used_keys=set(),
        )

        rendered = "\n".join(lines)
        self.assertIn("Quantum networking milestone", rendered)
        self.assertNotIn("Insufficient sourced material", rendered)


if __name__ == "__main__":
    unittest.main()

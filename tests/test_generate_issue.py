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
    @mock.patch("generate_issue.load_latest_market_snapshot", return_value=None)
    @mock.patch("generate_issue.fetch_yahoo_quote_snapshot")
    def test_select_company_movers_prefers_largest_moves(self, mock_quote: mock.Mock, _mock_cache: mock.Mock) -> None:
        quotes = {
            "nvda.us": {"price": "120.00", "move": "up 3.10%", "move_pct": 3.1, "as_of": "2026-04-03", "captured_on": "2026-04-03"},
            "tsla.us": {"price": "200.00", "move": "down 6.20%", "move_pct": 6.2, "as_of": "2026-04-03", "captured_on": "2026-04-03"},
            "pltr.us": {"price": "88.00", "move": "up 1.70%", "move_pct": 1.7, "as_of": "2026-04-03", "captured_on": "2026-04-03"},
            "arm.us": {"price": "140.00", "move": "up 0.90%", "move_pct": 0.9, "as_of": "2026-04-03", "captured_on": "2026-04-03"},
        }

        def side_effect(symbol: str) -> dict | None:
            return quotes.get(symbol)

        mock_quote.side_effect = side_effect

        selected, failures, _entries = generate_issue.select_company_movers()

        self.assertEqual(
            [label for label, _price, _move in selected],
            ["Tesla (TSLA)", "NVIDIA (NVDA)", "Palantir (PLTR)"],
        )
        self.assertNotIn("ARM Holdings (ARM)", failures)

    @mock.patch("generate_issue.load_latest_market_snapshot")
    @mock.patch("generate_issue.fetch_yahoo_quote_snapshot", return_value=None)
    def test_select_company_movers_uses_recent_cache_when_live_fails(
        self,
        _mock_live: mock.Mock,
        mock_cache: mock.Mock,
    ) -> None:
        mock_cache.return_value = {
            "quotes": {
                "NVIDIA (NVDA)": {
                    "price": "120.00",
                    "move": "up 3.10%",
                    "move_pct": 3.1,
                    "as_of": "2026-04-03",
                    "captured_on": "2026-04-03",
                },
                "Tesla (TSLA)": {
                    "price": "200.00",
                    "move": "down 6.20%",
                    "move_pct": 6.2,
                    "as_of": "2026-04-03",
                    "captured_on": "2026-04-03",
                },
            }
        }

        selected, failures, _entries = generate_issue.select_company_movers(issue_date=dt.date(2026, 4, 3))

        self.assertEqual([label for label, _price, _move in selected], ["Tesla (TSLA)", "NVIDIA (NVDA)"])
        self.assertNotIn("Tesla (TSLA)", failures)
        self.assertNotIn("NVIDIA (NVDA)", failures)

    @mock.patch("generate_issue.load_latest_market_snapshot")
    @mock.patch("generate_issue.latest_fred_value", side_effect=RuntimeError("down"))
    @mock.patch("generate_issue.latest_fred_yoy", side_effect=RuntimeError("down"))
    def test_build_macro_lines_uses_recent_cache_when_live_fails(
        self,
        _mock_yoy: mock.Mock,
        _mock_value: mock.Mock,
        mock_cache: mock.Mock,
    ) -> None:
        mock_cache.return_value = {
            "macro": {
                "US CPI (YoY)": {
                    "kind": "yoy",
                    "value": 2.7,
                    "as_of": "2026-02-01",
                    "source": "BLS via FRED",
                    "url": "https://fred.stlouisfed.org/series/CPIAUCSL",
                    "captured_on": "2026-04-03",
                },
                "US unemployment rate": {
                    "kind": "value_1",
                    "value": 4.3,
                    "as_of": "2026-03-01",
                    "source": "BLS via FRED",
                    "url": "https://fred.stlouisfed.org/series/UNRATE",
                    "captured_on": "2026-04-03",
                },
                "Fed funds rate": {
                    "kind": "value_2",
                    "value": 3.64,
                    "as_of": "2026-03-01",
                    "source": "Federal Reserve via FRED",
                    "url": "https://fred.stlouisfed.org/series/FEDFUNDS",
                    "captured_on": "2026-04-03",
                },
                "US 10-year Treasury": {
                    "kind": "daily_2",
                    "value": 4.33,
                    "as_of": "2026-04-01",
                    "source": "Treasury via FRED",
                    "url": "https://fred.stlouisfed.org/series/DGS10",
                    "captured_on": "2026-04-03",
                },
                "Brent crude": {
                    "kind": "oil_2",
                    "value": 121.88,
                    "as_of": "2026-03-30",
                    "source": "EIA via FRED",
                    "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
                    "captured_on": "2026-04-03",
                },
            }
        }

        lines, failures, metrics, entries = generate_issue.build_macro_lines(issue_date=dt.date(2026, 4, 4))

        self.assertEqual(failures, [])
        self.assertEqual(metrics["fed_funds"], 3.64)
        self.assertIn("(cached)", "\n".join(lines))
        self.assertEqual(set(entries), set(generate_issue.MACRO_SERIES))

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
        self.assertTrue(
            any(title in rendered for title in ("Quantum networking milestone", "Agent tooling improves evaluation"))
        )
        self.assertNotIn("Insufficient sourced material", rendered)


if __name__ == "__main__":
    unittest.main()

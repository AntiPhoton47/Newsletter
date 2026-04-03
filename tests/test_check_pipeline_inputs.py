from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_pipeline_inputs as cpi  # noqa: E402


class CandidateHealthTests(unittest.TestCase):
    def test_healthy_payload_passes(self) -> None:
        sections = {
            "Need To Know": [{}, {}, {}],
            "Research Watch": [{}, {}, {}, {}],
            "World News": [{}, {}, {}],
            "Philosophy": [{}, {}],
            "Biology": [{}, {}],
            "Psychology and Neuroscience": [{}, {}],
            "Health and Medicine": [{}, {}],
            "Sociology and Anthropology": [{}, {}],
            "Technology": [{}, {}],
            "Robotics": [{}, {}],
            "AI": [{}, {}, {}],
            "Engineering": [{}, {}],
            "Mathematics": [{}, {}],
            "Historical Discoveries": [{}, {}],
            "Archaeology": [{}, {}],
            "Tools You Can Use": [{}, {}, {}],
            "Entertainment": [{}],
            "Travel": [{}],
        }
        fetch_sections = {
            section: {
                "queries": [
                    {
                        "query": f"{section} query",
                        "status": "ok",
                        "entry_count": len(entries),
                    }
                ]
            }
            for section, entries in sections.items()
        }
        payload = {
            "sections": sections,
            "fetch": {"sections": fetch_sections},
        }

        report = cpi.summarize_candidate_health(payload)

        self.assertTrue(report["passed"])
        self.assertEqual(report["findings"], [])

    def test_failed_payload_is_blocked(self) -> None:
        payload = {
            "sections": {
                "Need To Know": [],
                "Research Watch": [],
                "World News": [],
                "AI": [],
                "Tools You Can Use": [],
            },
            "fetch": {
                "sections": {
                    "Need To Know": {
                        "queries": [
                            {"query": "q1", "status": "failed", "entry_count": 0},
                            {"query": "q2", "status": "failed", "entry_count": 0},
                        ]
                    },
                    "Research Watch": {
                        "queries": [
                            {"query": "q3", "status": "failed", "entry_count": 0},
                            {"query": "q4", "status": "failed", "entry_count": 0},
                        ]
                    },
                }
            },
        }

        report = cpi.summarize_candidate_health(payload)

        self.assertFalse(report["passed"])
        self.assertGreaterEqual(len(report["findings"]), 3)
        self.assertEqual(len(report["failed_queries"]), 4)
        self.assertFalse(report["rescue_ready"])
        self.assertTrue(report["hard_fail"])

    def test_thin_payload_can_continue_in_rescue_mode(self) -> None:
        payload = {
            "sections": {
                "Need To Know": [{}, {}],
                "Research Watch": [{}, {}, {}],
                "World News": [{}, {}],
                "AI": [{}, {}],
                "Tools You Can Use": [{}, {}],
                "Technology": [{}, {}],
                "Engineering": [{}, {}],
            },
            "fetch": {
                "sections": {
                    "Need To Know": {"queries": [{"query": "q1", "status": "ok", "entry_count": 2}]},
                    "Research Watch": {"queries": [{"query": "q2", "status": "ok", "entry_count": 3}]},
                    "World News": {"queries": [{"query": "q3", "status": "failed", "entry_count": 0}]},
                    "AI": {"queries": [{"query": "q4", "status": "ok", "entry_count": 2}]},
                    "Tools You Can Use": {"queries": [{"query": "q5", "status": "ok", "entry_count": 2}]},
                }
            },
        }

        report = cpi.summarize_candidate_health(payload)

        self.assertFalse(report["passed"])
        self.assertTrue(report["rescue_ready"])
        self.assertFalse(report["hard_fail"])


class MarketHealthTests(unittest.TestCase):
    @mock.patch("generate_issue.save_market_snapshot")
    @mock.patch("generate_issue.select_company_movers")
    @mock.patch("generate_issue.build_macro_lines")
    @mock.patch("generate_issue.fetch_yahoo_quote_snapshot")
    def test_market_health_passes_with_enough_data(
        self,
        mock_quote: mock.Mock,
        mock_macro: mock.Mock,
        mock_movers: mock.Mock,
        _mock_save: mock.Mock,
    ) -> None:
        mock_quote.return_value = {
            "price": "101.00",
            "move": "up 1.00%",
            "move_pct": 1.0,
            "as_of": "2026-04-03",
            "captured_on": "2026-04-03",
        }
        mock_macro.return_value = (["macro"] * 5, [], {}, {})
        mock_movers.return_value = ([("NVIDIA (NVDA)", "101.00", "up 1.00%")] * 2, [], {})
        report = cpi.summarize_market_health()
        self.assertTrue(report["passed"])
        self.assertEqual(report["quote_failures"], [])
        self.assertEqual(report["macro_failures"], [])

    @mock.patch("generate_issue.save_market_snapshot")
    @mock.patch("generate_issue.select_company_movers", return_value=([], ["NVIDIA (NVDA)", "Tesla (TSLA)"], {}))
    @mock.patch("generate_issue.build_macro_lines", return_value=([], ["US CPI (YoY)", "US unemployment rate"], {}, {}))
    @mock.patch("generate_issue.fetch_yahoo_quote_snapshot", return_value=None)
    def test_market_health_fails_when_data_is_missing(
        self,
        _mock_quote: mock.Mock,
        _mock_macro: mock.Mock,
        _mock_movers: mock.Mock,
        _mock_save: mock.Mock,
    ) -> None:
        report = cpi.summarize_market_health()
        self.assertFalse(report["passed"])
        self.assertGreaterEqual(len(report["findings"]), 1)


if __name__ == "__main__":
    unittest.main()

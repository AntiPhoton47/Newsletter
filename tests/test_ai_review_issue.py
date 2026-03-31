from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_review_issue  # noqa: E402


class LocalFallbackReviewTests(unittest.TestCase):
    def test_short_draft_fails_local_fallback(self) -> None:
        benchmark = (
            "# Frontier Threads\n\n"
            + ("**Source:** Example\n\nDetailed benchmark paragraph.\n\n**Link:** [Read](https://example.com)\n\n" * 40)
        )
        draft = "# Frontier Threads\n\n## Quick Hits\n\n- **Need To Know:** Thin.\n"

        report = ai_review_issue.build_local_fallback_report(dt.date(2026, 3, 31), draft, benchmark)

        self.assertFalse(report["passed"])
        self.assertGreater(len(report["findings"]), 0)
        self.assertEqual(report["model"], "local-heuristic")


if __name__ == "__main__":
    unittest.main()

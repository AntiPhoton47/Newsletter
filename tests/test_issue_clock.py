from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import issue_clock  # noqa: E402


class IssueClockTests(unittest.TestCase):
    def test_explicit_date_wins(self) -> None:
        self.assertEqual(issue_clock.resolve_issue_date("2026-03-31"), dt.date(2026, 3, 31))

    def test_timezone_controls_default_date(self) -> None:
        now = dt.datetime(2026, 3, 30, 22, 30, tzinfo=dt.timezone.utc)
        with mock.patch.dict("os.environ", {"NEWSLETTER_TIMEZONE": "Europe/Oslo"}, clear=False):
            self.assertEqual(issue_clock.resolve_issue_date(None, now=now), dt.date(2026, 3, 31))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "UTC"


def configured_timezone_name() -> str:
    for name in ("NEWSLETTER_TIMEZONE", "TZ"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return DEFAULT_TIMEZONE


def configured_timezone() -> dt.tzinfo:
    name = configured_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return dt.timezone.utc


def resolve_issue_date(date_arg: str | None, *, now: dt.datetime | None = None) -> dt.date:
    if date_arg:
        return dt.date.fromisoformat(date_arg)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    return current.astimezone(configured_timezone()).date()

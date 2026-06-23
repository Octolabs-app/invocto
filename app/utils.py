"""
utils.py — Small shared helpers for safe form parsing and sequence numbering.

These guard against malformed user/form input that would otherwise raise an
unhandled exception (→ HTTP 500). Parsers always return a sane fallback.
"""
import re
from datetime import date
from typing import Optional


def safe_float(value, default: float = 0.0) -> float:
    """Parse a float from form input, falling back to `default` on bad input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: Optional[int] = None) -> Optional[int]:
    """Parse an int from form input, returning `default` (None) on bad input."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_date(value, default: Optional[date] = None) -> Optional[date]:
    """Parse an ISO date (YYYY-MM-DD), returning `default` on bad/empty input."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def next_sequence_number(existing: list, prefix: str) -> str:
    """
    Given a list of existing numbers like ['INV-0007', 'INV-0012'], return the
    next number as f'{prefix}-{max+1:04d}'. Robust to deletions and gaps —
    derives from the highest trailing integer rather than a row count, so a
    delete-then-create can never reuse an existing number.
    """
    highest = 0
    for num in existing:
        if not num:
            continue
        m = re.search(r"(\d+)\s*$", str(num))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{prefix}-{highest + 1:04d}"

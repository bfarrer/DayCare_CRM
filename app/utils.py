"""Small helpers shared by the view modules."""

from datetime import date, datetime


def clean(value, max_length=None):
    """Trim a submitted string; return None when it is empty."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if max_length:
        value = value[:max_length]
    return value


def parse_date(value):
    """Parse an HTML date input (YYYY-MM-DD). Returns None when blank/invalid."""
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_bool(value):
    return str(value).lower() in {"1", "true", "on", "yes"}


def date_input(value):
    """Format a date for an HTML date input."""
    return value.isoformat() if isinstance(value, date) else ""


def display_date(value, empty="—"):
    """Format a date for reading: 'Mar 4, 2026'."""
    if not isinstance(value, date):
        return empty
    return value.strftime("%b %-d, %Y") if _supports_dash_modifier() else value.strftime("%b %d, %Y")


def _supports_dash_modifier():
    """glibc supports %-d; fall back to zero-padded days elsewhere."""
    try:
        return date(2026, 3, 4).strftime("%-d") == "4"
    except ValueError:
        return False


def pct(numerator, denominator, digits=1):
    """Percentage, guarding against divide-by-zero on an empty funnel."""
    if not denominator:
        return 0.0
    return round(100.0 * numerator / denominator, digits)

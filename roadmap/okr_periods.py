"""Calendar helpers for OKR set period presets (quarter / year)."""
from datetime import date
from calendar import monthrange


QUARTERLY = 'quarterly'
ANNUAL = 'annual'

# UI / URL window keys → (period type stored on ObjectiveSet, label)
WINDOW_CURRENT_QUARTER = 'current_quarter'
WINDOW_NEXT_QUARTER = 'next_quarter'
WINDOW_CURRENT_YEAR = 'current_year'
WINDOW_NEXT_YEAR = 'next_year'
WINDOW_CUSTOM = 'custom'

WINDOW_CHOICES = [
    (WINDOW_CURRENT_QUARTER, 'Current quarter'),
    (WINDOW_NEXT_QUARTER, 'Next quarter'),
    (WINDOW_CURRENT_YEAR, 'Current year'),
    (WINDOW_NEXT_YEAR, 'Next year'),
]

PRESET_CHOICES = WINDOW_CHOICES + [
    (WINDOW_CUSTOM, 'Choose my own dates'),
]


def quarter_bounds(year, quarter):
    """Return (start, end) for a 1–4 calendar quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    end = date(year, end_month, monthrange(year, end_month)[1])
    return start, end


def year_bounds(year):
    return date(year, 1, 1), date(year, 12, 31)


def current_quarter(today=None):
    today = today or date.today()
    q = (today.month - 1) // 3 + 1
    return quarter_bounds(today.year, q)


def next_quarter(today=None):
    today = today or date.today()
    q = (today.month - 1) // 3 + 1
    if q == 4:
        return quarter_bounds(today.year + 1, 1)
    return quarter_bounds(today.year, q + 1)


def current_year(today=None):
    today = today or date.today()
    return year_bounds(today.year)


def next_year(today=None):
    today = today or date.today()
    return year_bounds(today.year + 1)


def resolve_preset(preset, today=None):
    """
    Map a preset key to (period, start, end, suggested_name).
    period is 'quarterly', 'annual', or None for custom.
    """
    today = today or date.today()
    if preset == WINDOW_CURRENT_QUARTER:
        start, end = current_quarter(today)
        q = (start.month - 1) // 3 + 1
        return QUARTERLY, start, end, f'{start.year} Q{q}'
    if preset == WINDOW_NEXT_QUARTER:
        start, end = next_quarter(today)
        q = (start.month - 1) // 3 + 1
        return QUARTERLY, start, end, f'{start.year} Q{q}'
    if preset == WINDOW_CURRENT_YEAR:
        start, end = current_year(today)
        return ANNUAL, start, end, str(start.year)
    if preset == WINDOW_NEXT_YEAR:
        start, end = next_year(today)
        return ANNUAL, start, end, str(start.year)
    return None, None, None, ''


def window_range(window, today=None):
    """(period, start, end, label) for an org OKR overview window."""
    period, start, end, name = resolve_preset(window, today=today)
    labels = dict(WINDOW_CHOICES)
    return period, start, end, labels.get(window, name)


def detect_preset(period, start_date, end_date, today=None):
    """Best-matching preset for an existing set, or 'custom'."""
    today = today or date.today()
    if not start_date or not end_date:
        return WINDOW_CUSTOM
    for key, _label in WINDOW_CHOICES:
        p, s, e, _ = resolve_preset(key, today=today)
        if period == p and start_date == s and end_date == e:
            return key
    return WINDOW_CUSTOM


def suggested_name_for_dates(period, start_date, end_date):
    if not start_date or not end_date:
        return ''
    if period == QUARTERLY:
        q = (start_date.month - 1) // 3 + 1
        return f'{start_date.year} Q{q}'
    if period == ANNUAL:
        return str(start_date.year)
    return ''

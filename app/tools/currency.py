"""
SEA currency registry.
All rates are expressed as: 1 unit of this currency = N PHP.
Base currency is PHP (rate 1.0).
"""

from typing import Dict, Optional, Tuple

# (iso_code, display_symbol, php_rate)
# php_rate: how many PHP equal 1 unit of this currency
_TABLE: Dict[str, Tuple[str, str, float]] = {
    "php":         ("PHP", "PHP",  1.0),
    "peso":        ("PHP", "PHP",  1.0),
    "₱":           ("PHP", "PHP",  1.0),
    "myr":         ("MYR", "MYR",  12.0),
    "rm":          ("MYR", "MYR",  12.0),
    "ringgit":     ("MYR", "MYR",  12.0),
    "sgd":         ("SGD", "SGD",  38.5),
    "s$":          ("SGD", "SGD",  38.5),
    "singapore":   ("SGD", "SGD",  38.5),
    "thb":         ("THB", "THB",  1.45),
    "baht":        ("THB", "THB",  1.45),
    "idr":         ("IDR", "IDR",  0.0032),
    "rp":          ("IDR", "IDR",  0.0032),
    "rupiah":      ("IDR", "IDR",  0.0032),
    "vnd":         ("VND", "VND",  0.002),
    "dong":        ("VND", "VND",  0.002),
    "bnd":         ("BND", "BND",  38.5),
    "brunei":      ("BND", "BND",  38.5),
    "khr":         ("KHR", "KHR",  0.012),
    "riel":        ("KHR", "KHR",  0.012),
    "lak":         ("LAK", "LAK",  0.0024),
    "kip":         ("LAK", "LAK",  0.0024),
    "mmk":         ("MMK", "MMK",  0.024),
    "kyat":        ("MMK", "MMK",  0.024),
    "usd":         ("USD", "USD",  57.0),
    "dollar":      ("USD", "USD",  57.0),
    "dollars":     ("USD", "USD",  57.0),
    "$":           ("USD", "USD",  57.0),
}

# canonical ISO → (symbol, php_rate)
_BY_ISO: Dict[str, Tuple[str, float]] = {}
for _key, (_iso, _sym, _rate) in _TABLE.items():
    if _iso not in _BY_ISO:
        _BY_ISO[_iso] = (_sym, _rate)


def detect(text: str) -> Tuple[str, str, float]:
    """
    Detect currency from a free-text string (e.g. '20000 MYR', 'RM 5000').
    Returns (iso_code, symbol, php_rate).  Defaults to PHP.
    """
    lower = text.lower()
    for key, (iso, sym, rate) in _TABLE.items():
        if key in lower:
            return iso, sym, rate
    return "PHP", "PHP", 1.0


def lookup_iso(iso: str) -> Tuple[str, float]:
    """Return (symbol, php_rate) for a known ISO code, defaulting to PHP."""
    return _BY_ISO.get(iso.upper(), ("PHP", 1.0))


def all_iso_codes() -> list:
    return list(_BY_ISO.keys())

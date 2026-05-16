"""
Eve Cater's AI — iNextLabs' smart catering assistant.

Usage (Terminal 2, while app.main is running in Terminal 1):
    python -m app.chat

Eve guides customers through a structured menu:
  1. New Customer  — full booking flow with receipt generation
  2. View booking  — lookup by Booking ID
  3. Browse catalogue — curated event packages
  4. How do I use Eve Cater's AI? — feature guide
  5. Chat with a staff — contact handoff

Type 'menu' at any time to return to the main menu.
Type 'quit' or 'exit' to leave.
"""

from __future__ import annotations

import json
import os
import random
import re
import string
import sys
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# Force UTF-8 output so emoji display correctly on all terminals (incl. Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

BASE_URL = os.getenv("AGENT_API_URL", "http://127.0.0.1:8000")

# ── Branding ──────────────────────────────────────────────────────────────────

BRAND = "Eve Cater's AI"
EVE = "Eve"
COMPANY = "iNextLabs"

# ── Geography ─────────────────────────────────────────────────────────────────

SEA_COUNTRIES: Dict[str, Dict[str, str]] = {
    "malaysia":    {"name": "Malaysia",     "currency": "MYR", "flag": "🇲🇾"},
    "philippines": {"name": "Philippines",  "currency": "PHP", "flag": "🇵🇭"},
    "singapore":   {"name": "Singapore",    "currency": "SGD", "flag": "🇸🇬"},
    "indonesia":   {"name": "Indonesia",    "currency": "IDR", "flag": "🇮🇩"},
    "thailand":    {"name": "Thailand",     "currency": "THB", "flag": "🇹🇭"},
    "vietnam":     {"name": "Vietnam",      "currency": "VND", "flag": "🇻🇳"},
    "myanmar":     {"name": "Myanmar",      "currency": "MMK", "flag": "🇲🇲"},
    "cambodia":    {"name": "Cambodia",     "currency": "KHR", "flag": "🇰🇭"},
    "brunei":      {"name": "Brunei",       "currency": "BND", "flag": "🇧🇳"},
    "laos":        {"name": "Laos",         "currency": "LAK", "flag": "🇱🇦"},
}

_COUNTRY_ALIASES: Dict[str, str] = {
    "kl": "malaysia", "kuala lumpur": "malaysia", "penang": "malaysia",
    "johor": "malaysia", "sabah": "malaysia", "sarawak": "malaysia", "my": "malaysia",
    "manila": "philippines", "cebu": "philippines", "ph": "philippines",
    "davao": "philippines", "quezon": "philippines",
    "sg": "singapore",
    "bali": "indonesia", "jakarta": "indonesia", "surabaya": "indonesia",
    "bandung": "indonesia", "id": "indonesia",
    "bangkok": "thailand", "phuket": "thailand", "chiang mai": "thailand", "th": "thailand",
    "ho chi minh": "vietnam", "hanoi": "vietnam", "saigon": "vietnam", "vn": "vietnam",
    "rangoon": "myanmar", "yangon": "myanmar",
    "phnom penh": "cambodia",
    "vientiane": "laos",
    "bandar seri begawan": "brunei",
}

# ── Event types ───────────────────────────────────────────────────────────────

EVENT_TYPES: List[Dict[str, Any]] = [
    {"id": "malay_wedding",    "label": "Malay Wedding",                 "category": "wedding"},
    {"id": "chinese_wedding",  "label": "Chinese Wedding / Banquet",     "category": "wedding"},
    {"id": "indian_wedding",   "label": "Indian Wedding",                "category": "wedding"},
    {"id": "filipino_wedding", "label": "Filipino Wedding",              "category": "wedding"},
    {"id": "western_wedding",  "label": "Western / Garden Wedding",      "category": "wedding"},
    {"id": "birthday_party",   "label": "Birthday Party",                "category": "birthday"},
    {"id": "debut",            "label": "Debut / Debutante Ball",        "category": "birthday"},
    {"id": "graduation",       "label": "Graduation Party",              "category": "birthday"},
    {"id": "corporate_lunch",  "label": "Corporate Lunch / Seminar",     "category": "corporate"},
    {"id": "corporate_gala",   "label": "Corporate Gala Dinner",         "category": "corporate"},
    {"id": "product_launch",   "label": "Product Launch / Networking",   "category": "corporate"},
    {"id": "eid_celebration",  "label": "Eid / Raya Celebration",        "category": "cultural"},
    {"id": "chinese_new_year", "label": "Chinese New Year Banquet",      "category": "cultural"},
    {"id": "deepavali",        "label": "Deepavali / Diwali Celebration", "category": "cultural"},
    {"id": "christmas_party",  "label": "Christmas / Year-End Party",    "category": "cultural"},
    {"id": "community_event",  "label": "Community / Public Event",      "category": "community"},
    {"id": "custom",           "label": "Custom / Something Else",       "category": "custom"},
]

_EVENT_KW: Dict[Tuple[str, ...], str] = {
    # Wedding types — require explicit ethnicity/style qualifier before "wedding"
    ("malay wedding", "kahwin", "nikah", "perkahwinan", "kasal melayu"):          "malay_wedding",
    ("chinese wedding", "chinese banquet", "cantonese wedding", "hokkien wedding"): "chinese_wedding",
    ("indian wedding", "hindu wedding", "tamil wedding", "sikh wedding"):          "indian_wedding",
    ("filipino wedding", "pilipino wedding", "philippine wedding"):                "filipino_wedding",
    ("western wedding", "garden wedding", "christian wedding", "church wedding",
     "civil wedding", "chapel wedding", "christian"):                             "western_wedding",
    # Standalone "wedding" is intentionally excluded — use LLM or the numbered list
    ("birthday", "bday", "b'day", "birth day"):                                   "birthday_party",
    ("debut", "debutante", "debut ball"):                                          "debut",
    ("graduation", "grad", "convocation", "commencement"):                        "graduation",
    ("corporate lunch", "seminar", "workshop", "business lunch"):                 "corporate_lunch",
    ("gala", "gala dinner", "corporate dinner", "awards night", "award ceremony"): "corporate_gala",
    ("product launch", "launch event", "networking event", "mixer"):              "product_launch",
    ("eid", "raya", "aidilfitri", "lebaran", "hari raya"):                        "eid_celebration",
    ("chinese new year", "cny", "lunar new year", "imlek"):                       "chinese_new_year",
    ("deepavali", "diwali", "divali"):                                             "deepavali",
    ("christmas", "xmas", "year-end party", "new year eve", "new year party"):    "christmas_party",
    ("community event", "festival", "public event", "street fair"):               "community_event",
}

SERVICE_STYLES: Dict[str, str] = {
    "buffet":      "Buffet — self-service spread with station attendants",
    "semi_buffet": "Semi-Buffet — served starters & desserts, buffet mains",
    "plated":      "Plated / Sit-down — full table service, multiple courses",
    "cocktail":    "Cocktail / Standing — canape circulation and drink stations",
}

# ── Date availability ─────────────────────────────────────────────────────────

_AVAIL_YEAR = 2026
_AVAIL_MONTHS: Dict[int, str] = {5: "May", 6: "June"}

# Pre-booked / unavailable dates
_BLOCKED: set = {
    "2026-05-01",  # Labour Day — venue closed
    "2026-05-16",  # Fully booked
    "2026-05-17",  # Fully booked
    "2026-05-30",  # Fully booked
    "2026-05-31",  # Fully booked
    "2026-06-06",  # Fully booked
    "2026-06-07",  # Fully booked
    "2026-06-20",  # Fully booked
    "2026-06-21",  # Fully booked
}


def _date_ok(d: date) -> bool:
    return d.year == _AVAIL_YEAR and d.month in _AVAIL_MONTHS and d.isoformat() not in _BLOCKED


def _available_in_month(month: int) -> List[date]:
    _, days = monthrange(_AVAIL_YEAR, month)
    return [date(_AVAIL_YEAR, month, day) for day in range(1, days + 1)
            if _date_ok(date(_AVAIL_YEAR, month, day))]


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()

    # Strip leading day-name prefix produced by Eve's own output:
    # "Thursday, 25 June 2026"  →  "25 June 2026"
    # "Thursday 25 June 2026"   →  "25 June 2026"
    raw = re.sub(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*[,\s]+", "", raw, flags=re.IGNORECASE)

    # Strip trailing day-abbreviation from the availability grid:
    # "03 Sat"  →  "03"  (treat as day-of-month in current avail month context)
    grid_m = re.match(r"^(\d{1,2})\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)$", raw, re.IGNORECASE)
    if grid_m:
        day = int(grid_m.group(1))
        # Try May then June of the availability year
        for month in _AVAIL_MONTHS:
            try:
                return date(_AVAIL_YEAR, month, day)
            except ValueError:
                pass
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    # "May 15", "15 May", "15th May", "May 15th"
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?$", raw, re.IGNORECASE)
    if m:
        try:
            yr = int(m.group(3)) if m.group(3) else _AVAIL_YEAR
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {yr}", "%d %B %Y").date()
        except ValueError:
            pass
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?$", raw, re.IGNORECASE)
    if m:
        try:
            yr = int(m.group(3)) if m.group(3) else _AVAIL_YEAR
            return datetime.strptime(f"{m.group(2)} {m.group(1)} {yr}", "%d %B %Y").date()
        except ValueError:
            pass
    return None


def _parse_time(raw: str) -> Optional[str]:
    """Return 'HH:MM' or None."""
    raw = raw.strip().lower().replace(".", ":").replace(" ", "")
    m = re.match(r"(\d{1,2})(?::(\d{2}))?(am|pm)?$", raw)
    if not m:
        return None
    h, mins, period = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if period == "pm" and h < 12:
        h += 12
    elif period == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}" if 8 <= h <= 23 else None


def _fmt_time(t: str) -> str:
    """'19:00' -> '7:00 PM'"""
    try:
        h, m = int(t[:2]), int(t[3:5])
        period = "AM" if h < 12 else "PM"
        dh = h if h <= 12 else h - 12
        if dh == 0:
            dh = 12
        return f"{dh}:{m:02d} {period}"
    except Exception:
        return t


# ── Pricing estimates ─────────────────────────────────────────────────────────

_PRICE_MYR: Dict[Tuple[str, str], float] = {
    ("wedding",   "buffet"):      88.0,
    ("wedding",   "semi_buffet"): 110.0,
    ("wedding",   "plated"):      160.0,
    ("wedding",   "cocktail"):    90.0,
    ("birthday",  "buffet"):      65.0,
    ("birthday",  "plated"):      105.0,
    ("birthday",  "cocktail"):    70.0,
    ("corporate", "buffet"):      95.0,
    ("corporate", "plated"):      155.0,
    ("corporate", "cocktail"):    82.0,
    ("cultural",  "buffet"):      78.0,
    ("cultural",  "plated"):      130.0,
    ("community", "buffet"):      60.0,
    ("custom",    "buffet"):      75.0,
    ("custom",    "plated"):      130.0,
    ("default",   "buffet"):      75.0,
    ("default",   "plated"):      130.0,
    ("default",   "cocktail"):    72.0,
    ("default",   "semi_buffet"): 95.0,
}

_FOREX: Dict[str, float] = {
    "MYR": 1.0,    "PHP": 13.0,  "SGD": 0.30,
    "IDR": 3600.0, "THB": 7.8,   "VND": 5600.0,
    "MMK": 2900.0, "KHR": 1120.0,"BND": 0.30, "LAK": 22000.0,
}


def _estimate(cat: str, style: str, guests: int, currency: str) -> Tuple[float, float]:
    per_myr = _PRICE_MYR.get((cat, style)) or _PRICE_MYR.get(("default", style)) or 75.0
    rate = _FOREX.get(currency, 1.0)
    ph = per_myr * rate
    return ph, ph * guests


# ── Booking store ─────────────────────────────────────────────────────────────

_BOOKINGS: Dict[str, Dict[str, Any]] = {}


def _gen_bid(event_date: str) -> str:
    dp = event_date.replace("-", "")[:8]
    sfx = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"EVE-{dp}-{sfx}"


# ── State identifiers ─────────────────────────────────────────────────────────

ST_MAIN    = "main"
ST_COUNTRY = "country"
ST_EVENT   = "event"
ST_MENU    = "menu"
ST_DATE    = "date"
ST_TIME    = "time"
ST_GUESTS  = "guests"
ST_DIETARY = "dietary"
ST_STYLE   = "style"
ST_BUDGET  = "budget"
ST_NAME    = "name"
ST_PHONE   = "phone"
ST_CONFIRM = "confirm"

_BOOKING_FLOW = [
    ST_COUNTRY, ST_EVENT, ST_MENU, ST_DATE, ST_TIME,
    ST_GUESTS, ST_DIETARY, ST_STYLE, ST_BUDGET, ST_NAME, ST_PHONE, ST_CONFIRM,
]

_FIELD_LABELS = {
    ST_COUNTRY: "Country",
    ST_EVENT:   "Event Type",
    ST_MENU:    "Menu / Cuisine Preferences",
    ST_DATE:    "Event Date",
    ST_TIME:    "Event Time",
    ST_GUESTS:  "Number of Guests",
    ST_DIETARY: "Dietary Requirements",
    ST_STYLE:   "Service Style",
    ST_BUDGET:  "Budget per Head",
    ST_NAME:    "Your Full Name",
    ST_PHONE:   "WhatsApp Number",
}

# ── Catalogue ─────────────────────────────────────────────────────────────────

_CATALOGUE = [
    {
        "n": 1,
        "name": "Royal Malay Wedding Feast",
        "desc": (
            "Our signature Malay wedding package: Nasi Minyak, Chicken & Beef Rendang,\n"
            "     Ayam Masak Merah, 3 gulai varieties, fresh ulam spread, and a live satay\n"
            "     station. Full setup, chafing dishes, and teardown included."
        ),
        "for":   "Malay Weddings, Eid Celebrations",
        "style": "Buffet",
        "pax":   "100 – 1,000 pax",
        "from":  "MYR 85/pax",
        "stars": ["12-dish spread", "Live satay station", "Pandan layer cake", "JAKIM halal certified"],
    },
    {
        "n": 2,
        "name": "Corporate Gala Dinner — 5-Course Plated",
        "desc": (
            "Sophisticated Continental-Asian fusion for VIP corporate events. 5-course\n"
            "     plated service: amuse-bouche, soup, salad, pan-seared main, and dessert.\n"
            "     White-glove table service with full linen and centrepiece setup."
        ),
        "for":   "Corporate Galas, Award Dinners, VIP Events",
        "style": "Plated",
        "pax":   "50 – 400 pax",
        "from":  "MYR 150/pax",
        "stars": ["5-course custom menu", "White-glove service", "Full A/V coordination"],
    },
    {
        "n": 3,
        "name": "Filipino Celebration Feast",
        "desc": (
            "A whole-roasted lechon centrepiece surrounded by 10 beloved Filipino classics:\n"
            "     Kare-Kare, Sinigang, Crispy Pata, Pancit Palabok, and more. Ideal for\n"
            "     Filipino weddings, debuts, and milestone birthdays."
        ),
        "for":   "Filipino Weddings, Birthdays, Debuts, Reunions",
        "style": "Buffet",
        "pax":   "80 – 800 pax",
        "from":  "PHP 1,800/pax",
        "stars": ["Whole lechon centrepiece", "10-dish Filipino spread", "Halo-Halo dessert station"],
    },
    {
        "n": 4,
        "name": "Celebration Birthday Package",
        "desc": (
            "Flexible buffet package for all birthday sizes. Choose from 3 cuisine bases\n"
            "     (Malay, Chinese, Western fusion). Includes themed table setup, cake table,\n"
            "     and beverage station."
        ),
        "for":   "Birthdays, Graduations, Anniversaries",
        "style": "Buffet / Semi-Buffet",
        "pax":   "30 – 300 pax",
        "from":  "MYR 65/pax",
        "stars": ["Customisable 8-dish menu", "Cake table setup", "Kids-friendly options"],
    },
    {
        "n": 5,
        "name": "Cocktail & Canape Reception",
        "desc": (
            "Elegant standing reception with roaming canape service and a live mocktail bar.\n"
            "     Ideal for product launches and corporate mixers. Includes 6 hot + 4 cold\n"
            "     canapes, seasonal fruit display, and dessert bites."
        ),
        "for":   "Product Launches, Networking Events, Corporate Mixers",
        "style": "Cocktail / Standing",
        "pax":   "30 – 250 pax",
        "from":  "MYR 70/pax",
        "stars": ["10 canape varieties", "Live mocktail bar", "2-hour flexible package"],
    },
]

# ── Menu suggestions per event type ──────────────────────────────────────────

_MENU_SUGGESTIONS: Dict[str, List[str]] = {
    "malay_wedding": [
        "Traditional Malay Feast — Nasi Minyak, Rendang, Ayam Masak Merah, Sayur Lodeh, live Satay",
        "Modern Malay-Continental Fusion — Western starters, Malay mains, Onde-onde & Pandan cake desserts",
        "Grand Royal Spread — 14 dishes: Nasi Briyani, Ikan Bakar, Gulai Kawah, live carving + Ulam corner",
    ],
    "chinese_wedding": [
        "Classic Chinese Banquet — 10-course Cantonese set: shark fin soup, Peking duck, steamed fish",
        "Chinese-Malay Fusion Buffet — Char Siew, Nasi Lemak, Roast Duck, Chilli Crab station",
        "Modern Dim Sum & Main Buffet — Dim Sum trolley service + main course buffet + mango pudding",
    ],
    "corporate_gala": [
        "Continental 5-Course — Amuse-bouche, Lobster Bisque, Caesar Salad, Pan-seared Barramundi, Tiramisu",
        "Asian Fusion Buffet — Japanese, Thai, Malaysian live stations plus teppanyaki corner",
        "Cocktail Reception — 10 canape varieties, live mocktail bar, macaroon tower, cheese station",
    ],
    "birthday_party": [
        "Casual SEA Buffet — 8 dishes across Malay, Chinese, and Western with satay and noodles bar",
        "Kids Fun Spread — nuggets, mini burgers, satay, fruit skewers, juice bar, cake table",
        "Themed Cuisine Night — choose 1 cuisine: Filipino, Thai, or Mediterranean full spread",
    ],
    "filipino_wedding": [
        "Traditional Filipino Feast — Lechon centrepiece, Kare-Kare, Pancit, Sinigang, Leche Flan",
        "Modern Filipino Buffet — 12 dishes with live Lechon carving and Halo-Halo dessert station",
        "Filipino-Malay Fusion — Lechon, Rendang, Adobo, Nasi Lemak corner, Bibingka dessert",
    ],
    "eid_celebration": [
        "Classic Raya Spread — Nasi Impit, Rendang, Ketupat, Kuah Kacang, Serunding, Kuih Raya",
        "Modern Eid Buffet — Nasi Minyak, 4 curries, live Murtabak station, Pandan cake desserts",
        "Kampung Feast — Open buffet with traditional earthenware, Ikan Bakar, Ulam Raja, Tempoyak",
    ],
    "christmas_party": [
        "Western Christmas Feast — Roast Turkey, Gammon Ham, Yule Log, mashed potato, bread rolls",
        "Asian-Christmas Fusion — Roast Chicken, Beef Rendang, pasta corner, pavlova dessert",
        "Cocktail Christmas Party — Canape service, mulled apple cider bar, Christmas cookie station",
    ],
}


# ── Display helpers ───────────────────────────────────────────────────────────

_DIV = "─" * 62


def _eve(msg: str) -> None:
    print(f"\n  Eve: {msg}\n")


def _div(title: str = "") -> None:
    if title:
        pad = max(0, 58 - len(title))
        print(f"\n  ── {title} {'─' * pad}")
    else:
        print(f"\n  {_DIV}")


def _hint() -> None:
    print("  (Type 'back' to edit previous step | 'menu' for main menu)\n")


def _show_main_menu() -> None:
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║           Eve Cater's AI —  iNextLabs 💚              ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Eve: Hi, I'm Eve! I'm {COMPANY}'s smart catering assistant! 😊")
    print("       Choose the below options so we can start.")
    print()
    print("    1.  New Customer")
    print("    2.  View my booking")
    print("    3.  Browse catalogue for ideas")
    print("    4.  How do I use Eve Cater's AI?")
    print("    5.  Chat with a staff")
    print()
    print("  (Type a number or keyword — e.g. '1', 'new', 'view booking')")
    print()


def _show_receipt(b: Dict[str, Any]) -> None:
    bid = b.get("booking_id", "N/A")
    ccy = b.get("currency", "MYR")
    ph = b.get("estimated_per_head", 0)
    total = b.get("estimated_total", 0)
    guests = b.get("guest_count", 0)
    phone = b.get("phone", "")
    try:
        d_fmt = datetime.strptime(b.get("event_date", ""), "%Y-%m-%d").strftime("%A, %d %B %Y")
    except Exception:
        d_fmt = b.get("event_date", "")
    dietary = b.get("dietary_constraints", [])

    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║           EVE CATER'S AI — BOOKING RECEIPT 🎉           ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Booking ID   : {bid}")
    print(f"  Status       : ✅ Confirmed — Awaiting Staff Confirmation")
    _div("EVENT DETAILS")
    print(f"  Event        : {b.get('event_type_label', b.get('event_type', ''))}")
    print(f"  Date & Time  : {d_fmt} at {b.get('event_time', '')}")
    print(f"  Country      : {b.get('country_label', b.get('country', ''))}")
    print(f"  Guests       : {guests} pax")
    print(f"  Service      : {b.get('service_style_label', b.get('service_style', ''))}")
    print(f"  Dietary      : {', '.join(dietary) if dietary else 'None'}")
    _div("MENU PREFERENCES")
    print(f"  {b.get('menu_preferences', 'As discussed with staff')}")
    _div("CUSTOMER DETAILS")
    print(f"  Name         : {b.get('customer_name', '')}")
    print(f"  WhatsApp     : {phone}")
    _div("COST ESTIMATE")
    print(f"  Per Head     : {ccy} {ph:,.2f}")
    print(f"  Total ({guests} pax): {ccy} {total:,.2f}")
    print(f"  (Final pricing confirmed by our team via WhatsApp)")
    _div("NEXT STEPS")
    print(f"  ✅  A staff member will contact you via WhatsApp")
    print(f"       at {phone} within 24 hours to confirm your")
    print(f"       booking and arrange final payment.")
    print(f"  📋  Save your Booking ID: {bid}")
    print(f"  💬  Type 'View my booking' to check status anytime.")
    print()
    print(f"  {'─' * 56}")
    print(f"  Thank you for choosing {BRAND}! Have a wonderful event! 🎊")
    print()


def _show_catalogue() -> None:
    _eve("Here are our featured packages and event inspirations! 🌟")
    for p in _CATALOGUE:
        print(f"  ── Package {p['n']}: {p['name']} ──────────────")
        print(f"     {p['desc']}")
        print(f"     ✅ Suitable for  : {p['for']}")
        print(f"     🍽️  Service style : {p['style']}")
        print(f"     👥 Capacity      : {p['pax']}")
        print(f"     💰 Starting from : {p['from']}")
        print(f"     ⭐ Highlights    : {' | '.join(p['stars'])}")
        print()
    print("  💡 Type a package number (1–5) to start booking it,")
    print("     or 'menu' to return to the main menu.\n")


def _show_how_to_use() -> None:
    _eve(f"Welcome to {BRAND}! Here's everything I can do for you:\n")
    features = [
        ("📋", "New Booking",
         "Tell me your country, event, date, and preferences — I'll build a full plan\n"
         "     with menu, staff, logistics, and a quoted price."),
        ("🗓️", "Date Availability",
         "I'll check live availability in May & June 2026 and help you pick the\n"
         "     perfect slot. I'll show you alternatives if your first choice is taken."),
        ("🍽️", "Menu Suggestions",
         "Ask me for dish ideas, cuisine styles, or live station options. I'll suggest\n"
         "     the ideal spread for your event type and guest count."),
        ("💰", "Pricing Estimates",
         "Get a per-head cost estimate before you commit. I'll show you budget,\n"
         "     standard, and premium tiers based on your event profile."),
        ("📄", "Booking Receipt",
         "After confirmation I'll generate a Booking ID and a full receipt.\n"
         "     A staff member will WhatsApp you to finalise payment."),
        ("🔍", "View Your Booking",
         "Use your Booking ID to pull up your receipt and status at any time."),
        ("✏️", "Edit Before Confirming",
         "Change any detail — date, menu, guest count, budget — right up until\n"
         "     you confirm. After confirmation, contact staff to modify."),
        ("📦", "Browse Catalogue",
         "Explore 5 curated event packages for inspiration — from royal Malay\n"
         "     weddings to Filipino feasts to cocktail receptions."),
        ("💬", "Chat with Staff",
         "Need a human? I'll give you our WhatsApp, email, and office hours."),
        ("🌏", "Southeast Asia Coverage",
         "We serve events in Malaysia, Philippines, Singapore, Indonesia, Thailand,\n"
         "     Vietnam, Myanmar, Cambodia, Brunei, and Laos."),
    ]
    for emoji, title, desc in features:
        print(f"  {emoji}  {title}")
        print(f"     {desc}\n")
    print("  Type '1' to start a new booking, or 'menu' for the main menu.\n")


def _show_chat_staff() -> None:
    _eve("Connecting you with our catering team! 👋\n")
    print("  Our staff can help with:")
    print("    •  Complex or highly customised menus")
    print("    •  Large events (1,000+ guests)")
    print("    •  Last-minute bookings or urgent requests")
    print("    •  On-site tasting sessions and venue visits")
    print()
    print("  ── Contact Our Team ─────────────────────────────────────")
    print("  📱 WhatsApp   : +60-11-1234 5678  (Malaysia & SEA)")
    print("               : +63-917-1234 5678  (Philippines)")
    print("  📧 Email      : hello@evecaters.ai")
    print("  🕐 Hours      : Monday – Saturday, 9:00 AM – 6:00 PM")
    print("  🌐 Website    : www.evecaters.ai")
    print()
    print("  Staff typically respond within 1 business hour.")
    print()
    print("  (Type 'menu' to return to the main menu)\n")


# ── Provider helpers ──────────────────────────────────────────────────────────

_EVE_SYSTEM = (
    f"You are {EVE}, a warm, friendly AI catering assistant for {COMPANY} in Southeast Asia. "
    "You help customers plan catering events — weddings, birthdays, corporate dinners, and more. "
    "You are professional, enthusiastic, and naturally use 1-2 emojis per message. "
    "Keep every reply concise (1-3 sentences). "
    "Never ask multiple questions at once — the booking flow handles that step by step. "
    "Never break character or mention that you are a language model."
)


def _build_provider():
    try:
        from app.providers import build_provider
        from app.providers.mock_provider import MockProvider
        p = build_provider()
        return None if isinstance(p, MockProvider) else p
    except Exception:
        return None


def _check_llm_status(provider) -> None:
    """Print a one-line status at startup showing whether Ollama is reachable."""
    model = os.getenv("MODEL_NAME", "?")
    if not provider:
        print(f"  ℹ️  Running in guided mode — AI model not configured.")
        print()
        return
    try:
        provider.generate("Reply with the single word: ready")
        print(f"  ✅ AI model online ({model}) — {BRAND} is fully powered! 🤖")
    except Exception as exc:
        print(f"  ⚠️  AI model offline ({model}: {exc}) — running in guided mode.")
    print()


def _call_agents(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # PLATFORM: POST /invocations respects ORCHESTRATION_BACKEND / USE_MS_AGENT_FRAMEWORK (see app.platform)
    payload = {k: v for k, v in payload.items() if not k.startswith("_")}
    payload.setdefault("thread_id", str(uuid.uuid4()))
    try:
        r = requests.post(f"{BASE_URL}/invocations", json=payload, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ── Tool: web search ──────────────────────────────────────────────────────────

_TOOL_RE = re.compile(r"\[SEARCH:\s*([^\]]+)\]", re.IGNORECASE)


def _web_search(query: str, max_results: int = 5) -> str:
    """Search the web using the `ddgs` package (DuckDuckGo, no API key).
    Falls back to the DDG Instant Answer API if the package is unavailable."""
    # Primary: ddgs package — returns real search results
    try:
        from ddgs import DDGS  # type: ignore
        results = list(DDGS().text(query, max_results=max_results))
        if results:
            lines = [f"• {r['title']}: {r['body'][:180]}" for r in results]
            return "\n".join(lines)
    except ImportError:
        pass  # fall through to API fallback
    except Exception as exc:
        return f"Web search error: {exc}"

    # Fallback: DuckDuckGo Instant Answer API
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        parts: List[str] = []
        if data.get("AbstractText"):
            parts.append(data["AbstractText"][:400])
        for topic in (data.get("RelatedTopics") or [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                parts.append(f"• {topic['Text'][:200]}")
        return "\n".join(parts) if parts else "No results found for that query."
    except Exception as exc:
        return f"Web search unavailable: {exc}"


# ── Main chat engine ──────────────────────────────────────────────────────────

class EveChat:
    def __init__(self) -> None:
        self.state: str = ST_MAIN
        self.s: Dict[str, Any] = {}           # booking session data
        self.history: List[Dict[str, str]] = []  # rolling LLM conversation turns
        self.provider = _build_provider()

    # ── LLM helpers ───────────────────────────────────────────────────────

    def _llm_classify(self, question: str, raw: str, options: List[str]) -> Optional[str]:
        """Ask the LLM to map raw user input to the best option label. Returns label or None."""
        if not self.provider:
            return None
        numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
        prompt = (
            f"A customer is answering this question: \"{question}\"\n"
            f"They said: \"{raw}\"\n"
            f"Choose the single best matching option:\n{numbered}\n\n"
            "Reply with ONLY the option number (e.g. '5') or 'none' if nothing fits."
        )
        msgs = [
            {"role": "system", "content": "You are a precise intent classifier. Reply with only a number or 'none'."},
            {"role": "user",   "content": prompt},
        ]
        try:
            reply = self.provider.chat(msgs).strip()
            m = re.match(r"^(\d+)", reply)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(options):
                    return options[idx]
        except Exception:
            pass
        return None

    def _llm_ack(self, user_said: str, confirmed_as: str, next_topic: str) -> Optional[str]:
        """Generate a warm conversational acknowledgment for what Eve detected."""
        if not self.provider:
            return None
        context = "\n".join(
            f"{m['role'].title()}: {m['content']}" for m in self.history[-4:]
        ) if self.history else ""
        prompt = (
            f"{'Previous conversation:\\n' + context + chr(10) if context else ''}"
            f"The customer just said: \"{user_said}\"\n"
            f"You recognised this as: \"{confirmed_as}\"\n"
            f"Next you will ask about: {next_topic}\n\n"
            "Write a brief warm acknowledgment (1-2 sentences) that:\n"
            "1. Reflects back what the customer said naturally\n"
            "2. Confirms what you recorded (if different from what they said)\n"
            "3. Sounds like it naturally leads to the next topic\n"
            "Use 1-2 emojis. Be concise. Do NOT ask the next question — just acknowledge."
        )
        msgs = [
            {"role": "system", "content": _EVE_SYSTEM},
            {"role": "user",   "content": prompt},
        ]
        try:
            reply = self.provider.chat(msgs).strip()
            # phi3-family models sometimes tack on a follow-up question; remove it
            # so it doesn't collide with the state machine's own prompt.
            reply = re.sub(r"\s+[A-Z][^.!?]{5,}\?\s*$", "", reply).strip()
            return reply or None
        except Exception:
            return None

    def _llm_chat(self, user_msg: str, system_hint: str = "") -> Optional[str]:
        """Free conversational LLM reply using rolling history. Returns text or None."""
        if not self.provider:
            return None
        sys_content = f"{_EVE_SYSTEM}\n\n{system_hint}".strip() if system_hint else _EVE_SYSTEM
        msgs = [{"role": "system", "content": sys_content}]
        msgs += self.history[-6:]  # last 3 turns of context
        msgs.append({"role": "user", "content": user_msg})
        try:
            reply = self.provider.chat(msgs).strip()
            # Record in history
            self.history.append({"role": "user",      "content": user_msg})
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception:
            return None

    def _record(self, user_said: str, eve_said: str) -> None:
        """Append a turn to rolling conversation history."""
        self.history.append({"role": "user",      "content": user_said})
        self.history.append({"role": "assistant", "content": eve_said})

    # Patterns emitted by phi3/phi-family models from their training data —
    # these must never appear in customer-facing output.
    _ARTIFACT_RE = re.compile(
        r"^#{1,6}\s*(instruction|solution|follow.up|follow up|example|answer:|note:|"
        r"step\s+\d|task\s+\d|question\s+\d|problem\s+\d|output:|input:)",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_artifact(line: str) -> bool:
        stripped = line.strip()
        return bool(EveChat._ARTIFACT_RE.match(stripped))

    @staticmethod
    def _clean_reply(text: str) -> str:
        """Remove any artifact lines from a completed LLM reply."""
        out = []
        for line in text.splitlines():
            if EveChat._is_artifact(line):
                break  # everything after first artifact is noise
            out.append(line)
        return "\n".join(out).strip()

    def _stream_or_call(self, msgs: List[Dict[str, str]]) -> str:
        """Stream LLM tokens line-by-line to the terminal, filtering training
        artifacts before they ever appear.  Falls back to a blocking call when
        streaming is unavailable.  Returns the clean reply text."""
        try:
            if hasattr(self.provider, "stream_chat"):
                sys.stdout.write("\n  Eve: ")
                sys.stdout.flush()
                all_chunks: List[str] = []
                line_buf = ""

                for token in self.provider.stream_chat(msgs):
                    all_chunks.append(token)
                    line_buf += token

                    # Process every complete line that ended with \n
                    while "\n" in line_buf:
                        nl = line_buf.index("\n")
                        complete = line_buf[:nl]
                        line_buf  = line_buf[nl + 1:]

                        if self._is_artifact(complete):
                            # Discard this line and everything that follows
                            line_buf = ""
                            # Signal outer loop to stop consuming
                            all_chunks.append("\x00STOP\x00")
                            break
                        sys.stdout.write(complete + "\n")
                        sys.stdout.flush()
                    else:
                        continue
                    break  # artifact stop signal

                # Print whatever safe partial line remains
                if line_buf and not self._is_artifact(line_buf):
                    sys.stdout.write(line_buf)
                    sys.stdout.flush()

                sys.stdout.write("\n\n")
                sys.stdout.flush()

                full = "".join(all_chunks).replace("\x00STOP\x00", "")
                return self._clean_reply(full)

            # Non-streaming fallback
            reply = self._clean_reply(self.provider.chat(msgs).strip())
            _eve(reply)
            return reply
        except Exception:
            return ""

    def _session_context(self) -> str:
        """Return a compact summary of confirmed booking details for the LLM."""
        s = self.s
        parts: List[str] = []
        if s.get("country_label"):
            parts.append(f"Country: {s['country_label']}")
        if s.get("event_type_label"):
            parts.append(f"Event type: {s['event_type_label']}")
        if s.get("menu_preferences"):
            parts.append(f"Menu preference: {s['menu_preferences']}")
        if s.get("event_date"):
            parts.append(f"Event date: {s['event_date']}")
        if s.get("event_time"):
            parts.append(f"Event time: {s['event_time']}")
        if s.get("guest_count"):
            parts.append(f"Guests: {s['guest_count']}")
        if s.get("dietary_constraints"):
            parts.append(f"Dietary: {', '.join(str(d) for d in s['dietary_constraints'])}")
        if s.get("service_style_label"):
            parts.append(f"Service style: {s['service_style_label']}")
        if s.get("budget_per_head"):
            ccy = s.get("currency", "MYR")
            parts.append(f"Budget: {ccy} {s['budget_per_head']}/pax")
        if s.get("customer_name"):
            parts.append(f"Customer name: {s['customer_name']}")
        if not parts:
            return ""
        return "Confirmed booking details so far:\n" + "\n".join(f"  - {p}" for p in parts)

    def _eve_llm_stream(
        self,
        system_hint: str,
        user_msg: str,
        allow_tools: bool = False,
    ) -> str:
        """Main LLM conversation driver.

        Streams Eve's reply token-by-token.  When *allow_tools* is True the
        model may insert ``[SEARCH: <query>]`` markers; the system executes
        each search and feeds results back for a second reply pass.

        Falls back silently to an empty string when the provider is offline —
        callers should then display their own hardcoded fallback message.
        """
        if not self.provider:
            return ""

        tool_note = (
            "\n\nTool — web search: when the user asks for online suggestions, "
            "current trends, or real-world examples, embed [SEARCH: your query] "
            "in your reply and the system will fetch live results for you."
        ) if allow_tools else ""

        sys_content = f"{_EVE_SYSTEM}{tool_note}"
        ctx_parts: List[str] = []
        session_ctx = self._session_context()
        if session_ctx:
            ctx_parts.append(session_ctx)
        if system_hint:
            ctx_parts.append(system_hint)
        if ctx_parts:
            sys_content = f"{sys_content}\n\n{chr(10).join(ctx_parts)}"

        msgs: List[Dict[str, str]] = [{"role": "system", "content": sys_content}]
        msgs += self.history[-6:]
        msgs.append({"role": "user", "content": user_msg})

        reply = self._stream_or_call(msgs)
        if not reply:
            return ""

        # Execute any [SEARCH: …] tool calls the model emitted
        tool_hits = _TOOL_RE.findall(reply)
        if tool_hits and allow_tools:
            search_blocks: List[str] = []
            for q in tool_hits:
                q = q.strip()
                print(f"  🔍 Searching online: {q} …")
                result = _web_search(q)
                search_blocks.append(f"Query: {q}\n{result}")

            msgs.append({"role": "assistant", "content": reply})
            msgs.append({
                "role": "user",
                "content": (
                    "Web search results:\n\n"
                    + "\n\n---\n".join(search_blocks)
                    + "\n\nNow give the customer a clear, friendly summary with "
                      "3–5 concrete suggestions based on these results. "
                      "Do NOT include [SEARCH: …] markers in your reply."
                ),
            })
            reply2 = self._stream_or_call(msgs)
            if reply2:
                reply = reply2

        self.history.append({"role": "user",      "content": user_msg})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    # ── Run loop ──────────────────────────────────────────────────────────

    def run(self) -> None:
        _check_llm_status(self.provider)
        _show_main_menu()
        while True:
            try:
                raw = input("  You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n  Eve: Thank you for using {BRAND}! See you soon! 💚\n")
                break
            if not raw:
                continue
            low = raw.lower()
            if low in ("quit", "exit", "bye", "goodbye"):
                print(f"\n  Eve: Thank you for using {BRAND}! Have a wonderful day! 💚\n")
                break
            if low in ("menu", "main menu", "home", "0", "start over", "restart"):
                self._reset()
                _show_main_menu()
                continue
            # Allow navigation to any main menu option from any state
            if self._try_global_nav(raw):
                continue
            self._dispatch(raw)

    def _dispatch(self, raw: str) -> None:
        {
            ST_MAIN:     self._h_main,
            ST_COUNTRY:  self._h_country,
            ST_EVENT:    self._h_event,
            ST_MENU:     self._h_menu,
            ST_DATE:     self._h_date,
            ST_TIME:     self._h_time,
            ST_GUESTS:   self._h_guests,
            ST_DIETARY:  self._h_dietary,
            ST_STYLE:    self._h_style,
            ST_BUDGET:   self._h_budget,
            ST_NAME:     self._h_name,
            ST_PHONE:    self._h_phone,
            ST_CONFIRM:  self._h_confirm,
            "view":      self._h_view,
            "catalogue": self._h_catalogue,
            "howto":     self._h_howto,
            "staff":     self._h_staff,
        }.get(self.state, self._h_main)(raw)

    def _reset(self) -> None:
        self.state = ST_MAIN
        self.s = {}

    def _back(self) -> None:
        if self.state not in _BOOKING_FLOW:
            self._reset()
            _show_main_menu()
            return
        idx = _BOOKING_FLOW.index(self.state)
        if idx == 0:
            self._reset()
            _show_main_menu()
        else:
            self.state = _BOOKING_FLOW[idx - 1]
            self._reprompt(self.state)

    def _reprompt(self, st: str) -> None:
        {
            ST_COUNTRY: self._ask_country,
            ST_EVENT:   self._ask_event,
            ST_MENU:    self._ask_menu,
            ST_DATE:    self._ask_date,
            ST_TIME:    self._ask_time,
            ST_GUESTS:  self._ask_guests,
            ST_DIETARY: self._ask_dietary,
            ST_STYLE:   self._ask_style,
            ST_BUDGET:  self._ask_budget,
            ST_NAME:    self._ask_name,
            ST_PHONE:   self._ask_phone,
            ST_CONFIRM: self._ask_confirm,
        }.get(st, lambda: None)()

    # ── MAIN MENU ─────────────────────────────────────────────────────────

    def _try_global_nav(self, raw: str) -> bool:
        """Check whether the input matches a main-menu option regardless of current state.
        If so, navigate directly and return True; otherwise return False."""
        low = raw.lower()
        # Only intercept when not already at the main menu
        if self.state == ST_MAIN:
            return False
        # Must be a reasonably explicit navigation phrase, not just a stray keyword
        nav2 = ("view my booking", "view booking", "check my booking", "see my booking",
                "my booking id", "booking status", "find my booking", "look up booking")
        nav3 = ("browse catalogue", "browse catalog", "see catalogue", "view catalogue",
                "show catalogue", "ideas", "packages", "inspiration", "browse ideas")
        nav4 = ("how do i use", "how to use", "feature guide", "what can eve", "help guide")
        nav5 = ("chat with staff", "speak to staff", "talk to staff", "contact staff",
                "speak to human", "talk to human", "need human", "chat with a staff")
        nav1 = ("new customer", "start new booking", "make new booking", "new booking")
        if any(p in low for p in nav2):
            self._reset()
            self.state = "view"
            _eve("Please enter your Booking ID. 🔍\n"
                 "  (Format: EVE-YYYYMMDD-XXXXX)\n  (Type 'menu' to go back)")
            return True
        if any(p in low for p in nav3):
            self._reset()
            self.state = "catalogue"
            _show_catalogue()
            return True
        if any(p in low for p in nav4):
            self._reset()
            self.state = "howto"
            _show_how_to_use()
            return True
        if any(p in low for p in nav5):
            self._reset()
            self.state = "staff"
            _show_chat_staff()
            return True
        if any(p in low for p in nav1):
            self._reset()
            self.state = ST_COUNTRY
            self._ask_country()
            return True
        return False

    def _h_main(self, raw: str) -> None:
        low = raw.lower()
        # Guard: "view"/"browse" phrases should never fall into option 1
        # "book" removed — too generic (collides with "view my booking")
        is_new = (
            raw.strip() == "1"
            or (any(k in low for k in ("new", "start", "customer"))
                and not any(k in low for k in ("view", "browse", "catalogue", "catalog",
                                               "my booking", "lookup", "status")))
        )
        if is_new:
            self.state = ST_COUNTRY
            self._ask_country()
        elif raw.strip() == "2" or any(k in low for k in ("view", "my booking", "status", "receipt", "lookup")):
            self.state = "view"
            _eve("Please enter your Booking ID. 🔍\n"
                 "  (Format: EVE-YYYYMMDD-XXXXX)\n"
                 "  (Type 'menu' to go back)")
        elif raw.strip() == "3" or any(k in low for k in ("browse", "catalogue", "catalog", "idea", "package", "inspiration")):
            self.state = "catalogue"
            _show_catalogue()
        elif raw.strip() == "4" or any(k in low for k in ("how", "guide", "help", "use", "what can", "about")):
            self.state = "howto"
            _show_how_to_use()
        elif raw.strip() == "5" or any(k in low for k in ("staff", "human", "agent", "contact", "speak", "chat")):
            self.state = "staff"
            _show_chat_staff()
        else:
            # Let the LLM handle natural language and route the customer
            hint = (
                "The customer is at the main menu and said something unexpected. "
                "Respond warmly, try to understand what they want, and gently guide "
                "them to one of these options:\n"
                "  1. New Customer — start a new catering booking\n"
                "  2. View my booking — look up an existing booking by ID\n"
                "  3. Browse catalogue for ideas — event packages\n"
                "  4. How do I use Eve Cater's AI? — feature guide\n"
                "  5. Chat with a staff — speak to a human\n"
                "If they seem to be asking about catering, weddings, food, or events, "
                "encourage them to start option 1."
            )
            reply = self._eve_llm_stream(hint, raw, allow_tools=False)
            if not reply:
                _eve("I didn't quite catch that! 😊 Please choose an option:\n\n"
                     "    1.  New Customer\n"
                     "    2.  View my booking\n"
                     "    3.  Browse catalogue for ideas\n"
                     "    4.  How do I use Eve Cater's AI?\n"
                     "    5.  Chat with a staff")

    # ── Side flows ────────────────────────────────────────────────────────

    def _h_view(self, raw: str) -> None:
        bid = raw.strip().upper()
        if not bid.startswith("EVE-"):
            _eve("That doesn't look like a valid Booking ID.\n"
                 "  Format: EVE-YYYYMMDD-XXXXX\n"
                 "  Type 'menu' to go back.")
            return
        b = _BOOKINGS.get(bid)
        if not b:
            _eve(f"I couldn't find booking '{bid}'. 😔\n"
                 f"  Please double-check the ID, or type 'menu' to go back.")
            return
        _show_receipt(b)
        self._return_to_menu()

    def _h_catalogue(self, raw: str) -> None:
        low = raw.lower().strip()
        if raw.strip().isdigit() and 1 <= int(raw.strip()) <= len(_CATALOGUE):
            pkg = _CATALOGUE[int(raw.strip()) - 1]
            _eve(f"Great choice — '{pkg['name']}'! 🎊\n  Let's start your booking.")
            self.s["menu_preferences"] = pkg["name"]
            self.state = ST_COUNTRY
            self._ask_country()
        elif any(k in low for k in ("book", "want", "choose", "pick")):
            _eve("Type the package number (1–5) to book it, or 'menu' to go back.")
        else:
            _eve("Type a package number (1–5) to start booking, or 'menu' to go back.")

    def _h_howto(self, raw: str) -> None:
        low = raw.lower().strip()
        if raw.strip() == "1" or any(k in low for k in ("book", "start", "new")):
            self.state = ST_COUNTRY
            self._ask_country()
        else:
            _eve("Type '1' to start a new booking, or 'menu' for the main menu.")

    def _h_staff(self, raw: str) -> None:
        _eve("Our team will be in touch shortly! 😊\n"
             "  Type 'menu' to return to the main menu, or 'quit' to exit.")

    def _return_to_menu(self) -> None:
        self.state = ST_MAIN
        self.s = {}
        _eve("What would you like to do next?\n\n"
             "    1.  New Customer\n"
             "    2.  View my booking\n"
             "    3.  Browse catalogue for ideas\n"
             "    4.  How do I use Eve Cater's AI?\n"
             "    5.  Chat with a staff")

    # ── BOOKING FLOW ──────────────────────────────────────────────────────

    # ── 1. Country ──

    def _ask_country(self) -> None:
        _eve("Let's get started! 🌏\n\n"
             "  Which country will your event be held in?\n\n"
             "  We currently serve:\n"
             "    Malaysia 🇲🇾  |  Philippines 🇵🇭  |  Singapore 🇸🇬  |  Indonesia 🇮🇩\n"
             "    Thailand 🇹🇭  |  Vietnam 🇻🇳       |  Myanmar 🇲🇲    |  Cambodia 🇰🇭\n"
             "    Brunei 🇧🇳    |  Laos 🇱🇦")
        _hint()

    def _h_country(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        low = raw.lower().strip()
        key = _COUNTRY_ALIASES.get(low)
        if not key:
            for k, info in SEA_COUNTRIES.items():
                if k in low or info["name"].lower() in low:
                    key = k; break
        if not key:
            _eve(f"Sorry — we currently only serve Southeast Asian countries. 😊\n"
                 f"  Supported: {', '.join(c['name'] for c in SEA_COUNTRIES.values())}")
            return
        info = SEA_COUNTRIES[key]
        self.s.update(country=key, country_label=info["name"], currency=info["currency"])
        hint = (f"The customer chose {info['name']} as their event country. "
                "Acknowledge warmly and confirm the country.")
        if not self._eve_llm_stream(hint, raw):
            msg = f"Great — {info['flag']} {info['name']}! We cater events there."
            _eve(msg)
            self._record(raw, msg)
        self.state = ST_EVENT
        self._ask_event()

    # ── 2. Event type ──

    def _ask_event(self) -> None:
        _eve("What type of event are you planning? 🎉\n")
        for i, et in enumerate(EVENT_TYPES, 1):
            print(f"    {i:>2}.  {et['label']}")
        print()
        print("  Or just describe it naturally — I'll figure it out! 😊")
        _hint()

    def _h_event(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        low = raw.lower().strip()

        # Numeric pick
        if raw.strip().isdigit():
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(EVENT_TYPES):
                self._set_event(EVENT_TYPES[idx], raw); return
            _eve(f"Please enter 1–{len(EVENT_TYPES)}."); return

        # Exact label / id match
        for et in EVENT_TYPES:
            if et["id"].replace("_", " ") in low or et["label"].lower() in low:
                self._set_event(et, raw); return

        # Keyword map
        for kws, eid in _EVENT_KW.items():
            if any(k in low for k in kws):
                et = next((e for e in EVENT_TYPES if e["id"] == eid), None)
                if et:
                    self._set_event(et, raw); return

        # LLM fallback — let Ollama classify the free-text description
        if self.provider:
            option_labels = [et["label"] for et in EVENT_TYPES]
            matched_label = self._llm_classify(
                "What type of event are you planning?", raw, option_labels
            )
            if matched_label:
                et = next((e for e in EVENT_TYPES if e["label"] == matched_label), None)
                if et and et["id"] != "custom":
                    self._set_event(et, raw); return

        # Accept as custom event
        _eve(f"I'll note this as a custom event: '{raw.title()}' ✏️")
        self._set_event({"id": "custom", "label": raw.title(), "category": "custom"}, raw)

    def _set_event(self, et: Dict[str, Any], user_said: str = "") -> None:
        self.s.update(event_type=et["id"], event_type_label=et["label"],
                      event_category=et.get("category", "custom"))
        label = et["label"]
        hint = (
            f"The customer described their event as \"{user_said or label}\" "
            f"and you identified it as \"{label}\". "
            "Acknowledge it naturally — if what they said differs from the label, "
            "gently confirm what you recorded. Keep it warm and brief."
        )
        if not self._eve_llm_stream(hint, user_said or label):
            msg = f"Perfect — {label}! 🎊"
            _eve(msg)
            if user_said:
                self._record(user_said, msg)
        self.state = ST_MENU
        self._ask_menu()

    # ── 3. Menu preferences ──

    def _ask_menu(self) -> None:
        evt = self.s.get("event_type_label", "your event")
        _eve(f"What kind of menu or cuisine would you like for your {evt}? 🍽️\n\n"
             "  Describe a style (e.g. 'Traditional Malay buffet with live satay'),\n"
             "  name dishes, or type 'suggest' for ideas — I can also search online!")
        _hint()

    # Keywords that indicate the customer is confirming/selecting a menu
    _MENU_CONFIRM_KWS = (
        "yes", "yep", "yeah", "ok", "okay", "alright", "sure", "perfect", "great",
        "confirmed", "confirm", "finaliz", "use all", "take all", "all of them",
        "all those", "all the", "go with", "i'll take", "i want all", "use the",
        "i'll go", "go ahead", "proceed", "those dishes", "that menu", "sounds good",
        "looks good", "i like", "i love", "let's go", "book it", "done",
    )
    # Keywords that indicate a follow-up question (stay in menu state)
    _MENU_QUESTION_KWS = (
        "what", "how", "why", "tell me", "explain", "describe", "show me",
        "can you", "could you", "more about", "ingredient", "cooking style",
        "how is", "how do", "what is", "what are", "details", "info",
    )

    def _h_menu(self, raw: str) -> None:
        low = raw.lower().strip()
        if low == "back":
            self._back(); return

        evt     = self.s.get("event_type_label", "event")
        country = self.s.get("country_label", "Southeast Asia")

        # Classify intent: confirming, questioning, or new preference
        is_confirm   = any(k in low for k in self._MENU_CONFIRM_KWS)
        is_question  = any(k in low for k in self._MENU_QUESTION_KWS) or "?" in raw
        opts_shown   = self.s.get("_menu_opts_llm") or "_menu_opts" in self.s

        _online_kws  = ("online", "search", "look up", "find", "web", "internet",
                        "google", "current", "trend", "popular", "latest")
        wants_online  = any(k in low for k in _online_kws)
        wants_suggest = any(k in low for k in ("suggest", "idea", "recommend",
                                               "help", "surprise", "not sure",
                                               "don't know", "what should", "any idea"))

        # ── If Ollama is live, let it drive the full menu conversation ──
        if self.provider:
            if wants_online or wants_suggest:
                # Search / suggest flow
                hint = (
                    f"The customer is planning a {evt} in {country} and wants menu suggestions. "
                    f"You may use [SEARCH: catering menu ideas for {evt} in {country}] to fetch "
                    "real-world inspiration, then present 3–5 concrete, named options. "
                    "End by asking the customer to confirm their choice."
                )
                reply = self._eve_llm_stream(hint, raw, allow_tools=True)
                if reply:
                    self.s["_menu_opts_llm"] = True
                return

            if opts_shown and is_question:
                # Customer asked a follow-up about already-shown options — answer and stay
                hint = (
                    f"The customer is asking a follow-up question about the catering menu "
                    f"options you previously suggested for their {evt} in {country}. "
                    "Answer their question helpfully then remind them they can confirm "
                    "whenever ready."
                )
                self._eve_llm_stream(hint, raw, allow_tools=False)
                return  # stay in ST_MENU

            if opts_shown and is_confirm:
                # Customer is accepting the previously shown options
                # Ask LLM to summarise what they selected as a clean label
                summary_hint = (
                    f"The customer is confirming the menu options you previously suggested "
                    f"for their {evt} in {country}. Their message: \"{raw}\". "
                    "Acknowledge warmly that you've noted their full menu selection."
                )
                reply = self._eve_llm_stream(summary_hint, raw, allow_tools=False)
                # Store a clean summary; fall back to their raw words
                self.s["menu_preferences"] = (
                    f"All suggested options for {evt} ({country})"
                    if not raw.strip() else raw
                )
                self.s.pop("_menu_opts_llm", None)
                self.s.pop("_menu_opts", None)
                if not reply:
                    _eve("✅ Menu confirmed — noted! Let's pick a date.")
                self.state = ST_DATE
                self._ask_date()
                return

            # Free-text preference (no options shown yet, or unambiguous description)
            if not is_question:
                hint = (
                    f"The customer described their menu preference for a {evt} in {country}: "
                    f"\"{raw}\". Acknowledge it warmly in 1–2 sentences."
                )
                reply = self._eve_llm_stream(hint, raw, allow_tools=False)
                self.s["menu_preferences"] = raw
                self.s.pop("_menu_opts_llm", None)
                self.s.pop("_menu_opts", None)
                if not reply:
                    _eve(f"Noted — '{raw}'. Sounds delicious! 😋")
                self.state = ST_DATE
                self._ask_date()
                return

            # Follow-up question with no prior options shown — answer and stay
            hint = (
                f"The customer asked a question about menus for a {evt} in {country}. "
                "Answer helpfully, then invite them to describe their preference."
            )
            self._eve_llm_stream(hint, raw, allow_tools=False)
            return

        # ── Offline fallback ──
        # Numbered pick from a previously shown list
        if raw.strip().isdigit() and "_menu_opts" in self.s:
            idx = int(raw.strip()) - 1
            opts = self.s.pop("_menu_opts")
            if 0 <= idx < len(opts):
                self.s["menu_preferences"] = opts[idx]
                _eve(f"Excellent choice! 🍽️  '{opts[idx]}'")
                self.state = ST_DATE
                self._ask_date()
            else:
                _eve(f"Please enter 1–{len(opts)}, or describe your own menu preference.")
            return

        # After LLM showed online options, any text becomes the menu preference
        if self.s.pop("_menu_opts_llm", False) and raw.strip().isdigit() is False:
            self.s["menu_preferences"] = raw
            _eve(f"Noted — '{raw}'. Sounds delicious! 😋")
            self.state = ST_DATE
            self._ask_date()
            return

        # Suggest from local library
        if any(k in low for k in ("suggest", "idea", "recommend", "help", "surprise",
                                   "not sure", "don't know")):
            self._show_menu_suggestions()
            return

        # Accept free-text description
        self.s["menu_preferences"] = raw
        _eve(f"Noted — '{raw}'. Sounds delicious! 😋")
        self.s.pop("_menu_opts", None)
        self.state = ST_DATE
        self._ask_date()

    def _show_menu_suggestions(self) -> None:
        eid     = self.s.get("event_type", "default")
        country = self.s.get("country_label", "")
        opts = _MENU_SUGGESTIONS.get(eid, [
            "Classic 8-Dish Buffet — rice, protein mains, vegetables, noodles, and dessert",
            "Live Station Experience — 2 live cooking stations + buffet spread",
            "Fusion Spread — blend of 2 SEA cuisines tailored to your guest profile",
        ])
        _eve(f"Here are menu ideas for your event in {country}:\n")
        for i, opt in enumerate(opts, 1):
            print(f"    {i}. {opt}")
        print()
        print("  Type a number to choose, or describe your own preference!\n")
        self.s["_menu_opts"] = opts

    # ── 4. Date ──

    def _ask_date(self) -> None:
        _eve("What date would you like for your event? 🗓️\n\n"
             "  We have availability in May and June 2026.\n"
             "  Examples: 'May 15', '15 June', '2026-06-20'\n"
             "  Type 'show May' or 'show June' to see all available dates.")
        _hint()

    def _h_date(self, raw: str) -> None:
        low = raw.lower().strip()
        if low == "back":
            self._back(); return

        # Show available dates
        if any(k in low for k in ("show", "available", "list", "what date", "which date", "open")):
            if "june" in low or "jun" in low:
                self._print_avail(6)
            elif "may" in low:
                self._print_avail(5)
            else:
                self._print_avail(5)
                self._print_avail(6)
            return

        parsed = _parse_date(raw)
        if not parsed:
            _eve("I couldn't read that date. 😊\n"
                 "  Try formats like 'May 15', '15 June 2026', or '2026-06-20'.")
            return
        if parsed.year != _AVAIL_YEAR or parsed.month not in _AVAIL_MONTHS:
            _eve("We currently only take bookings for May and June 2026. 😊\n"
                 "  Type 'show May' or 'show June' to see available dates.")
            return
        if not _date_ok(parsed):
            _eve(f"Sorry — {parsed.strftime('%d %B %Y')} is already fully booked. 😔\n"
                 "  Here are the nearest available dates:")
            for delta in [-3, -2, -1, 1, 2, 3, 4, 5]:
                c = parsed + timedelta(days=delta)
                if _date_ok(c):
                    print(f"    • {c.strftime('%A, %d %B %Y')}")
            print()
            print("  Type a date from the list above to continue.\n")
            return

        self.s["event_date"] = parsed.isoformat()
        _eve(f"✅ {parsed.strftime('%A, %d %B %Y')} is available! 🎉")
        self.state = ST_TIME
        self._ask_time()

    def _print_avail(self, month: int) -> None:
        name = _AVAIL_MONTHS[month]
        dates = _available_in_month(month)
        _eve(f"Available dates in {name} 2026:\n")
        row: List[str] = []
        for d in dates:
            row.append(d.strftime("%d %a"))
            if len(row) == 7:
                print("    " + "   |   ".join(row))
                row = []
        if row:
            print("    " + "   |   ".join(row))
        print()

    # ── 5. Time ──

    def _ask_time(self) -> None:
        _eve("What time should the event start? ⏰\n\n"
             "  Common times:\n"
             "    Morning   : 9:00 AM     Lunch : 12:00 PM\n"
             "    Afternoon : 3:00 PM    Dinner : 7:00 PM    Night : 8:00 PM\n\n"
             "  (Type in any format — e.g. '7pm', '7:00 PM', '19:00')")
        _hint()

    def _h_time(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        parsed = _parse_time(raw)
        if not parsed:
            _eve("I couldn't read that time. Try '7pm', '7:00 PM', or '19:00'.")
            return
        display = _fmt_time(parsed)
        self.s["event_time"] = display
        hint = f"The customer's event start time is {display}. Confirm it briefly."
        if not self._eve_llm_stream(hint, raw):
            _eve(f"✅ {display} — perfect!")
            self._record(raw, f"{display} — perfect!")
        self.state = ST_GUESTS
        self._ask_guests()

    # ── 6. Guests ──

    def _ask_guests(self) -> None:
        _eve("How many guests are you expecting? 👥\n"
             "  (An estimate is fine — we'll confirm closer to the date.)")
        _hint()

    def _h_guests(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        nums = re.findall(r"\d+", raw.replace(",", ""))
        if not nums:
            _eve("Please enter a number — e.g. '200' or 'around 150'."); return
        g = int(nums[0])
        if g < 10:
            _eve("Our minimum event size is 10 guests."); return
        if g > 5000:
            _eve("For events over 5,000 guests, please use Option 5 to speak with our team directly.")
            return
        self.s["guest_count"] = g
        hint = f"The customer confirmed {g} guests for their event. Acknowledge briefly."
        if not self._eve_llm_stream(hint, raw):
            _eve(f"✅ {g} guests — got it!")
            self._record(raw, f"{g} guests — got it!")
        self.state = ST_DIETARY
        self._ask_dietary()

    # ── 7. Dietary ──

    def _ask_dietary(self) -> None:
        _eve("Any dietary requirements or restrictions? 🥗\n\n"
             "  Common: Halal | Vegetarian | Vegan | Gluten-free | Nut-free | Kosher\n"
             "  Type 'none' if there are no restrictions, or list multiple with commas.")
        _hint()

    def _h_dietary(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        low = raw.lower().strip()
        if low in ("none", "no", "n/a", "nope", "nil", "nothing", "no restrictions"):
            self.s["dietary_constraints"] = []
            summary = "no dietary restrictions"
        else:
            items = re.split(r"[,;&/]|\band\b|\bor\b|\bplus\b", raw, flags=re.IGNORECASE)
            cleaned = [d.strip() for d in items
                       if d.strip() and d.strip().lower() not in ("none", "n/a", "")]
            self.s["dietary_constraints"] = cleaned
            summary = " | ".join(cleaned)
        hint = (f"The customer stated their dietary requirements: {summary}. "
                "Confirm warmly and briefly.")
        if not self._eve_llm_stream(hint, raw):
            msg = f"✅ {summary.capitalize()} — noted!"
            _eve(msg)
            self._record(raw, msg)
        self.state = ST_STYLE
        self._ask_style()

    # ── 8. Service style ──

    def _ask_style(self) -> None:
        _eve("What service style would you prefer? 🍽️\n")
        for i, (k, desc) in enumerate(SERVICE_STYLES.items(), 1):
            print(f"    {i}.  {desc}")
        print()
        _hint()

    def _h_style(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        low = raw.lower().strip()
        keys = list(SERVICE_STYLES.keys())
        if raw.strip().isdigit():
            idx = int(raw.strip()) - 1
            if 0 <= idx < len(keys):
                self._set_style(keys[idx], raw); return
            _eve(f"Please choose 1–{len(keys)}."); return
        for k in keys:
            if k.replace("_", " ") in low or k in low:
                self._set_style(k, raw); return
        kw = {"buffet": "buffet", "self service": "buffet", "plated": "plated",
              "sit down": "plated", "sit-down": "plated", "table service": "plated",
              "cocktail": "cocktail", "standing": "cocktail", "canape": "cocktail",
              "semi": "semi_buffet"}
        for trigger, k in kw.items():
            if trigger in low:
                self._set_style(k, raw); return
        # LLM fallback
        if self.provider:
            style_labels = [desc.split("—")[0].strip() for desc in SERVICE_STYLES.values()]
            matched = self._llm_classify("What service style would you prefer?", raw, style_labels)
            if matched:
                k = next((sk for sk, desc in SERVICE_STYLES.items()
                          if desc.split("—")[0].strip() == matched), None)
                if k:
                    self._set_style(k, raw); return
        _eve("Please choose 1–4 or type 'buffet', 'plated', 'cocktail', or 'semi-buffet'.")

    def _set_style(self, key: str, user_said: str = "") -> None:
        label = SERVICE_STYLES[key].split("—")[0].strip()
        self.s.update(service_style=key, service_style_label=label)
        hint = (f"The customer chose \"{label}\" as their service style. "
                "Confirm their choice warmly in 1 sentence.")
        if not self._eve_llm_stream(hint, user_said or label):
            msg = f"✅ {label} — excellent choice!"
            _eve(msg)
            self._record(user_said or label, msg)
        self.state = ST_BUDGET
        self._ask_budget()

    # ── 9. Budget ──

    def _ask_budget(self) -> None:
        ccy = self.s.get("currency", "MYR")
        cat = self.s.get("event_category", "default")
        sty = self.s.get("service_style", "buffet")
        g = self.s.get("guest_count", 100)
        ph, total = _estimate(cat, sty, g, ccy)
        self.s["_ph_estimate"] = ph
        _eve(f"What is your budget per head? 💰\n\n"
             f"  Currency : {ccy}\n"
             f"  Market range for your event:\n"
             f"    Budget   : {ccy} {ph * 0.8:,.0f}/pax  (~{ccy} {ph * 0.8 * g:,.0f} total)\n"
             f"    Standard : {ccy} {ph:,.0f}/pax  (~{ccy} {total:,.0f} total)\n"
             f"    Premium  : {ccy} {ph * 1.4:,.0f}/pax  (~{ccy} {ph * 1.4 * g:,.0f} total)\n\n"
             f"  Type a per-head number — e.g. '{ccy} {ph:,.0f}' or just '{ph:,.0f}'")
        _hint()

    def _h_budget(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return

        ccy = self.s.get("currency", "MYR")
        g   = self.s.get("guest_count", 0)
        cat = self.s.get("event_category", "default")
        sty = self.s.get("service_style", "buffet")
        ph_estimate, _ = _estimate(cat, sty, g, ccy)
        premium = round(ph_estimate * 1.4)

        nums = re.findall(r"[\d,]+(?:\.\d+)?", raw.replace(",", ""))

        if not nums:
            # No number found — let LLM interpret flexible/open-ended responses
            _flexible_kws = ("flexible", "don't care", "dont care", "best", "whatever",
                             "up to you", "your choice", "recommend", "any", "open",
                             "doesn't matter", "doesnt matter", "no preference",
                             "surprise me", "go ahead", "finest", "premium", "top")
            if self.provider and any(k in raw.lower() for k in _flexible_kws):
                # Customer deferred to us — use the premium tier automatically
                amt = float(premium)
                hint = (
                    f"The customer said they are flexible on budget and want your best service. "
                    f"You have automatically selected the premium tier at {ccy} {amt:,.0f}/pax "
                    f"(estimated total: {ccy} {amt * g:,.0f} for {g} guests). "
                    "Confirm this warmly, tell them they'll get the full premium experience, "
                    "and let them know they can adjust later if needed."
                )
                reply = self._eve_llm_stream(hint, raw)
                if not reply:
                    _eve(f"✅ Premium package selected — {ccy} {amt:,.0f}/pax "
                         f"(~{ccy} {amt * g:,.0f} total). The very best for your event! 🌟")
                self.s["budget_per_head"] = amt
                self.state = ST_NAME
                self._ask_name()
            else:
                hint = (
                    f"The customer's response about budget was unclear: \"{raw}\". "
                    f"Kindly ask them to give a number per person in {ccy}. "
                    f"Remind them the range is {ccy} {round(ph_estimate * 0.8):,}–"
                    f"{ccy} {premium:,}/pax."
                )
                reply = self._eve_llm_stream(hint, raw)
                if not reply:
                    _eve(f"Please enter a budget per head — e.g. '{ccy} {round(ph_estimate):,}'.")
            return

        amt = float(nums[0])
        if amt <= 0:
            _eve("Please enter a valid amount."); return
        self.s["budget_per_head"] = amt
        hint = (
            f"The customer set their budget at {ccy} {amt:,.2f}/pax "
            f"(estimated total {ccy} {amt * g:,.2f} for {g} guests). "
            "Confirm it warmly in one sentence."
        )
        reply = self._eve_llm_stream(hint, raw)
        if not reply:
            _eve(f"✅ {ccy} {amt:,.2f}/pax — estimated total: {ccy} {amt * g:,.2f}")
        self.state = ST_NAME
        self._ask_name()

    # ── 10. Name ──

    def _ask_name(self) -> None:
        _eve("What is your full name? 😊")
        _hint()

    def _h_name(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        if len(raw.strip()) < 2:
            _eve("Please enter your full name."); return
        self.s["customer_name"] = raw.strip()
        first = raw.strip().split()[0]
        _eve(f"Nice to meet you, {first}! 👋")
        self.state = ST_PHONE
        self._ask_phone()

    # ── 11. Phone ──

    def _ask_phone(self) -> None:
        _eve("What is your WhatsApp number? 📱\n\n"
             "  Our staff will contact you on this number to confirm your booking.\n"
             "  (e.g. +60123456789 or 0123456789)")
        _hint()

    def _h_phone(self, raw: str) -> None:
        if raw.lower().strip() == "back":
            self._back(); return
        digits = re.sub(r"[^\d+]", "", raw)
        if len(digits) < 8:
            _eve("Please enter a valid phone number (at least 8 digits)."); return
        phone = digits if digits.startswith("+") else f"+{digits}"
        self.s["phone"] = phone
        _eve(f"✅ WhatsApp: {phone}")
        self.state = ST_CONFIRM
        self._ask_confirm()

    # ── 12. Confirm ──

    def _ask_confirm(self) -> None:
        s = self.s
        ccy = s.get("currency", "MYR")
        g = s.get("guest_count", 0)
        ph = s.get("budget_per_head", 0)
        total = ph * g
        try:
            d_fmt = datetime.strptime(s.get("event_date", ""), "%Y-%m-%d").strftime("%A, %d %B %Y")
        except Exception:
            d_fmt = s.get("event_date", "")
        dietary = s.get("dietary_constraints", [])

        print()
        print("  ╔══════════════════════════════════════════════════════════╗")
        print("  ║                  BOOKING SUMMARY 📋                     ║")
        print("  ╚══════════════════════════════════════════════════════════╝")
        _div("Your Details")
        print(f"     1.  Country        : {s.get('country_label', '')}")
        print(f"     2.  Event Type     : {s.get('event_type_label', '')}")
        print(f"     3.  Menu Style     : {s.get('menu_preferences', 'Not specified')}")
        print(f"     4.  Date           : {d_fmt}")
        print(f"     5.  Time           : {s.get('event_time', '')}")
        print(f"     6.  Guests         : {g} pax")
        print(f"     7.  Dietary        : {', '.join(dietary) if dietary else 'None'}")
        print(f"     8.  Service Style  : {s.get('service_style_label', '')}")
        print(f"     9.  Budget/Head    : {ccy} {ph:,.2f}")
        print(f"    10.  Full Name      : {s.get('customer_name', '')}")
        print(f"    11.  WhatsApp       : {s.get('phone', '')}")
        _div("Cost Estimate")
        print(f"     Estimated Total   : {ccy} {total:,.2f}")
        print(f"     (Staff will confirm final pricing via WhatsApp)")
        print()
        print("  " + "─" * 58)
        print("  Eve: To edit any detail, type its number (e.g. '4' to change date).")
        print("       Type 'confirm' to finalise your booking. 🎉")
        print("       Type 'back' to go to the previous step.")
        print()

    def _h_confirm(self, raw: str) -> None:
        low = raw.lower().strip()
        if low in ("confirm", "yes", "ok", "go ahead", "submit", "done", "book it", "proceed", "y"):
            self._finalize()
            return
        if low == "back":
            self._back(); return

        # Numeric edit
        if raw.strip().isdigit():
            n = int(raw.strip())
            edit = {1: ST_COUNTRY, 2: ST_EVENT, 3: ST_MENU, 4: ST_DATE, 5: ST_TIME,
                    6: ST_GUESTS, 7: ST_DIETARY, 8: ST_STYLE, 9: ST_BUDGET, 10: ST_NAME, 11: ST_PHONE}
            if n in edit:
                self.state = edit[n]
                _eve(f"Let's update: {_FIELD_LABELS.get(edit[n], '')} ✏️")
                self._reprompt(self.state)
            else:
                _eve("Please type a number 1–11 to edit a field, or 'confirm' to proceed.")
            return

        if any(k in low for k in ("change", "edit", "update", "modify")):
            _eve("Type the number of the field to edit (1–11), or 'confirm' to finalise.")
            return
        _eve("Type 'confirm' to finalise, a number 1–11 to edit a field, or 'back' for the previous step.")

    # ── Finalize booking ──────────────────────────────────────────────────

    def _finalize(self) -> None:
        s = self.s
        event_date = s.get("event_date", "2026-05-01")
        bid = _gen_bid(event_date)
        g = s.get("guest_count", 0)
        cat = s.get("event_category", "default")
        sty = s.get("service_style", "buffet")
        ccy = s.get("currency", "MYR")
        budget_ph = s.get("budget_per_head", 0.0)
        ph_est, _ = _estimate(cat, sty, g, ccy)
        final_ph = budget_ph if budget_ph > 0 else ph_est
        total = final_ph * g

        booking: Dict[str, Any] = {
            **{k: v for k, v in s.items() if not k.startswith("_")},
            "booking_id": bid,
            "estimated_per_head": final_ph,
            "estimated_total": total,
            "status": "confirmed_awaiting_payment",
            "created_at": datetime.now().isoformat(),
        }

        # Fire the agent pipeline in the background so the plan is logged server-side.
        # CustomerInteractionAgent treats "budget" as the TOTAL event budget.
        _call_agents({
            "event_type":          s.get("event_type", "custom"),
            "guest_count":         g,
            "dietary_constraints": s.get("dietary_constraints", []),
            "budget":              total,          # total = final_ph * g
            "budget_per_head":     final_ph,       # explicit per-head for downstream agents
            "currency":            ccy,
            "event_date":          event_date,
            "location":            s.get("country_label", ""),
            "service_style":       sty,
            "menu_preferences":    s.get("menu_preferences", ""),
        })

        _BOOKINGS[bid] = booking
        _show_receipt(booking)
        self._reset()
        self._return_to_menu()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n  Connecting to {BRAND} agent server at {BASE_URL}...")
    try:
        requests.get(f"{BASE_URL}/health", timeout=4).raise_for_status()
        print("  ✅ Agent server: Online")
    except Exception:
        print(
            f"\n  ⚠️  Agent server not reachable at {BASE_URL}.\n"
            "     Booking flow works normally, but AI-powered pricing may be unavailable.\n"
            "     To enable: run 'python -m app.main' in a separate terminal.\n"
        )

    prov = _build_provider()
    if prov:
        pname = os.getenv("MODEL_PROVIDER", "?")
        mname = os.getenv("MODEL_NAME", "?")
        print(f"  ✅ AI provider  : {pname} ({mname})")
    try:
        from app.platform.config import platform_status_banner

        print(f"  ℹ️  Platform     : {platform_status_banner()}")
    except Exception:
        pass
    print()

    EveChat().run()


if __name__ == "__main__":
    main()

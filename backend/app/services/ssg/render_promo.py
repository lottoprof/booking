"""
SSG renderer: generates promo sections in index.html from promotions table.

Usage:
    python -m backend.app.services.ssg.render_promo

Reads active promotions from SQLite, renders 2 SSG marker pairs in index.html:
  1. OFFERS_SCHEMA — JSON-LD Offer structured data
  2. PROMOS_SECTION — promo cards HTML
"""

import json
import os
import re
import sqlite3
from html import escape
from pathlib import Path

MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

DB_PATH = os.path.join("data", "sqlite", "booking.db")
FRONTEND_DIR = Path("frontend")
INDEX_HTML = FRONTEND_DIR / "index.html"
SITE_URL = "https://upgradelpg.site"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_active_promos(conn: sqlite3.Connection) -> list[dict]:
    """Fetch 0-3 active promotions, filtered by is_active + end_date."""
    rows = conn.execute("""
        SELECT * FROM promotions
        WHERE is_active = 1
          AND (end_date IS NULL OR end_date >= date('now'))
        ORDER BY sort_order
    """).fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Price / date formatting
# ──────────────────────────────────────────────────────────────────────────────

def format_price(value: int) -> str:
    """1990 -> '1 990 ₽', 23000 -> '23 000 ₽'."""
    return f"{value:,}".replace(",", "\u00a0") + "\u00a0₽"


def format_deadline(end_date: str | None) -> str:
    """Format end_date to human-readable deadline string."""
    if not end_date:
        return "Постоянное предложение"
    parts = end_date.split("-")
    day = int(parts[2])
    month = int(parts[1])
    return f"Действует до <strong>{day} {MONTHS_RU[month]}</strong>"


# ──────────────────────────────────────────────────────────────────────────────
# Point 1: Offers Schema (JSON-LD)
# ──────────────────────────────────────────────────────────────────────────────

def render_offers_schema(promos: list[dict]) -> str:
    """Render JSON-LD Offer structured data, or '' if 0 promos."""
    if not promos:
        return ""

    offers = []
    for p in promos:
        offer: dict[str, str] = {
            "@type": "Offer",
            "name": p["title"],
            "description": p["description"],
        }
        if p["price_new"] is not None:
            offer["price"] = str(p["price_new"])
            offer["priceCurrency"] = "RUB"
        if p["end_date"]:
            offer["validThrough"] = p["end_date"]
        if p["cta_url"]:
            offer["url"] = SITE_URL + p["cta_url"]
        offers.append(offer)

    schema = {
        "@context": "https://schema.org",
        "@type": "HealthAndBeautyBusiness",
        "name": "UPGRADE",
        "url": SITE_URL,
        "hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Акции",
            "itemListElement": offers,
        },
    }

    json_str = json.dumps(schema, ensure_ascii=False, indent=4)
    return (
        '  <script type="application/ld+json">\n'
        f"  {json_str}\n"
        "  </script>"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Point 2: Promos Section (HTML cards)
# ──────────────────────────────────────────────────────────────────────────────

def _render_promo_card(p: dict) -> str:
    """Render a single promo card <article>."""
    lines = [
        f'        <article class="promo-card">',
        f'          <div class="promo-badge {escape(p["badge_type"])}">{escape(p["badge_text"])}</div>',
        f'          <h3>{escape(p["title"])}</h3>',
        f'          <p class="promo-card-desc">{escape(p["description"])}</p>',
    ]

    # Price block
    if p["price_new"] is not None:
        lines.append('          <div class="promo-price">')
        lines.append(f'            <span class="promo-price-new">{format_price(p["price_new"])}</span>')
        if p["price_old"] is not None:
            lines.append(f'            <span class="promo-price-old">{format_price(p["price_old"])}</span>')
        lines.append('          </div>')

    # Deadline
    lines.append(f'          <div class="promo-deadline">{format_deadline(p["end_date"])}</div>')

    # CTA button
    if p["cta_text"] and p["cta_url"]:
        lines.append(f'          <a href="{escape(p["cta_url"])}" class="promo-cta">{escape(p["cta_text"])}</a>')

    lines.append('        </article>')
    return "\n".join(lines)


def render_promos_section(promos: list[dict]) -> str:
    """Render full <section class="promos"> or '' if 0 promos."""
    if not promos:
        return ""

    cards = "\n\n".join(_render_promo_card(p) for p in promos)

    return (
        '  <section class="promos" id="promos">\n'
        '    <div class="section-inner">\n'
        '      <div class="section-label reveal">Спецпредложения</div>\n'
        '      <h2 class="section-title reveal">Актуальные <em>акции</em></h2>\n'
        '\n'
        '      <div class="promos-grid stagger reveal">\n'
        '\n'
        f'{cards}\n'
        '\n'
        '      </div>\n'
        '      <div class="promo-dots" id="promoDots"></div>\n'
        '    </div>\n'
        '  </section>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Marker replacement
# ──────────────────────────────────────────────────────────────────────────────

def render_promos(html: str, promos: list[dict]) -> str:
    """Replace all 3 SSG marker pairs in html with rendered content."""

    markers = [
        ("SSG:OFFERS_SCHEMA_START", "SSG:OFFERS_SCHEMA_END", render_offers_schema(promos)),
        ("SSG:PROMOS_SECTION_START", "SSG:PROMOS_SECTION_END", render_promos_section(promos)),
    ]

    for start_marker, end_marker, content in markers:
        pattern = re.compile(
            rf"(<!-- {re.escape(start_marker)} -->).*?(<!-- {re.escape(end_marker)} -->)",
            re.DOTALL,
        )
        if content:
            replacement = f"\\1\n{content}\n  \\2"
        else:
            replacement = f"\\1\n  \\2"
        html = pattern.sub(replacement, html)

    return html


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def render_promo_all():
    """Main: DB -> read index.html -> render -> write back."""
    conn = get_db()
    promos = fetch_active_promos(conn)
    conn.close()

    print(f"render_promo: {len(promos)} active promo(s)")

    html = INDEX_HTML.read_text(encoding="utf-8")
    html = render_promos(html, promos)
    INDEX_HTML.write_text(html, encoding="utf-8")

    print("render_promo: index.html updated")


if __name__ == "__main__":
    render_promo_all()

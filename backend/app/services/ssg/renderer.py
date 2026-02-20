"""
SSG renderer: generates static HTML blog pages from DB articles.

Usage:
    python -m backend.app.services.ssg.renderer

Reads article.html and blog.html as templates, queries articles from SQLite,
renders static files into frontend/blog/.
"""

import math
import os
import re
import sqlite3
from datetime import datetime
from html import escape
from pathlib import Path

from PIL import Image

MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

DB_PATH = os.path.join("data", "sqlite", "booking.db")
FRONTEND_DIR = Path("frontend")
BLOG_DIR = FRONTEND_DIR / "blog"
BLOG_IMAGES_DIR = FRONTEND_DIR / "images" / "blog"
ARTICLE_TEMPLATE = FRONTEND_DIR / "article.html"
BLOG_TEMPLATE = FRONTEND_DIR / "blog.html"
FALLBACK_IMAGE = "/logo/logo.svg"
SITE_URL = "https://upgradelpg.site"
ARTICLES_PER_PAGE = 9
AUTHOR_NAME = "UPGRADE"
WEBP_QUALITY = 80
HERO_WIDTH = 1440
CARD_WIDTH = 640


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def format_date_human(iso_date: str) -> str:
    """Convert '2026-02-12' or '2026-02-12 14:30:00' to '12 февраля 2026'."""
    dt = datetime.strptime(iso_date[:10], "%Y-%m-%d")
    return f"{dt.day} {MONTHS_RU[dt.month]} {dt.year}"


def calc_read_time(html_body: str) -> str:
    """Estimate reading time from HTML body text."""
    text = re.sub(r"<[^>]+>", "", html_body)
    words = len(text.split())
    minutes = max(1, round(words / 200))
    return f"{minutes} мин"


def get_excerpt(html_body: str, max_len: int = 200) -> str:
    """Extract plain-text excerpt from HTML."""
    text = re.sub(r"<[^>]+>", "", html_body)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Image processing: JPG/PNG → WebP conversion
# ──────────────────────────────────────────────────────────────────────────────

def convert_images():
    """Convert all JPG/PNG in images/blog/ to WebP. Skip if .webp already exists."""
    if not BLOG_IMAGES_DIR.exists():
        return

    converted = 0
    for src in BLOG_IMAGES_DIR.iterdir():
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        webp_path = src.with_suffix(".webp")
        if webp_path.exists() and webp_path.stat().st_mtime >= src.stat().st_mtime:
            continue

        img = Image.open(src)
        # Hero size (card will use object-fit: cover)
        if img.width > HERO_WIDTH:
            ratio = HERO_WIDTH / img.width
            img = img.resize((HERO_WIDTH, int(img.height * ratio)), Image.Resampling.LANCZOS)
        img.save(webp_path, "WEBP", quality=WEBP_QUALITY)
        converted += 1
        print(f"  Converted: {src.name} → {webp_path.name} ({webp_path.stat().st_size // 1024} KB)")

    if converted:
        print(f"  {converted} image(s) converted to WebP")


def resolve_image_url(slug: str, db_image_url: str | None) -> str:
    """Resolve article image: check WebP exists, fallback to logo.svg."""
    webp_path = BLOG_IMAGES_DIR / f"{slug}.webp"
    if webp_path.exists():
        return f"/images/blog/{slug}.webp"
    if db_image_url:
        return db_image_url
    return FALLBACK_IMAGE


# ──────────────────────────────────────────────────────────────────────────────
# Article page rendering
# ──────────────────────────────────────────────────────────────────────────────

def render_article_page(article: dict, related: list[dict], template: str) -> str:
    """Render a single article page from template."""
    published_date = (article["published_at"] or article["created_at"])[:10]
    updated_date = (article["updated_at"] or published_date)[:10]
    read_time = calc_read_time(article["body_html"])

    # ── Direct {{placeholder}} replacement (head + body) ──
    replacements = {
        "{{title}}": escape(article["title"]),
        "{{slug}}": escape(article["slug"]),
        "{{description}}": escape(article["meta_description"] or ""),
        "{{category}}": escape(article["category_name"] or ""),
        "{{category_slug}}": escape(article["category_slug"] or ""),
        "{{published_date}}": published_date,
        "{{published_human}}": format_date_human(published_date),
        "{{updated_date}}": updated_date,
        "{{read_time}}": f"{read_time} чтения",
        "{{author_name}}": AUTHOR_NAME,
        "{{image_url}}": escape(article["image_url"] or ""),
        "{{content}}": article["body_html"],
    }

    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    # ── Hero image: replace commented-out block ──
    if article["image_url"]:
        hero_html = (
            f'<div class="article-hero">\n'
            f'        <img src="{escape(article["image_url"])}" alt="{escape(article["title"])}" />\n'
            f"      </div>"
        )
    else:
        hero_html = ""

    html = re.sub(
        r"<!--\s*\n\s*Hero image.*?-->",
        hero_html,
        html,
        flags=re.DOTALL,
    )

    # ── Related articles: replace <!-- {{related}} ... --> inside related-grid ──
    related_cards = _render_related_cards(related)
    html = re.sub(
        r"<!--\s*\{\{related\}\}[^>]*-->",
        related_cards,
        html,
    )

    return html


def _render_related_cards(related: list[dict]) -> str:
    """Render related article cards (without section wrapper)."""
    if not related:
        return ""

    cards = []
    for r in related[:3]:
        excerpt = get_excerpt(r["body_html"])
        cards.append(
            f'        <article class="related-card">\n'
            f'          <div class="related-card-cat">{escape(r["category_name"] or "")}</div>\n'
            f'          <h3 class="related-card-title"><a href="/blog/{escape(r["slug"])}.html">{escape(r["title"])}</a></h3>\n'
            f'          <p class="related-card-excerpt">{escape(excerpt)}</p>\n'
            f"        </article>"
        )

    return "\n\n".join(cards)


# ──────────────────────────────────────────────────────────────────────────────
# Blog index page rendering
# ──────────────────────────────────────────────────────────────────────────────

def render_blog_index(articles: list[dict], template: str, page: int = 1, total_pages: int = 1) -> str:
    """Render blog index page with article cards."""

    # Build article cards HTML
    cards = []
    for a in articles:
        published = (a["published_at"] or a["created_at"])[:10]
        read_time = calc_read_time(a["body_html"])
        excerpt = get_excerpt(a["body_html"])
        cat_slug = escape(a["category_slug"] or "")
        cat_name = escape(a["category_name"] or "")

        image_url = a["image_url"] or FALLBACK_IMAGE
        image_html = f'<img src="{escape(image_url)}" alt="{escape(a["title"])}" />'

        cards.append(
            f'        <article class="article-card" data-cat="{cat_slug}">\n'
            f'          <div class="article-card-image">\n'
            f"            {image_html}\n"
            f"          </div>\n"
            f'          <div class="article-card-body">\n'
            f'            <div class="article-card-meta">\n'
            f'              <span class="article-category">{cat_name}</span>\n'
            f"              <span>{format_date_human(published)}</span>\n"
            f"            </div>\n"
            f'            <h2 class="article-card-title">\n'
            f'              <a href="/blog/{escape(a["slug"])}.html">{escape(a["title"])}</a>\n'
            f"            </h2>\n"
            f'            <p class="article-card-excerpt">{escape(excerpt)}</p>\n'
            f'            <div class="article-card-footer">\n'
            f'              <span class="read-time">{read_time} чтения</span>\n'
            f'              <a href="/blog/{escape(a["slug"])}.html" class="read-more">Читать →</a>\n'
            f"            </div>\n"
            f"          </div>\n"
            f"        </article>"
        )

    cards_html = "\n\n".join(cards)

    # Build pagination
    pagination_html = _render_pagination(page, total_pages)

    # Replace <!-- {{articles}} ... --> comment with cards
    html = re.sub(
        r"<!--\s*\{\{articles\}\}[^>]*-->",
        cards_html,
        template,
    )

    # Replace <!-- {{pagination}} ... --> comment with pagination nav
    html = re.sub(
        r"<!--\s*\{\{pagination\}\}[^>]*-->",
        pagination_html,
        html,
    )

    return html


def _render_pagination(page: int, total_pages: int) -> str:
    """Render pagination nav."""
    if total_pages <= 1:
        return ""

    parts = []

    for p in range(1, total_pages + 1):
        if p == page:
            parts.append(f'<span class="current">{p}</span>')
        elif p == 1:
            parts.append(f'<a href="/blog/">1</a>')
        else:
            parts.append(f'<a href="/blog/page/{p}.html">{p}</a>')

    if page < total_pages:
        next_href = f"/blog/page/{page + 1}.html"
        parts.append(f'<a href="{next_href}" class="arrow" aria-label="Следующая страница">›</a>')

    return f'<nav class="pagination" aria-label="Страницы блога">\n        {"  ".join(parts)}\n      </nav>'


# ──────────────────────────────────────────────────────────────────────────────
# Sitemap generation
# ──────────────────────────────────────────────────────────────────────────────

def render_sitemap(articles: list[dict]) -> str:
    """Generate sitemap.xml."""
    urls = [
        f"  <url><loc>{SITE_URL}/</loc><priority>1.0</priority></url>",
        f"  <url><loc>{SITE_URL}/pricing.html</loc><priority>0.8</priority></url>",
        f"  <url><loc>{SITE_URL}/book.html</loc><priority>0.7</priority></url>",
        f"  <url><loc>{SITE_URL}/blog/</loc><priority>0.8</priority></url>",
    ]

    for a in articles:
        updated = (a["updated_at"] or a["created_at"])[:10]
        urls.append(
            f'  <url><loc>{SITE_URL}/blog/{a["slug"]}.html</loc>'
            f"<lastmod>{updated}</lastmod><priority>0.6</priority></url>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main render pipeline
# ──────────────────────────────────────────────────────────────────────────────

def render_all():
    """Main entry point: render all published articles and blog index."""
    # ── Convert images first ──
    convert_images()

    conn = get_db()

    # Fetch all published articles with category info
    articles = conn.execute("""
        SELECT
            a.id, a.slug, a.title, a.meta_description,
            a.body_html, a.image_url, a.sort_order,
            a.published_at, a.updated_at, a.created_at,
            c.slug AS category_slug, c.name AS category_name
        FROM articles a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.is_published = 1
        ORDER BY a.sort_order DESC, a.published_at DESC
    """).fetchall()

    articles = [dict(a) for a in articles]

    if not articles:
        print("No published articles found. Skipping render.")
        conn.close()
        return

    print(f"Found {len(articles)} published articles")

    # ── Resolve image URLs (WebP > DB > fallback) ──
    for article in articles:
        article["image_url"] = resolve_image_url(article["slug"], article["image_url"])

    # Load templates
    article_template = ARTICLE_TEMPLATE.read_text(encoding="utf-8")
    blog_template = BLOG_TEMPLATE.read_text(encoding="utf-8")

    # Ensure output directories exist
    BLOG_DIR.mkdir(parents=True, exist_ok=True)

    # ── Render individual article pages ──
    for article in articles:
        # Get related articles (same category, excluding self)
        related = [
            a for a in articles
            if a["category_slug"] == article["category_slug"] and a["id"] != article["id"]
        ][:3]
        if len(related) < 2:
            # Fill with other articles if not enough from same category
            other = [a for a in articles if a["id"] != article["id"] and a not in related]
            related.extend(other[:3 - len(related)])

        html = render_article_page(article, related, article_template)
        out_path = BLOG_DIR / f"{article['slug']}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"  Rendered: blog/{article['slug']}.html")

    # ── Render blog index pages (with pagination) ──
    total_pages = max(1, math.ceil(len(articles) / ARTICLES_PER_PAGE))

    for page in range(1, total_pages + 1):
        start = (page - 1) * ARTICLES_PER_PAGE
        page_articles = articles[start:start + ARTICLES_PER_PAGE]

        html = render_blog_index(page_articles, blog_template, page, total_pages)

        if page == 1:
            out_path = BLOG_DIR / "index.html"
        else:
            page_dir = BLOG_DIR / "page"
            page_dir.mkdir(parents=True, exist_ok=True)
            out_path = page_dir / f"{page}.html"

        out_path.write_text(html, encoding="utf-8")
        print(f"  Rendered: {out_path.relative_to(FRONTEND_DIR)}")

    # ── Render sitemap ──
    sitemap = render_sitemap(articles)
    sitemap_path = FRONTEND_DIR / "sitemap.xml"
    sitemap_path.write_text(sitemap, encoding="utf-8")
    print(f"  Rendered: sitemap.xml")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    render_all()

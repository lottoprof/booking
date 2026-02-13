"""URL-safe slug generation with Cyrillic transliteration."""

import re

_TRANSLIT = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "abvgdeejziyklmnoprstufhccss_y_eua",
)


def slugify(text: str) -> str:
    """Generate URL-safe slug from Russian/English text."""
    s = text.lower().translate(_TRANSLIT)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "service"

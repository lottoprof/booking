import re
from pathlib import Path
from typing import Dict, Set, List

MESSAGES: Dict[str, Dict[str, str]] = {}
AVAILABLE_LANGS: Set[str] = set()

DEFAULT_LANG = "ru"

LINE_RE = re.compile(r'^(\w+):([^|]+)\|\s*"(.*)"$')


def load_messages(path: str | Path):
    global MESSAGES, AVAILABLE_LANGS

    MESSAGES.clear()
    AVAILABLE_LANGS.clear()

    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"messages file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        m = LINE_RE.match(line)
        if not m:
            continue

        lang, key, text = m.groups()
        text = text.replace("\\n", "\n").strip()

        MESSAGES.setdefault(lang, {})[key.strip()] = text
        AVAILABLE_LANGS.add(lang)


def t(key: str, lang: str | None = None, *args) -> str:
    if not lang:
        lang = DEFAULT_LANG

    text = (
        MESSAGES.get(lang, {}).get(key)
        or MESSAGES.get(DEFAULT_LANG, {}).get(key)
        or key
    )

    if args:
        try:
            return text % args
        except Exception:
            return text

    return text


def t_all(key: str) -> List[str]:
    """
    Возвращает список всех переводов ключа для всех доступных языков.
    
    Использование в фильтрах:
        @router.message(F.text.in_(t_all("admin:rooms:back")))
    
    включает все языки 
    """
    translations = []
    for lang in AVAILABLE_LANGS:
        text = MESSAGES.get(lang, {}).get(key)
        if text and text not in translations:
            translations.append(text)
    return translations


def get_available_langs() -> list[str]:
    return sorted(AVAILABLE_LANGS)

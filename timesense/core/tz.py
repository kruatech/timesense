"""Часовые пояса: пояс пользователя и явные маркеры пояса в тексте.

Только stdlib (zoneinfo, Python 3.9+). На системах без базы IANA (Windows,
некоторые slim-образы) нужен пакет tzdata: pip install "timesense[tz]".
Для поясов без перехода на летнее время (МСК и др.) есть фиксированный
fallback, чтобы «в 10 мск» работало и без tzdata.

Контракт:
  - parse(..., tz=None) и naive now → как раньше: naive datetime на выходе,
    фразы с маркером пояса («в 10 мск», «at 10 EST») → None.
  - tz задан или now aware → aware datetime в поясе пользователя; маркер
    пояса в тексте учитывается и время переводится в пояс пользователя.
"""

from __future__ import annotations

import re
from datetime import timedelta, timezone, tzinfo
from typing import Optional, Tuple, Union

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # stdlib, Python 3.9+

TzLike = Union[str, tzinfo, None]

# ключ IANA → смещение (часы) для fallback, только для поясов без летнего времени
_NO_DST_FALLBACK = {
    "UTC": 0,
    "Europe/Moscow": 3,
    "Europe/Minsk": 3,
    "Europe/Kaliningrad": 2,
    "Europe/Samara": 4,
    "Asia/Yekaterinburg": 5,
    "Asia/Omsk": 6,
    "Asia/Novosibirsk": 7,
    "Asia/Krasnoyarsk": 7,
    "Asia/Irkutsk": 8,
    "Asia/Vladivostok": 10,
    "Asia/Almaty": 5,
    "Asia/Tashkent": 5,
    "Asia/Tbilisi": 4,
    "Asia/Yerevan": 4,
    "Asia/Tokyo": 9,
}


def _zone(key: str) -> Optional[tzinfo]:
    if key == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        pass
    off = _NO_DST_FALLBACK.get(key)
    if off is not None:
        return timezone(timedelta(hours=off), key)
    return None


def resolve_tz(tz: TzLike) -> Optional[tzinfo]:
    """'Europe/Moscow' | tzinfo | None → tzinfo | None. Неизвестный ключ → ValueError."""
    if tz is None:
        return None
    if isinstance(tz, tzinfo):
        return tz
    if isinstance(tz, str):
        z = _zone(tz.strip())
        if z is None:
            raise ValueError(
                "Unknown time zone %r (IANA name expected, e.g. 'Europe/Moscow'; "
                "on systems without tz database: pip install tzdata)" % (tz,)
            )
        return z
    raise TypeError("tz must be str, tzinfo or None, got %r" % (type(tz).__name__,))


# ── маркеры пояса в тексте ────────────────────────────────────────────────
_ABBR = {
    "мск": "Europe/Moscow",
    "msk": "Europe/Moscow",
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "eet": "Europe/Helsinki",
    "eest": "Europe/Helsinki",
    "bst": "Europe/London",
    "jst": "Asia/Tokyo",
    "aest": "Australia/Sydney",
}

# «по Москве», «по киевскому времени» — форма после «по»
_RU_CITY = {
    "москве": "Europe/Moscow",
    "московскому": "Europe/Moscow",
    "киеву": "Europe/Kyiv",
    "киевскому": "Europe/Kyiv",
    "минску": "Europe/Minsk",
    "минскому": "Europe/Minsk",
    "алматы": "Asia/Almaty",
    "лондону": "Europe/London",
    "лондонскому": "Europe/London",
    "берлину": "Europe/Berlin",
    "калининграду": "Europe/Kaliningrad",
    "калининградскому": "Europe/Kaliningrad",
    "самаре": "Europe/Samara",
    "самарскому": "Europe/Samara",
    "екатеринбургу": "Asia/Yekaterinburg",
    "екатеринбургскому": "Asia/Yekaterinburg",
    "омску": "Asia/Omsk",
    "омскому": "Asia/Omsk",
    "новосибирску": "Asia/Novosibirsk",
    "новосибирскому": "Asia/Novosibirsk",
    "красноярску": "Asia/Krasnoyarsk",
    "красноярскому": "Asia/Krasnoyarsk",
    "иркутску": "Asia/Irkutsk",
    "иркутскому": "Asia/Irkutsk",
    "владивостоку": "Asia/Vladivostok",
    "владивостокскому": "Asia/Vladivostok",
    "ташкенту": "Asia/Tashkent",
    "ташкентскому": "Asia/Tashkent",
    "тбилиси": "Asia/Tbilisi",
    "еревану": "Asia/Yerevan",
    "ереванскому": "Asia/Yerevan",
}

# «moscow time», «new york time»
_EN_CITY = {
    "moscow": "Europe/Moscow",
    "london": "Europe/London",
    "new york": "America/New_York",
    "tokyo": "Asia/Tokyo",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "beijing": "Asia/Shanghai",
    "sydney": "Australia/Sydney",
    "dubai": "Asia/Dubai",
    "kyiv": "Europe/Kyiv",
    "kiev": "Europe/Kyiv",
}

_OFFSET_RE = re.compile(
    r"(?<![\w])(utc|gmt|мск|msk)\s*([+\-\u2212])\s*(\d{1,2})(?::?(\d{2}))?(?![\w])",
    re.IGNORECASE,
)
_ABBR_RE = re.compile(
    r"(?<![\w])(?:по\s+)?(" + "|".join(sorted(_ABBR, key=len, reverse=True)) + r")(?![\w])",
    re.IGNORECASE,
)
_RU_CITY_RE = re.compile(
    r"(?<![\w])по\s+(" + "|".join(sorted(_RU_CITY, key=len, reverse=True)) + r")(?:\s+времени)?(?![\w])",
    re.IGNORECASE,
)
_EN_CITY_RE = re.compile(
    r"(?<![\w])(" + "|".join(k.replace(" ", r"\s+") for k in _EN_CITY) + r")\s+time(?![\w])",
    re.IGNORECASE,
)


def _blank(text: str, a: int, b: int) -> str:
    """Заменяет фрагмент пробелами той же длины — позиции токенов не сдвигаются."""
    return text[:a] + " " * (b - a) + text[b:]


def find_tz_marker(text: str) -> Optional[Tuple[tzinfo, str]]:
    """Ищет явный пояс в тексте. → (tzinfo, текст без маркера) | None.

    None также если маркер найден, но пояс недоступен (нет tzdata и нет fallback).
    """
    m = _OFFSET_RE.search(text)
    if m:
        base = m.group(1).lower()
        sign = -1 if m.group(2) in ("-", "\u2212") else 1
        hours = int(m.group(3))
        minutes = int(m.group(4) or 0)
        if hours > 14 or minutes > 59:
            return None
        off = timedelta(hours=hours, minutes=minutes) * sign
        if base in ("мск", "msk"):
            off += timedelta(hours=3)
        return timezone(off), _blank(text, m.start(), m.end())
    for rx, table in ((_RU_CITY_RE, _RU_CITY), (_ABBR_RE, _ABBR)):
        m = rx.search(text)
        if m:
            z = _zone(table[m.group(1).lower()])
            return (z, _blank(text, m.start(), m.end())) if z is not None else None
    m = _EN_CITY_RE.search(text)
    if m:
        key = re.sub(r"\s+", " ", m.group(1).lower())
        z = _zone(_EN_CITY[key])
        return (z, _blank(text, m.start(), m.end())) if z is not None else None
    return None

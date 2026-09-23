"""Праздники по названию (RU и EN).

«на новый год поздравить», «до нового года», «на майские», «в Пасху»,
«christmas party at 7pm», «by thanksgiving», «every christmas».

Название заменяется явной датой ближайшего (не прошедшего) праздника на языке
фразы — дальше работает обычный парсер: время, дедлайн, повтор, диапазон.
Праздники из WorkingCalendar(holiday_names=...) имеют приоритет над встроенными.
Повтор («каждый новый год», «every christmas») — дата без года (ежегодно).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

_RU_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
                  "августа", "сентября", "октября", "ноября", "декабря"]
_EN_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"]

Span = Tuple[date, Optional[date]]  # (начало, конец периода или None)


# ── вычисляемые даты ──────────────────────────────────────────────────────
def easter_western(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def easter_orthodox(y: int) -> date:
    a, b, c = y % 4, y % 7, y % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return date(y, month, day) + timedelta(days=13)  # юлианский → григорианский (1900–2099)


def thanksgiving_us(y: int) -> date:
    first = date(y, 11, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 21)


def _fixed(m: int, d: int) -> Callable[[int], Span]:
    return lambda y: (date(y, m, d), None)


def _period(m1: int, d1: int, m2: int, d2: int) -> Callable[[int], Span]:
    return lambda y: (date(y, m1, d1), date(y, m2, d2))


# (регэксп, вычисление по году). Длинные/частные названия — раньше общих.
_RU: List[Tuple[str, Callable[[int], Span]]] = [
    (r"стар\w+\s+нов\w+\s+(?:год|года|году|годом|годе)", _fixed(1, 14)),
    (r"канун\w*\s+нов\w+\s+(?:год|года|году|годом|годе)|новогодн\w+\s+ноч\w*", _fixed(12, 31)),
    (r"новогодн\w+\s+(?:каникул\w*|праздник\w*)", _period(1, 1, 1, 8)),
    (r"нов\w+\s+(?:год|года|году|годом|годе)", _fixed(1, 1)),
    (r"рождеств\w*", _fixed(1, 7)),
    (r"(?:день|дня|дню|днём|днем)\s+защитника\s+отечества", _fixed(2, 23)),
    (r"(?:день|дня|дню|днём|днем)\s+святого\s+валентина|валентинов\w*\s+дн\w+", _fixed(2, 14)),
    (r"(?:международн\w+\s+)?женск\w+\s+(?:день|дня|дню|днём|днем)", _fixed(3, 8)),
    (r"майск\w+(?:\s+праздник\w*)?", _period(5, 1, 5, 10)),
    (r"первома\w+", _fixed(5, 1)),
    (r"(?:день|дня|дню|днём|днем)\s+победы", _fixed(5, 9)),
    (r"(?:день|дня|дню|днём|днем)\s+россии", _fixed(6, 12)),
    (r"(?:день|дня|дню|днём|днем)\s+знаний", _fixed(9, 1)),
    (r"(?:день|дня|дню|днём|днем)\s+народного\s+единства", _fixed(11, 4)),
    (r"хэллоуин\w*|хеллоуин\w*", _fixed(10, 31)),
    (r"пасх\w*", lambda y: (easter_orthodox(y), None)),
]

_EN: List[Tuple[str, Callable[[int], Span]]] = [
    (r"new\s+year'?s\s+eve|nye", _fixed(12, 31)),
    (r"christmas\s+eve|xmas\s+eve", _fixed(12, 24)),
    (r"new\s+year'?s?(?:\s+day)?", _fixed(1, 1)),
    (r"christmas(?:\s+day)?|xmas", _fixed(12, 25)),
    (r"boxing\s+day", _fixed(12, 26)),
    (r"valentine'?s?\s+day|valentines", _fixed(2, 14)),
    (r"st\.?\s+patrick'?s\s+day|saint\s+patrick'?s\s+day", _fixed(3, 17)),
    (r"halloween", _fixed(10, 31)),
    (r"independence\s+day|(?:the\s+)?(?:4th|fourth)\s+of\s+july", _fixed(7, 4)),
    (r"thanksgiving(?:\s+day)?", lambda y: (thanksgiving_us(y), None)),
    (r"easter(?:\s+sunday)?", lambda y: (easter_western(y), None)),
]

_RECUR_RU = r"(?:кажд\w+|ежегодно)\s+(?:на\s+|в\s+)?$"
_RECUR_EN = r"(?:every|each)\s+(?:year\s+on\s+)?$"


def _nearest(calc: Callable[[int], Span], today: date) -> Span:
    for y in (today.year, today.year + 1):
        try:
            s, e = calc(y)
        except ValueError:
            continue
        if (e or s) >= today:
            return s, e
    return calc(today.year + 1)


def _fmt(lang: str, s: date, e: Optional[date], with_year: bool) -> str:
    if lang == "en":
        one = lambda d: "%s %d%s" % (_EN_MONTHS[d.month - 1], d.day, (" %d" % d.year) if with_year else "")
        if e is None or e == s:
            return one(s)
        return "from %s to %s" % (one(s), one(e))
    one = lambda d: "%d %s%s" % (d.day, _RU_MONTHS_GEN[d.month - 1], (" %d" % d.year) if with_year else "")
    if e is None or e == s:
        return one(s)
    if s.month == e.month and s.year == e.year:
        return "с %d по %s" % (s.day, one(e))
    return "с %s по %s" % (one(s), one(e))


_COMPILED: Dict[str, List[Tuple["re.Pattern[str]", Callable[[int], Span]]]] = {}
# быстрый фильтр: без этих корней встроенные праздники искать бессмысленно
_QUICK = {
    "ru": re.compile(r"нов|рожд|защитник|валентин|женск|майск|первома|побед|росси|знани|единств|"
                     r"хэллоуин|хеллоуин|пасх"),
    "en": re.compile(r"year|christmas|xmas|boxing|valentine|patrick|halloween|independence|july|"
                     r"thanksgiving|easter|nye"),
}


def _table(lang):
    key = "en" if lang == "en" else "ru"
    if key not in _COMPILED:
        src = _EN if key == "en" else _RU
        _COMPILED[key] = [
            (re.compile(r"(?<![\w'])(?:" + rx + r")(?![\w])"), calc) for rx, calc in src
        ]
    return _COMPILED[key]


def apply_holidays(text: str, today: date, lang: str, calendar=None) -> str:
    """Заменяет первое найденное название праздника явной датой. Иначе — text без изменений."""
    if not text:
        return text
    low = text.lower()
    names = getattr(calendar, "holiday_names", None) or {}
    if not names and not _QUICK["en" if lang == "en" else "ru"].search(low):
        return text
    found: Optional[Tuple[int, int, date, Optional[date]]] = None  # (start, end, s, e)

    # 1) праздники пользователя из WorkingCalendar — приоритетнее встроенных
    for name in sorted(names, key=len, reverse=True):
        m = re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", low)
        if not m:
            continue
        dates = sorted(d for d in names[name] if d >= today) or sorted(names[name])
        if dates:
            found = (m.start(), m.end(), dates[0], None)
            break

    # 2) встроенные
    if found is None:
        best: Optional[Tuple[int, int, date, Optional[date]]] = None
        for rx, calc in _table(lang):
            m = rx.search(low)
            if m and (best is None or m.start() < best[0]):
                s, e = _nearest(calc, today)
                best = (m.start(), m.end(), s, e)
        found = best

    if found is None:
        return text
    a, b, s, e = found
    moment_before = False
    # Новый год — момент наступления 1 января 00:00, поэтому «до/к/перед новым годом»
    # это конец 31 декабря, а не весь день 1 января. «На новый год» — сам праздник.
    if e is None and (s.month, s.day) == (1, 1):
        before = re.search(r"(?<![\w])(?:до|к|ко|перед|by|before)\s+$", low[:a])
        if before:
            s = s - timedelta(days=1)
            # «перед новым годом» / «before new year» — тот же дедлайн, что «до/by»
            moment_before = True
    # «в новом году переезд» — это «когда-то в следующем году», а не 1 января
    if lang != "en" and re.match(r"нов\w+\s+году\b", low[a:b]) and re.search(r"\bво?\s+$", low[:a]):
        return text[:a] + "%d году" % (today.year + 1) + text[b:]
    recurring = re.search(_RECUR_EN if lang == "en" else _RECUR_RU, low[:a]) is not None
    repl = _fmt(lang, s, e, with_year=not recurring)
    # предлог перед периодом («на майские» → «с 1 по 10 мая») не нужен
    prefix = text[:a]
    if moment_before:
        # «перед новым годом» / «before new year» — тот же дедлайн, что «до …» / «by …»
        prefix = re.sub(
            r"(?<![\w])(?:перед|before)\s+$", "by " if lang == "en" else "до ", prefix,
            flags=re.IGNORECASE,
        )
    if lang != "en" and (e is None or e == s):
        # «в новый год» → «1 января …», а не «в 1 января» («в 1» читалось бы как 01:00)
        prefix = re.sub(r"(?:\bво?\s+)$", "", prefix, flags=re.IGNORECASE)
    if recurring and lang != "en":
        # «каждый новый год» → «ежегодно 1 января» (форма ежегодного повтора в RU)
        prefix = re.sub(r"кажд\w+\s+(?:на\s+|в\s+)?$", "ежегодно ", prefix, flags=re.IGNORECASE)
    if e is not None and e != s:
        prefix = re.sub(r"(?:\b(?:во\s+время|на|в|во|on|over|during|for)\s+)$", "", prefix, flags=re.IGNORECASE)
    return prefix + repl + text[b:]

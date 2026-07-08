"""Определение языка ввода для выбора локали парсинга.

Контракт разрешения языка (от явного к неявному):
  1. Явный аргумент вызова parse(text, language=...) — переопределяет всё.
  2. Иначе config.default_language.
  3. Если он "auto" — detect_language(text) по сигналам предметной области.

Детектор намеренно НЕ использует общий language-detector: на коротких
строках («в 10», «Feb 17») они ненадёжны. Вместо этого — счёт по сигналам:
кириллица vs латиница + попадание токенов в ru/en списки-маркеры.

Политика неоднозначности: при нулевом счёте (чистые цифры «17.02») язык не
угадывается — возвращается fallback (по умолчанию "ru", т.к. пока это основная
рабочая локаль). Смешанный текст → побеждает больший счёт, при равенстве fallback.
"""

import re

SUPPORTED = ("ru", "en")

_CYR = re.compile(r"[а-яё]", re.IGNORECASE)
_LAT = re.compile(r"[a-z]", re.IGNORECASE)

# Небольшие списки характерных маркеров (не полные словари локалей).
_EN_MARKERS = {
    "at",
    "on",
    "in",
    "by",
    "next",
    "this",
    "last",
    "tomorrow",
    "today",
    "yesterday",
    "am",
    "pm",
    "every",
    "each",
    "week",
    "month",
    "year",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "noon",
    "midnight",
    "morning",
    "evening",
    "night",
    "afternoon",
    "hour",
    "hours",
    "minute",
    "minutes",
    "day",
    "days",
    "weekday",
    "weekend",
    "until",
    "before",
    "after",
}
_RU_MARKERS = {
    "в",
    "во",
    "на",
    "к",
    "до",
    "по",
    "с",
    "со",
    "за",
    "через",
    "после",
    "завтра",
    "сегодня",
    "вчера",
    "послезавтра",
    "утром",
    "днём",
    "днем",
    "вечером",
    "ночью",
    "каждый",
    "каждую",
    "каждые",
    "неделю",
    "месяц",
    "год",
    "часа",
    "часов",
    "минут",
    "минуту",
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
    "полдень",
    "полночь",
}


def detect_language(text, fallback="ru"):
    """Возвращает 'ru' или 'en' по сигналам текста; fallback при неоднозначности."""
    if not text:
        return fallback
    low = text.lower()
    cyr = len(_CYR.findall(low))
    lat = len(_LAT.findall(low))

    ru_score = cyr
    en_score = lat
    for w in re.findall(r"[a-zа-яё]+", low):
        if w in _EN_MARKERS:
            en_score += 5
        elif w in _RU_MARKERS:
            ru_score += 5

    if ru_score == 0 and en_score == 0:
        return fallback
    if en_score > ru_score:
        return "en"
    if ru_score > en_score:
        return "ru"
    return fallback


def resolve_language(text, requested, default_language):
    """Итоговый язык по контракту: явный → config → auto-detect."""
    lang = requested or default_language or "auto"
    if lang == "auto":
        return detect_language(text)
    if lang not in SUPPORTED:
        return "ru"
    return lang

# -*- coding: utf-8 -*-
"""Экспорт результатов разбора в iCalendar (.ics, RFC 5545).

Открывается в Google Calendar, Apple Calendar, Outlook.
    from timesense import TimeSenseParser
    from timesense.ics import to_ics, to_ics_calendar
    r = TimeSenseParser().parse("каждый понедельник в 10:00 планёрка", language="ru")
    print(to_ics(r))                 # один VEVENT в обёртке VCALENDAR
    print(to_ics_calendar([r1, r2])) # несколько событий одним файлом
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Optional

_PRODID = "-//timesense//NONSGML timesense//EN"


def _esc(text: str) -> str:
    """Экранирование текста по RFC 5545 (\\ ; , перевод строки)."""
    if text is None:
        return ""
    out = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    out = out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return out


def _fold(line: str) -> str:
    """Сворачивание строк длиннее 75 октетов (CRLF + пробел)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks = []
    cur = b""
    for ch in line:
        b = ch.encode("utf-8")
        # первая строка до 75 октетов, продолжения до 74 (учёт ведущего пробела)
        limit = 75 if not chunks else 74
        if len(cur) + len(b) > limit:
            chunks.append(cur)
            cur = b
        else:
            cur += b
    if cur:
        chunks.append(cur)
    first = chunks[0].decode("utf-8")
    rest = ["\r\n " + c.decode("utf-8") for c in chunks[1:]]
    return first + "".join(rest)


def _dt(value: datetime, *, date_only: bool = False) -> str:
    """DTSTART/DTEND значение. date_only → VALUE=DATE (для all-day)."""
    if date_only:
        return value.strftime("%Y%m%d")
    return value.strftime("%Y%m%dT%H%M%S")


def _uid(seed: str) -> str:
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]
    return f"{h}@timesense"


def _has_time(dt: datetime) -> bool:
    return (dt.hour, dt.minute, dt.second) != (0, 0, 0)


def _event_fields(result: Any) -> Optional[dict]:
    """Извлекает поля события из результата (тип определяем по атрибутам)."""
    title = getattr(result, "title", "") or "(без названия)"
    location = getattr(result, "location", None)
    rec = getattr(result, "recurrence", None)
    rrule = None
    if rec is not None:
        rd = rec.to_dict() if hasattr(rec, "to_dict") else rec
        rrule = rd.get("rrule") if isinstance(rd, dict) else None

    # ReminderResult: точечное время
    dt_at = getattr(result, "datetime_at", None)
    if dt_at is not None:
        return {
            "title": title, "location": location, "rrule": rrule,
            "start": dt_at, "end": None, "all_day": not _has_time(dt_at),
        }

    # CalendarResult: интервал времени
    start_at = getattr(result, "start_at", None)
    end_at = getattr(result, "end_at", None)
    deadline = getattr(result, "deadline", None)

    # 23:59[:00] — маркер «конец дня», а не реальное время конца
    def _is_eod(dt):
        return dt is not None and (dt.hour, dt.minute) == (23, 59)

    if deadline is not None:
        # дедлайн без реального времени (конец дня/месяца) → all-day на дату дедлайна
        all_day = not _has_time(deadline) or _is_eod(deadline)
        return {
            "title": title, "location": location, "rrule": rrule,
            "start": deadline, "end": None, "all_day": all_day,
        }
    if start_at is not None:
        # period/fuzzy с полночным стартом и 23:59-концом — это all-day диапазон
        end_is_eod = _is_eod(end_at) or (end_at is not None and not _has_time(end_at))
        all_day = not _has_time(start_at) and (end_at is None or end_is_eod)
        return {
            "title": title, "location": location, "rrule": rrule,
            "start": start_at, "end": end_at, "all_day": all_day,
        }
    return None


def _vevent(result: Any, stamp: datetime) -> Optional[List[str]]:
    f = _event_fields(result)
    if f is None:
        return None
    start = f["start"]
    end = f["end"]
    all_day = f["all_day"]
    lines = ["BEGIN:VEVENT"]
    lines.append(f"UID:{_uid(getattr(result, 'source', '') + str(start))}")
    lines.append(f"DTSTAMP:{_dt(stamp)}")
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_dt(start, date_only=True)}")
        # для all-day DTEND эксклюзивен → +1 день (или конец периода +1)
        end_day = (end or start) + timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{_dt(end_day, date_only=True)}")
    else:
        lines.append(f"DTSTART:{_dt(start)}")
        if end is not None:
            lines.append(f"DTEND:{_dt(end)}")
    if f["rrule"]:
        lines.append(f"RRULE:{f['rrule']}")
    lines.append(f"SUMMARY:{_esc(f['title'])}")
    if f["location"]:
        lines.append(f"LOCATION:{_esc(f['location'])}")
    lines.append("END:VEVENT")
    return [_fold(ln) for ln in lines]


def to_ics_calendar(results: Iterable[Any], *, stamp: Optional[datetime] = None) -> str:
    """Несколько результатов → один VCALENDAR (.ics). Пустые/None пропускаются."""
    # Наивный UTC (как раньше utcnow()), но без DeprecationWarning на 3.12+.
    stamp = stamp or datetime.now(timezone.utc).replace(tzinfo=None)
    body: List[str] = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{_PRODID}", "CALSCALE:GREGORIAN"]
    for r in results:
        if r is None:
            continue
        ev = _vevent(r, stamp)
        if ev:
            body.extend(ev)
    body.append("END:VCALENDAR")
    return "\r\n".join(body) + "\r\n"


def to_ics(result: Any, *, stamp: Optional[datetime] = None) -> str:
    """Один результат → .ics (VCALENDAR с одним VEVENT)."""
    return to_ics_calendar([result], stamp=stamp)

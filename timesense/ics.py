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
    chunks: List[bytes] = []
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


def _dt_prop(name: str, value: datetime, recurring: bool) -> str:
    """DTSTART/DTEND с учётом пояса.

    naive → floating-время (как раньше); aware с IANA-ключом у повторяющегося
    события → TZID=<ключ> (серия не «плывёт» при переходе на летнее время);
    прочие aware → UTC с Z.
    """
    if value.tzinfo is None:
        return f"{name}:{_dt(value)}"
    key = getattr(value.tzinfo, "key", None)
    if recurring and key:
        return f"{name};TZID={key}:{_dt(value)}"
    return f"{name}:{_dt(value.astimezone(timezone.utc))}Z"


def _fmt_offset(td: timedelta) -> str:
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "%s%02d%02d" % (sign, total // 3600, (total % 3600) // 60)


def _vtimezone(tz: Any, year: int) -> Optional[List[str]]:
    """VTIMEZONE для IANA-пояса (RFC 5545 §3.6.5): переходы года вычисляются из
    zoneinfo, правило — «N-е/последнее <день недели> месяца» (так их пишут
    Google/Outlook). Без перехода на летнее время — один STANDARD."""
    key = getattr(tz, "key", None)
    if not key:
        return None
    from calendar import monthrange

    def _off(moment: datetime) -> timedelta:
        return moment.astimezone(tz).utcoffset() or timedelta(0)

    day, hour = timedelta(days=1), timedelta(hours=1)
    cur = datetime(year, 1, 1, tzinfo=timezone.utc)
    prev = _off(cur)
    trans = []
    while cur.year == year:
        nxt = cur + day
        off = _off(nxt)
        if off != prev:
            h = cur
            while h + hour <= nxt and _off(h + hour) == prev:
                h += hour
            at = h + hour
            trans.append((at, prev, off, at.astimezone(tz).tzname() or key))
            prev = off
        cur = nxt
    lines = ["BEGIN:VTIMEZONE", "TZID:%s" % key]
    if not trans:
        name = datetime(year, 1, 1, tzinfo=tz).tzname() or key
        lines += ["BEGIN:STANDARD", "DTSTART:19700101T000000",
                  "TZOFFSETFROM:%s" % _fmt_offset(prev), "TZOFFSETTO:%s" % _fmt_offset(prev),
                  "TZNAME:%s" % name, "END:STANDARD"]
    else:
        codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        for at, off_from, off_to, name in trans:
            local = (at + off_from).replace(tzinfo=None)  # стенное время ДО перехода
            n = (local.day - 1) // 7 + 1
            if local.day + 7 > monthrange(local.year, local.month)[1]:
                n = -1  # последний такой день месяца
            kind = "DAYLIGHT" if off_to > off_from else "STANDARD"
            lines += ["BEGIN:%s" % kind, "DTSTART:%s" % local.strftime("%Y%m%dT%H%M%S"),
                      "TZOFFSETFROM:%s" % _fmt_offset(off_from), "TZOFFSETTO:%s" % _fmt_offset(off_to),
                      "RRULE:FREQ=YEARLY;BYMONTH=%d;BYDAY=%d%s" % (local.month, n, codes[local.weekday()]),
                      "TZNAME:%s" % name, "END:%s" % kind]
    lines.append("END:VTIMEZONE")
    return lines


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


def _vevent(result: Any, stamp: datetime, alarm_minutes: Optional[int] = None) -> Optional[List[str]]:
    f = _event_fields(result)
    if f is None:
        return None
    start = f["start"]
    end = f["end"]
    all_day = f["all_day"]
    lines = ["BEGIN:VEVENT"]
    lines.append(f"UID:{_uid(getattr(result, 'source', '') + str(start))}")
    # RFC 5545: DTSTAMP обязан быть в UTC (с Z)
    lines.append(f"DTSTAMP:{_dt(stamp)}Z")
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{_dt(start, date_only=True)}")
        # для all-day DTEND эксклюзивен → +1 день (или конец периода +1)
        end_day = (end or start) + timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{_dt(end_day, date_only=True)}")
    else:
        recurring = bool(f["rrule"])
        lines.append(_dt_prop("DTSTART", start, recurring))
        if end is not None:
            lines.append(_dt_prop("DTEND", end, recurring))
    if f["rrule"]:
        rrule = f["rrule"]
        if all_day:
            # RFC 5545: тип UNTIL совпадает с DTSTART; у события на весь день — DATE
            import re as _re

            rrule = _re.sub(r"UNTIL=(\d{8})T\d{6}Z?", r"UNTIL=\1", rrule)
        lines.append(f"RRULE:{rrule}")
        # EXDATE того же типа, что DTSTART (RFC 5545 §3.8.5.1)
        rec_obj = getattr(result, "recurrence", None)
        for ex in (getattr(rec_obj, "exdates", None) or []):
            if all_day:
                lines.append(f"EXDATE;VALUE=DATE:{ex.strftime('%Y%m%d')}")
            else:
                lines.append(_dt_prop("EXDATE", ex, True))
    lines.append(f"SUMMARY:{_esc(f['title'])}")
    if f["location"]:
        lines.append(f"LOCATION:{_esc(f['location'])}")
    if alarm_minutes is not None:
        if alarm_minutes < 0:
            raise ValueError("alarm_minutes must be >= 0")
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(f['title'])}",
                  f"TRIGGER:-PT{int(alarm_minutes)}M", "END:VALARM"]
    lines.append("END:VEVENT")
    return [_fold(ln) for ln in lines]


def _tz_of_recurring(result: Any):
    """Пояс (IANA) повторяющегося aware-события — для VTIMEZONE."""
    f = _event_fields(result)
    if not f or not f["rrule"] or f["all_day"]:
        return None, None
    st = f["start"]
    if st.tzinfo is None or not getattr(st.tzinfo, "key", None):
        return None, None
    return st.tzinfo, st.year


def to_ics_calendar(
    results: Iterable[Any], *, stamp: Optional[datetime] = None, alarm_minutes: Optional[int] = None
) -> str:
    """Несколько результатов → один VCALENDAR (.ics). Пустые/None пропускаются.

    stamp — момент создания (DTSTAMP); naive считается UTC.
    alarm_minutes — добавить напоминание (VALARM) за N минут до начала (0 — в момент начала).
    """
    if stamp is None:
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
    elif stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    results = [r for r in results if r is not None]
    body: List[str] = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{_PRODID}", "CALSCALE:GREGORIAN"]
    # VTIMEZONE для каждого IANA-пояса, на который ссылаются повторы с TZID
    seen = set()
    for r in results:
        tz, year = _tz_of_recurring(r)
        if tz is not None and (tz.key, year) not in seen:
            seen.add((tz.key, year))
            vt = _vtimezone(tz, year)
            if vt:
                body.extend(_fold(ln) for ln in vt)
    for r in results:
        ev = _vevent(r, stamp, alarm_minutes)
        if ev:
            body.extend(ev)
    body.append("END:VCALENDAR")
    return "\r\n".join(body) + "\r\n"


def to_ics(result: Any, *, stamp: Optional[datetime] = None, alarm_minutes: Optional[int] = None) -> str:
    """Один результат → .ics (VCALENDAR с одним VEVENT)."""
    return to_ics_calendar([result], stamp=stamp, alarm_minutes=alarm_minutes)

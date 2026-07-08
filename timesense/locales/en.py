"""English locale for TimeSense — regex-driven date/time/recurrence parser.

Produces a single best DateTimeToken (with flags the shared classifier understands)
plus a cleaned title. English grammar is positional/regular, so this locale parses
the raw (lowercased) text with ordered regex handlers rather than morphology.

Covered: today/tomorrow/tonight/yesterday/day after tomorrow; [next|this|last]
weekday; month-name dates (Feb 17 / 17 Feb / March 3rd [, YYYY]); MM/DD[/YYYY] and
ISO; times (at 5pm, 5:30pm, at 17:00, noon, midnight, day-parts); in N units;
ranges (from 9 to 5, 9am-11am, between 10 and 12); recurrence (every day/week/
month/year, daily/weekly, every Monday, every weekday/on weekdays, every N units,
every other week, every month on the Nth); deadlines (by/before/due <date|time>,
by end of week/month/year); duration (for N hours/minutes).
"""

import re
from datetime import datetime, timedelta
from calendar import monthrange
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule

WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_WD = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
    "half": 0.5,
}
DAYPARTS = {
    "morning": (9, 12),
    "afternoon": (12, 15),
    "evening": (18, 22),
    "night": (22, 30),
    "tonight": (18, 22),
}
_FILLER = {
    "a",
    "an",
    "the",
    "at",
    "on",
    "in",
    "by",
    "of",
    "to",
    "from",
    "and",
    "please",
    "remind",
    "me",
    "reminder",
    "for",
    "this",
    "next",
    "last",
    "every",
    "each",
    "before",
    "after",
    "due",
    "um",
    "uh",
    "like",
    "so",
    "on",
    "with",
    "except",
    "excluding",
    "through",
    "around",
    "about",
    "exactly",
    "sharp",
    "roughly",
    "approximately",
    "maybe",
    "perhaps",
    "pls",
    "gotta",
    "wanna",
    "either",
    "or",
}


class EnglishLocaleParser:
    _EN_NUM = {
        "zero": 0,
        "oh": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fourty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
        "hundred": 100,
    }

    def __init__(self, config):
        self.config = config
        self.nf = config.prefer_nearest_future

    def _invalid_date(self, low):
        """True для невозможной явной даты: 'Feb 31', '31 Feb', '2/31'."""
        from calendar import monthrange

        def bad(mon, day, year=None):
            if not (1 <= day <= 31):
                return False
            maxd = (
                monthrange(year, mon)[1] if year else (29 if mon == 2 else monthrange(2001, mon)[1])
            )
            return day > maxd

        m = re.search(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", low)
        if m and bad(MONTHS[m.group(1)], int(m.group(2)), int(m.group(3)) if m.group(3) else None):
            return True
        m = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MON + r")\.?(?:,?\s+(\d{4}))?\b", low
        )
        if m and bad(MONTHS[m.group(2)], int(m.group(1)), int(m.group(3)) if m.group(3) else None):
            return True
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
        if m:
            mo = int(m.group(1))
            day = int(m.group(2))
            yr = m.group(3)
            if 1 <= mo <= 12:
                y = int(yr) if yr else None
                if y is not None and y < 100:
                    y += 2000
                if bad(mo, day, y):
                    return True
        return False

    # ── number-word preprocessing (voice / spelled-out) ──────────────────
    def _num_run(self, toks, i):
        cur = 0
        cnt = 0
        got = False
        while i + cnt < len(toks):
            v = self._EN_NUM.get(toks[i + cnt])
            if v is None:
                break
            if v >= 100:
                cur = (cur or 1) * v
            else:
                cur += v
            got = True
            cnt += 1
            if v < 20:  # unit/teen ends the run
                break
        return (cur, cnt) if got else (0, 0)

    def _digitize(self, s):
        toks = s.split(" ")
        out = []
        i = 0
        while i < len(toks):
            val, cnt = self._num_run(toks, i)
            if cnt > 0:
                out.append(str(val))
                i += cnt
            else:
                out.append(toks[i])
                i += 1
        return " ".join(out)

    _ORD_ONES = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
        "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
        "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
        "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
    }
    _ORD_TENS = {"twenty": 20, "thirty": 30}
    _ORD_UNIT = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
    }

    def _fold_ordinals(self, s):
        """Порядковые слова дня месяца → цифра+th, чтобы _month_date их поймал.
        Составные: 'twenty eighth' → '28th'; одиночные: 'fifteenth' → '15th'.
        Делается ДО _digitize, иначе 'twenty' уедет в 20, а 'eighth' потеряется."""
        def _comp(m):
            return str(self._ORD_TENS[m.group(1)] + self._ORD_UNIT[m.group(2)]) + "th"

        _kind = (
            r"(?:business\s+day|weekday|weekend|week|last|to|" + _WD + r")"
        )
        s = re.sub(
            r"\b(twenty|thirty)\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)"
            r"\b(?![-\s]" + _kind + r")",
            _comp,
            s,
        )

        def _single(m):
            return str(self._ORD_ONES[m.group(1)]) + "th"

        s = re.sub(
            r"\b(" + "|".join(self._ORD_ONES) + r")\b(?![-\s]" + _kind + r")", _single, s
        )
        return s

    def _preprocess(self, s):
        # «no later than» / «not later than» → «by» (дедлайн-синоним) -> by
        s = re.sub(r"\bno(?:t)?\s+later\s+than\b", "by", s)
        # forty-five → forty five (не трогаем границы с цифрами, чтобы не сломать 9am-11am)
        s = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", s)
        s = self._fold_ordinals(s)
        s = self._digitize(s)
        # clock idioms → "at H:MM"
        s = re.sub(r"\bhalf past (\d{1,2})\b", lambda m: "at %d:30" % int(m.group(1)), s)
        s = re.sub(r"\bquarter past (\d{1,2})\b", lambda m: "at %d:15" % int(m.group(1)), s)
        s = re.sub(
            r"\bquarter to (\d{1,2})\b", lambda m: "at %d:45" % ((int(m.group(1)) - 1) % 24), s
        )
        s = re.sub(r"\b(\d{1,2})\s*o'?clock\b", lambda m: "at %d:00" % int(m.group(1)), s)
        # "at 10 30" / "ten thirty" (после digitize → "10 30") → 10:30
        s = re.sub(
            r"\bat (\d{1,2}) (\d{2})\b", lambda m: "at %d:%s" % (int(m.group(1)), m.group(2)), s
        )
        # "at 9-30" / "at 9.30" → "at 9:30" (дефис/точка = разделитель минут, минуты 0..59)
        s = re.sub(
            r"\bat (\d{1,2})[.\-](\d{2})\b",
            lambda m: ("at %d:%02d" % (int(m.group(1)), int(m.group(2)))) if int(m.group(2)) <= 59 else m.group(0),
            s,
        )
        s = re.sub(
            r"\b(\d{1,2}) (00|05|10|15|20|25|30|35|40|45|50|55)\b(?!\s*(?:to|-|:|am|pm|and))",
            lambda m: (
                ("%d:%s" % (int(m.group(1)), m.group(2)))
                if 0 <= int(m.group(1)) <= 23
                else m.group(0)
            ),
            s,
        )
        return s

    # ── public ──────────────────────────────────────────────────────────
    # Существительные-места для извлечения локации (зеркало RU LOCATION_MARKERS)
    _LOC_NOUNS = frozenset(
        [
            "office",
            "home",
            "cafe",
            "restaurant",
            "park",
            "gym",
            "school",
            "university",
            "college",
            "hospital",
            "clinic",
            "bank",
            "airport",
            "station",
            "club",
            "studio",
            "cinema",
            "theater",
            "theatre",
            "museum",
            "library",
            "pool",
            "stadium",
            "mall",
            "shop",
            "store",
            "work",
            "downtown",
            "bar",
            "hotel",
            "beach",
            "rooftop",
            "zoom",
        ]
    )
    # Двусловные места («at the client site», «in the meeting room»).
    _LOC_PHRASES = (
        "meeting room",
        "conference room",
        "client site",
        "video call",
        "war room",
        "server room",
    )

    def _location(self, low):
        """«at/in [the] <место>» → (фраза локации, существительное) | None.

        Как и в RU: маркер места считается локацией только с предлогом,
        иначе слово остаётся частью названия события.
        """
        # сначала двусловные («in the meeting room», «at the client site»)
        for ph in self._LOC_PHRASES:
            mm = re.search(r"\b(at|in)\s+(?:the\s+)?" + ph + r"\b", low)
            if mm:
                return mm.group(0), ph.split()
        for m in re.finditer(r"\b(at|in)\s+(?:the\s+)?([a-z]+)\b", low):
            if m.group(2) in self._LOC_NOUNS:
                return m.group(0), [m.group(2)]
        return None

    def parse(self, text, now):
        """→ (DateTimeToken | None, title, duration_minutes, location | None)."""
        dt, title, dur = self._parse_impl(text, now)
        loc = None
        if dt is not None:
            found = self._location(self._preprocess(text.lower()))
            if found:
                loc, nouns = found
                # слова места не должны оставаться в названии события
                if title:
                    drop = {w.lower() for w in nouns}
                    title = " ".join(
                        w for w in title.split() if w.lower() not in drop
                    )
        return dt, title, dur, loc

    def _parse_impl(self, text, now):
        """→ (DateTimeToken | None, title, duration_minutes)."""
        low = self._preprocess(text.lower())
        if self._invalid_date(low):
            return (None, "", None)
        # Часовые пояса не поддерживаются — не парсим молча как локальное время.
        _TZ_ABBR = r"\b(utc|gmt|est|edt|cst|cdt|mst|mdt|pst|pdt|cet|cest|eet|bst|ist|jst|aest|msk)\b"
        _TZ_CITY = r"\b(?:moscow|london|new\s*york|tokyo|paris|berlin|beijing|sydney|dubai)\s+time\b"
        if (
            re.search(_TZ_ABBR, low)
            or re.search(r"(?:gmt|utc)\s*[+-]\s*\d", low)
            or re.search(_TZ_CITY, low)
        ):
            return (None, "", None)
        # last week/month/quarter/year + только время (без дня недели/числа) →
        # момент внутри периода не определяется → None (паритет с RU).
        if self._ambiguous_last_period(low):
            return (None, "", None)
        # относительные рабочие дни (in N business days / next business day /
        # by the first business day of next month)
        br = self._business_relative(low, now)
        if br is not None:
            dt, sp = br
            title = self._title(low, [sp])
            return dt, title, None
        text = low  # title строим от нормализованного текста (спаны совпадают)
        spans = []  # (start, end) consumed by date/time/recurrence machinery

        # first/last/Nth <weekday|business day|weekend|week> of the month (+ every)
        om = self._ordinal_of_month(low, now) or self._month_day_rel(low, now)
        if om is not None:
            dt, sp = om
            spans.append(sp)
            rest = low[: sp[0]] + (" " * (sp[1] - sp[0])) + low[sp[1] :]
            tr = self._time(rest, now)
            if tr is not None and not isinstance(tr[3], tuple):
                h, m, tsp, _ = tr
                spans.append(tsp)
                dt.date_from = dt.date_from.replace(hour=h, minute=m)
                dt.date_to = dt.date_from
                dt.has_time = True
                dt.all_day = False
            title = self._title(text, spans)
            return dt, title, None

        rec, rspan = self._recurrence(low, now)

        # deadline?
        dl = self._deadline(low, now)
        if dl is not None:
            dt, sp = dl
            spans.append(sp)
            title = self._title(text, spans)
            return dt, title, None

        # Детектим дату первой и маскируем её в рабочей строке, чтобы цифры
        # даты (ISO 2026-02-17) не съедались range/time-регэкспами.
        date_res = self._date(low, now)
        low2 = low
        date = None
        fuzzy = False
        is_period = False
        period_end = None
        if date_res is not None:
            date, dsp, fuzzy, is_period, period_end = date_res
            spans.append(dsp)
            low2 = low[: dsp[0]] + (" " * (dsp[1] - dsp[0])) + low[dsp[1] :]

        # ranges → explicit period (calendar)
        rng = self._range(low2, now)
        if rng is not None:
            dt, sp = rng
            spans.append(sp)
            if date is not None:
                # перенести диапазон на явную дату (длительность берём ДО мутации date_from)
                span = dt.date_to - dt.date_from
                dt.date_from = dt.date_from.replace(year=date.year, month=date.month, day=date.day)
                dt.date_to = dt.date_from + span
                # is_past для диапазона на явной дате (yesterday/last Friday from ... to ...)
                dt.is_past = dt.date_from < now
            if rec is not None:
                dt.recurrence = rec
                spans.append(rspan)
            title = self._title(text, spans)
            return dt, title, None

        time_res = self._time(low2, now)  # (hour, minute, span, has_time|daypart-tuple)
        dur = self._duration(low2)

        # относительный интервал + время суток: «in two weeks at 16:05» =
        # целевой день из «in N units», час из «at HH:MM». Должно идти ДО
        # общей time-ветки, иначе время перебьёт интервал (даст сегодня).
        if rec is None and date is None:
            rel_pre = self._relative(low2, now)
            if rel_pre is not None:
                rdt, rsp = rel_pre
                if not rdt.has_time and time_res is not None and not isinstance(
                    time_res[3], tuple
                ):
                    h, m, tsp, _ = time_res
                    rdt.date_from = rdt.date_from.replace(
                        hour=h, minute=m, second=0, microsecond=0
                    )
                    rdt.date_to = rdt.date_from
                    rdt.has_time = True
                    rdt.all_day = False
                    rdt.is_past = rdt.date_from < now
                    spans.append(rsp)
                    spans.append(tsp)
                    title = self._title(text, spans)
                    return rdt, title, dur

        if rec is not None:
            spans.append(rspan)
            base = now.replace(second=0, microsecond=0)
            has_time = False
            if time_res is not None:
                h, m, tsp, _ = time_res
                base = base.replace(hour=h, minute=m)
                has_time = True
                spans.append(tsp)
            start = self._recurrence_dtstart(rec, base, now, has_time)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=start,
                date_to=start,
                has_time=has_time,
                all_day=not has_time,
                recurrence=rec,
                confidence=0.9,
            )
            title = self._title(text, spans)
            return dt, title, None

        if time_res is not None:
            h, m, tsp, has_time = time_res
            spans.append(tsp)
            if isinstance(has_time, tuple):  # daypart period
                s, e = has_time
                base_day = date or now
                df = base_day.replace(hour=s % 24, minute=0, second=0, microsecond=0)
                dtt = base_day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                    hours=e
                )
                if date is None and self.nf and df < now:
                    df += timedelta(days=1)
                    dtt += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=df,
                    date_to=dtt,
                    has_time=True,
                    fuzzy=True,
                    confidence=0.75,
                )
                title = self._title(text, spans)
                return dt, title, dur
            base = (date or now).replace(hour=h, minute=m, second=0, microsecond=0)
            if date is None and self.nf and base < now:
                base += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=base,
                date_to=base,
                has_time=True,
                confidence=0.9,
                is_past=base < now,
            )
            title = self._title(text, spans)
            return dt, title, dur

        if date is not None:
            if is_period:
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=date,
                    date_to=period_end,
                    has_time=False,
                    all_day=not fuzzy,
                    fuzzy=fuzzy,
                    confidence=0.8,
                )
                # is_past для fuzzy-периода: весь период уже прошёл (last week …)
                if period_end is not None and period_end < now:
                    dt.is_past = True
            else:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=date,
                    date_to=date.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    fuzzy=fuzzy,
                    confidence=0.9,
                    is_past=date.date() < now.date(),
                )
            title = self._title(text, spans)
            return dt, title, dur

        rel = self._relative(low2, now)
        if rel is not None:
            dt, sp = rel
            spans.append(sp)
            title = self._title(text, spans)
            return dt, title, dur

        return None, self._title(text, spans), None

    def _ambiguous_last_period(self, low):
        """True для 'last week/month/quarter/year' + только время (без дня недели
        и без числа). Момент внутри периода неоднозначен → None. Продуктивные
        случаи (last week on Thursday, last month on the 15th) и чистый период без
        времени (last week review …) сюда не попадают."""
        m = re.search(r"\blast\s+(week|month|quarter|year)\b", low)
        if not m:
            return False
        unit = m.group(1)
        has_time = bool(re.search(r"\bat\s+\d", low) or re.search(r"\b\d{1,2}:\d{2}\b", low))
        has_wd = bool(re.search(r"\b" + _WD + r"\b", low))
        has_daynum = bool(re.search(r"\b\d{1,2}(?:st|nd|rd|th)\b", low))
        if not (has_time or has_wd or has_daynum):
            return False
        if unit == "week" and has_wd:
            return False
        if unit == "month" and has_daynum and not has_time and not has_wd:
            return False
        return True

    def _add_business_days(self, base, n):
        t = base
        added = 0
        while added < n:
            t += timedelta(days=1)
            if self._is_working(t):
                added += 1
        return t

    def _business_relative(self, low, now):
        """Относительные рабочие дни:
        in N business days → +N рабочих дней (09:00); next business day → +1;
        by the first business day of next month → дедлайн на 1-й рабочий день;
        N business days before end of month → конец месяца − N рабочих дней."""
        # before_end_business: N business days before [the] end of [the] month
        m = re.search(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+business\s+days?"
            r"\s+before\s+(?:the\s+)?end\s+of\s+(?:the\s+)?month\b",
            low,
        )
        if m:
            w = m.group(1)
            n = NUM_WORDS.get(w)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                year, month = now.year, now.month
                last = monthrange(year, month)[1]
                target = datetime(year, month, last, 0, 0)
                if target.date() < now.date():
                    month2 = month + 1
                    year2 = year + (1 if month2 > 12 else 0)
                    month2 = (month2 - 1) % 12 + 1
                    last2 = monthrange(year2, month2)[1]
                    target = datetime(year2, month2, last2, 0, 0)
                stepped = 0
                while stepped < int(n):
                    target -= timedelta(days=1)
                    if self._is_working(target):
                        stepped += 1
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    is_deadline=True,
                    confidence=0.85,
                )
                return dt, m.span()
        # by the first business day of next month
        m = re.search(
            r"\b(?:by|before|due)\s+the\s+first\s+business\s+day\s+of\s+next\s+month\b", low
        )
        if m:
            mo2 = now.month + 1
            y2 = now.year + (1 if mo2 > 12 else 0)
            mo2 = (mo2 - 1) % 12 + 1
            dim = monthrange(y2, mo2)[1]
            target = None
            for d in range(1, dim + 1):
                cand = datetime(y2, mo2, d)
                if self._is_working(cand):
                    target = cand
                    break
            if target is not None:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    is_deadline=True,
                    confidence=0.85,
                )
                return dt, m.span()
        # in N business days
        m = re.search(
            r"\bin\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+business\s+days?\b",
            low,
        )
        if m:
            w = m.group(1)
            n = NUM_WORDS.get(w)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                base = now.replace(hour=9, minute=0, second=0, microsecond=0)
                target = self._add_business_days(base, int(n))
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=False,
                    all_day=True,
                    confidence=0.9,
                )
                return dt, m.span()
        # next business day
        m = re.search(r"\bnext\s+business\s+day\b", low)
        if m:
            base = now.replace(hour=9, minute=0, second=0, microsecond=0)
            target = self._add_business_days(base, 1)
            dt = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=target,
                date_to=target,
                has_time=False,
                all_day=True,
                confidence=0.9,
            )
            return dt, m.span()
        return None

    # ── date ────────────────────────────────────────────────────────────
    def _is_working(self, d):
        cal = getattr(self.config, "calendar", None)
        if cal is not None:
            return cal.is_working_day(d)
        return d.weekday() < 5

    def _ordinal_of_month(self, low, now):
        from calendar import monthrange

        ORD = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "1st": 1,
            "2nd": 2,
            "3rd": 3,
            "4th": 4,
            "5th": 5,
            "last": -1,
            "penultimate": -2,
        }
        ord_alt = r"first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|penultimate|last|(?:second|next)[-\s]to[-\s]last"
        kind_alt = r"business\s+day|weekday|weekend|week|" + _WD
        # Форма с конкретным месяцем: «first Tuesday of [every] January» → YEARLY.
        fixed_month = None
        m = re.search(
            r"\b(every\s+)?(" + ord_alt + r")\s+(" + kind_alt + r")"
            r"\s+of\s+(?:every\s+)?(" + _MON + r")\b",
            low,
        )
        if m:
            fixed_month = MONTHS[m.group(4)]
            # «of every January» тоже означает повторение, даже без ведущего every
            if re.search(r"of\s+every\s+" + _MON, low):
                every_from_month = True
            else:
                every_from_month = False
        else:
            m = re.search(
                r"\b(every\s+)?(" + ord_alt + r")\s+(" + kind_alt + r")\s+of\s+the\s+month\b",
                low,
            )
            every_from_month = False
        if not m:
            return None
        every = bool(m.group(1)) or every_from_month
        ow = m.group(2)
        pos = -2 if "to" in ow else ORD.get(ow)
        if pos is None:
            return None
        kind_raw = m.group(3)
        wd = None
        if re.fullmatch(_WD, kind_raw):
            kind = "weekday_name"
            wd = WEEKDAYS[kind_raw]
        elif kind_raw == "weekend":
            kind = "weekend"
        elif kind_raw == "week":
            kind = "week"
        else:
            kind = "business"

        def compute(year, month):
            dim = monthrange(year, month)[1]
            if kind == "week":
                if pos == 1:
                    return datetime(year, month, 1), datetime(year, month, min(7, dim), 23, 59)
                return datetime(year, month, max(1, dim - 6)), datetime(year, month, dim, 23, 59)
            if kind == "weekday_name":
                days = [d for d in range(1, dim + 1) if datetime(year, month, d).weekday() == wd]
            elif kind == "business":
                days = [d for d in range(1, dim + 1) if self._is_working(datetime(year, month, d))]
            else:  # weekend → субботы
                days = [d for d in range(1, dim + 1) if datetime(year, month, d).weekday() == 5]
            idx = pos - 1 if pos > 0 else len(days) + pos
            if not (0 <= idx < len(days)):
                return None, None
            s = datetime(year, month, days[idx])
            e = s.replace(hour=23, minute=59)
            if kind == "weekend":
                e = (s + timedelta(days=1)).replace(hour=23, minute=59)
            return s, e

        if fixed_month is not None:
            # конкретный месяц: ищем ближайший год, где дата ещё не прошла
            y = now.year
            s, e = compute(y, fixed_month)
            if s is None or s.date() < now.date():
                s, e = compute(y + 1, fixed_month)
            if s is None:
                return None
        else:
            y, mo = now.year, now.month
            s, e = compute(y, mo)
            if s is None or s.date() < now.date():
                mo2 = mo + 1
                y2 = y + (1 if mo2 > 12 else 0)
                mo2 = (mo2 - 1) % 12 + 1
                s2, e2 = compute(y2, mo2)
                if s2 is not None:
                    s, e = s2, e2
            if s is None:
                return None
        rec = None
        if every:
            freq = "YEARLY" if fixed_month is not None else "MONTHLY"
            bm = [fixed_month] if fixed_month is not None else None
            if kind == "weekday_name":
                rec = RecurrenceRule(
                    frequency=freq, by_day=[f"{pos}{RRULE_DAYS[wd]}"], by_month=bm
                )
            elif kind == "business":
                rec = RecurrenceRule(
                    frequency=freq, by_day=["MO", "TU", "WE", "TH", "FR"],
                    by_set_pos=pos, by_month=bm,
                )
            elif kind == "weekend":
                rec = RecurrenceRule(
                    frequency=freq, by_day=["SA", "SU"], by_set_pos=pos, by_month=bm
                )
            else:
                rec = RecurrenceRule(frequency=freq, by_month=bm)
        is_range = kind in ("weekend", "week")
        dt = DateTimeToken(
            type=DateTimeType.PERIOD if is_range else DateTimeType.FIXED,
            date_from=s,
            date_to=e if is_range else s.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            recurrence=rec,
            confidence=0.9,
        )
        if is_range:
            dt.is_explicit_range = True
        return dt, m.span()

    def _ordinal_of_month_disabled(self):
        pass

    def _month_day_rel(self, low, now):
        """first <weekday|business day> after the Nth;
        last <weekday|business day> before the end of the month."""
        from calendar import monthrange

        kind_alt = r"business\s+day|weekday|" + _WD

        def kind_of(raw):
            if re.fullmatch(_WD, raw):
                return ("weekday", WEEKDAYS[raw])
            return ("business", None)

        # after the Nth
        m = re.search(
            r"\b(?:first\s+)?(" + kind_alt + r")\s+after\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", low
        )
        if m:
            kind, wd = kind_of(m.group(1))
            n = int(m.group(2))
            if 1 <= n <= 31:

                def comp(y, mo):
                    dim = monthrange(y, mo)[1]
                    for d in range(n + 1, dim + 1):
                        dt = datetime(y, mo, d)
                        if (kind == "weekday" and dt.weekday() == wd) or (
                            kind == "business" and self._is_working(dt)
                        ):
                            return dt
                    return None

                t = comp(now.year, now.month)
                if t is None or t.date() < now.date():
                    mo2 = now.month + 1
                    y2 = now.year + (1 if mo2 > 12 else 0)
                    mo2 = (mo2 - 1) % 12 + 1
                    t = comp(y2, mo2) or t
                if t is not None:
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=t,
                        date_to=t.replace(hour=23, minute=59),
                        has_time=False,
                        all_day=True,
                        confidence=0.9,
                    )
                    return dt, m.span()

        # before the end of the month
        m = re.search(
            r"\b(?:last\s+)?(" + kind_alt + r")\s+before\s+the\s+end\s+of\s+the\s+month\b", low
        )
        if m:
            kind, wd = kind_of(m.group(1))

            def comp(y, mo):
                dim = monthrange(y, mo)[1]
                for d in range(dim, 0, -1):
                    dt = datetime(y, mo, d)
                    if (kind == "weekday" and dt.weekday() == wd) or (
                        kind == "business" and self._is_working(dt)
                    ):
                        return dt
                return None

            t = comp(now.year, now.month)
            if t is None or t.date() < now.date():
                mo2 = now.month + 1
                y2 = now.year + (1 if mo2 > 12 else 0)
                mo2 = (mo2 - 1) % 12 + 1
                t = comp(y2, mo2) or t
            if t is not None:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=t,
                    date_to=t.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    confidence=0.9,
                )
                return dt, m.span()
        return None

    def _date(self, low, now):
        # Диапазон дат «from MONTH D to [MONTH] D» → период (before N-units-ago,
        # иначе _range растащит «10 to 12» как время). Должно идти первым.
        dr = self._date_range(low, now)
        if dr is not None:
            return dr
        # N units ago → прошлая дата (three days ago, two weeks ago, a month ago)
        m = re.search(
            r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(day|days|week|weeks|month|months|year|years)\s+ago\b",
            low,
        )
        if m:
            w = m.group(1)
            n = 1 if w in ("a", "an") else NUM_WORDS.get(w, None)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                unit = m.group(2)
                base = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if unit.startswith("day"):
                    d = base - timedelta(days=n)
                elif unit.startswith("week"):
                    d = base - timedelta(weeks=n)
                elif unit.startswith("month"):
                    d = self._add_months(base, -n)
                else:
                    d = self._add_months(base, -n * 12)
                return d, m.span(), False, False, None
        # day after tomorrow
        m = re.search(r"\b(?:the\s+)?day after tomorrow\b", low)
        if m:
            d = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        m = re.search(r"\btomorrow\b", low)
        if m:
            return (
                (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        m = re.search(r"\byesterday\b", low)
        if m:
            return (
                (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        m = re.search(r"\btoday\b", low)
        if m:
            return (
                now.replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        # next/this/last week
        m = re.search(r"\b(next|this|last)\s+week\b", low)
        if m:
            ref = now + timedelta(weeks={"next": 1, "this": 0, "last": -1}[m.group(1)])
            mon = (ref - timedelta(days=ref.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sun = (mon + timedelta(days=6)).replace(hour=23, minute=59)
            return mon, m.span(), True, True, sun
        # [next|this|last] [coming] weekday
        # «coming» (this coming Saturday / coming Friday) = ближайший день, как this.
        m = re.search(r"\b(next|this|last)?\s*(?:coming\s+)?(" + _WD + r")\b", low)
        if m and m.group(2):
            wd = WEEKDAYS[m.group(2)]
            mod = m.group(1)
            if mod == "last":
                delta = -(((now.weekday() - wd) % 7) or 7)
            elif mod == "next":
                # Конвенция (как в RU): «next X» = ближайший X (включая сегодня) + неделя.
                # next Thursday в среду → чт следующей недели, НЕ завтра.
                delta = (wd - now.weekday()) % 7 + 7
            else:  # this / none → nearest upcoming (or today)
                delta = (wd - now.weekday()) % 7
                if delta == 0 and mod is None:
                    delta = 7 if self.nf else 0
            d = (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        # month-name forms
        d = self._month_date(low, now)
        if d is not None:
            return d
        # numeric MM/DD[/YYYY] or ISO
        d = self._numeric_date(low, now)
        if d is not None:
            return d
        # сезоны (in spring/…): после явных дат, чтобы «spring» в названии
        # не перебивал конкретную дату (March twenty first … spring presentation)
        sea = self._season(low, now)
        if sea is not None:
            return sea
        # end/beginning/middle of week/month/year (fuzzy period, no "by")
        m = re.search(
            r"\b(?:at\s+the\s+)?(beginning|start|middle|mid|end)\s+of\s+(?:the\s+|this\s+|next\s+)?(week|month|year|quarter)\b",
            low,
        )
        if m:
            part = {
                "beginning": "start",
                "start": "start",
                "middle": "middle",
                "mid": "middle",
                "end": "end",
            }[m.group(1)]
            s_full, e_full = self._period_bounds(m.group(2), now)
            s, e = self._part_window(m.group(2), part, s_full, e_full)
            return s, m.span(), True, True, e
        return None

    def _date_range(self, low, now):
        """from MONTH D to [MONTH] D / from D to D MONTH → период дат.
        Конец в прошлом относительно старта → +год (december 25 to january 5)."""
        # from MONTH D to MONTH D
        m = re.search(
            r"\bfrom\s+(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
            r"\s+to\s+(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            low,
        )
        if m:
            mo1, d1 = MONTHS[m.group(1)], int(m.group(2))
            mo2, d2 = MONTHS[m.group(3)], int(m.group(4))
        else:
            # from MONTH D to D (второй день тот же месяц)
            m = re.search(
                r"\bfrom\s+(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
                r"\s+to\s+(\d{1,2})(?:st|nd|rd|th)?\b",
                low,
            )
            if m:
                mo1 = mo2 = MONTHS[m.group(1)]
                d1, d2 = int(m.group(2)), int(m.group(3))
            else:
                # from D to D MONTH (месяц в конце)
                m = re.search(
                    r"\bfrom\s+(\d{1,2})(?:st|nd|rd|th)?\s+to\s+"
                    r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MON + r")\.?\b",
                    low,
                )
                if not m:
                    return None
                mo1 = mo2 = MONTHS[m.group(3)]
                d1, d2 = int(m.group(1)), int(m.group(2))
        year = now.year
        start = self._safe(year, mo1, d1)
        if start is None:
            return None
        end_year = year + 1 if mo2 < mo1 else year
        end = self._safe(end_year, mo2, d2)
        if end is None:
            return None
        # весь период в прошлом → перенос на следующий год (оба конца)
        if self.nf and start.date() < now.date():
            start2 = self._safe(year + 1, mo1, d1)
            end2 = self._safe(year + 1 + (1 if mo2 < mo1 else 0), mo2, d2)
            if start2 is not None and end2 is not None:
                start, end = start2, end2
        end = end.replace(hour=23, minute=59)
        return start, m.span(), False, True, end

    def _month_date(self, low, now):
        # Feb 17 [, 2026] / Feb 17th
        m = re.search(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", low)
        if not m:
            # 17 Feb [2026] / 3rd of March
            m = re.search(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MON + r")\.?(?:,?\s+(\d{4}))?\b",
                low,
            )
            if not m:
                return None
            day = int(m.group(1))
            mon = MONTHS[m.group(2)]
            yr = m.group(3)
        else:
            mon = MONTHS[m.group(1)]
            day = int(m.group(2))
            yr = m.group(3)
        year = int(yr) if yr else now.year
        d = self._safe(year, mon, day)
        if d is None:
            return None
        if not yr and self.nf and d.date() < now.date():
            d2 = self._safe(year + 1, mon, day)
            if d2 is not None:
                d = d2
        return d, m.span(), False, False, None

    def _numeric_date(self, low, now):
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", low)
        if m:
            d = self._safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d is not None:
                return d, m.span(), False, False, None
        # MM/DD[/YYYY] (US month-first)
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
        if m:
            mo = int(m.group(1))
            day = int(m.group(2))
            yr = m.group(3)
            if 1 <= mo <= 12:
                year = int(yr) if yr else now.year
                if year < 100:
                    year += 2000
                d = self._safe(year, mo, day)
                if d is not None:
                    if not yr and self.nf and d.date() < now.date():
                        d2 = self._safe(year + 1, mo, day)
                        if d2 is not None:
                            d = d2
                    return d, m.span(), False, False, None
        return None

    _SEASONS = {
        "spring": (3, 1, 5, 31),
        "summer": (6, 1, 8, 31),
        "fall": (9, 1, 11, 30),
        "autumn": (9, 1, 11, 30),
        "winter": (12, 1, 2, 28),
    }

    def _season(self, low, now):
        """«in spring/summer/fall/autumn/winter» → fuzzy-период сезона (паритет с RU).
        Winter пересекает год. Прошедший сезон → следующий год (nearest-future)."""
        m = re.search(r"\b(?:in\s+)?(spring|summer|fall|autumn|winter)\b", low)
        if not m:
            return None
        sm, sd, em, ed = self._SEASONS[m.group(1)]
        y = now.year
        winter = sm == 12
        ey = y + 1 if winter else y
        s = datetime(y, sm, sd)
        e = datetime(ey, em, ed, 23, 59)
        if self.nf and e < now:
            s = datetime(y + 1, sm, sd)
            e = datetime(ey + 1, em, ed, 23, 59)
        return s, m.span(), True, True, e

    # ── time ────────────────────────────────────────────────────────────
    def _time(self, low, now):
        if re.search(r"\bnoon\b", low):
            m = re.search(r"\bnoon\b", low)
            return (12, 0, m.span(), True)
        if re.search(r"\bmidnight\b", low):
            m = re.search(r"\bmidnight\b", low)
            return (0, 0, m.span(), True)
        # daypart
        m = re.search(r"\b(?:in\s+the\s+)?(morning|afternoon|evening|night|tonight)\b", low)
        dp = m
        # at H[:MM][ ]?[am|pm]
        m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
        if m:
            h = int(m.group(1))
            mm = int(m.group(2) or 0)
            ap = m.group(3)
            if not (1 <= h <= 12 and 0 <= mm <= 59):
                return None  # «at 25pm» — не время; не сваливаемся в слабые паттерны
            if ap == "pm" and h != 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            return (h, mm, m.span(), True)
        # at H:MM (24h)
        m = re.search(r"\bat\s+(\d{1,2}):(\d{2})\b", low)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= h <= 23 and 0 <= mm <= 59):
                return None  # «at 12:60» — опечатка; честнее None, чем 12:00
            return (h, mm, m.span(), True)
        # standalone H:MM
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", low)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= h <= 23 and 0 <= mm <= 59):
                return None
            return (h, mm, m.span(), True)
        # at H (bare hour) — only with explicit "at"
        m = re.search(r"\bat\s+(\d{1,2})\b", low)
        if m:
            h = int(m.group(1))
            if not (0 <= h <= 23):
                return None
            if self.nf and 1 <= h <= 7:
                h += 12
            return (h, 0, m.span(), True)
        if dp:
            s, e = DAYPARTS[dp.group(1)]
            return (s, 0, dp.span(), (s, e))
        return None

    # ── ranges ──────────────────────────────────────────────────────────
    def _range(self, low, now):
        # between H and H
        m = re.search(
            r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            low,
        )
        if not m:
            # from H to H / H to H / H-H with am/pm
            m = re.search(
                r"\b(?:from\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-|–)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                low,
            )
            if not m:
                return None
        h1 = int(m.group(1))
        m1 = int(m.group(2) or 0)
        ap1 = m.group(3)
        h2 = int(m.group(4))
        m2 = int(m.group(5) or 0)
        ap2 = m.group(6)
        h1 = self._ap(h1, ap1)
        h2 = self._ap(h2, ap2)
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
            return None
        # «9 to 5» (ранний старт) без am/pm: конец < старта и ≤7 → PM (17:00).
        # Поздний старт (≥18), напр. «23 to 1» → НЕ PM, а овернайт (+1 день ниже).
        if ap1 is None and ap2 is None and h2 < h1 and h2 <= 7 and h1 < 18:
            h2 += 12
        # если конец без am/pm, а начало pm и конец меньше — тянем в тот же смысл
        s = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        e = now.replace(hour=h2 % 24, minute=m2, second=0, microsecond=0)
        if self.nf and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD, date_from=s, date_to=e, has_time=True, confidence=0.9
        )
        dt.is_explicit_range = True
        return dt, m.span()

    def _ap(self, h, ap):
        if ap == "pm" and h != 12:
            return h + 12
        if ap == "am" and h == 12:
            return 0
        return h

    # ── recurrence ──────────────────────────────────────────────────────
    def _recurrence(self, low, now):
        rec, span = self._recurrence_base(low, now)
        if rec is None:
            return None, None
        span = self._apply_recur_mods(rec, low, now, span)
        return rec, span

    def _apply_recur_mods(self, rec, low, now, span):
        s0, e0 = span
        # UNTIL: end of <period-word> | end of <month-name> | <date>
        m = re.search(
            r"\buntil\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+|next\s+)?(day|week|month|year|quarter)\b",
            low,
        )
        if m:
            _, e_full = self._period_bounds(m.group(1), now)
            rec.until = e_full
            s0, e0 = min(s0, m.start()), max(e0, m.end())
        else:
            m = re.search(r"\buntil\s+(?:the\s+)?end\s+of\s+(" + _MON + r")\b", low)
            if m:
                mon = MONTHS[m.group(1)]
                year = now.year
                last = monthrange(year, mon)[1]
                e_full = datetime(year, mon, last, 23, 59)
                if self.nf and e_full < now:
                    last = monthrange(year + 1, mon)[1]
                    e_full = datetime(year + 1, mon, last, 23, 59)
                rec.until = e_full
                s0, e0 = min(s0, m.start()), max(e0, m.end())
            else:
                # until <MONTH> без дня («until December») → конец этого месяца
                mm = re.search(r"\buntil\s+(" + _MON + r")\b(?!\s+\d)", low)
                if mm:
                    mon = MONTHS[mm.group(1)]
                    year = now.year
                    last = monthrange(year, mon)[1]
                    e_full = datetime(year, mon, last, 23, 59)
                    if self.nf and e_full < now:
                        last = monthrange(year + 1, mon)[1]
                        e_full = datetime(year + 1, mon, last, 23, 59)
                    rec.until = e_full
                    s0, e0 = min(s0, mm.start()), max(e0, mm.end())
                else:
                    m = re.search(r"\buntil\s+", low)
                    if m:
                        dres = self._date(low[m.end() :], now)
                        if dres is not None:
                            rec.until = dres[0].replace(hour=23, minute=59)
                            s0, e0 = min(s0, m.start()), max(e0, m.end() + dres[1][1])
        # COUNT: "N times"
        m = re.search(r"\b(\d+)\s+(?:times|occurrences|occurrence)\b", low)
        if m:
            rec.count = int(m.group(1))
            s0, e0 = min(s0, m.start()), max(e0, m.end())
        # EXCEPT: consume ТОЛЬКО перечисление дней/выходных после except (не title)
        m = re.search(r"\b(?:except|excluding|but not)\s+", low)
        if m and rec.frequency == "DAILY":
            tail = low[m.end() :]
            scan = re.match(r"((?:(?:weekends?|" + _WD + r")(?:\s*(?:,|and)\s*)?)+)", tail)
            if scan:
                seg = scan.group(1)
                excl = set()
                if re.search(r"weekends?", seg):
                    excl |= {5, 6}
                for wm in re.finditer(_WD, seg):
                    excl.add(WEEKDAYS[wm.group(0)])
                if excl:
                    keep = [i for i in range(7) if i not in excl]
                    rec.frequency = "WEEKLY"
                    rec.by_day = [RRULE_DAYS[i] for i in keep]
                    s0, e0 = min(s0, m.start()), max(e0, m.end() + scan.end())
        return (s0, e0)

    def _has_specific_recurrence(self, low):
        """Более специфичный маркер every, который должен победить одиночный
        adverb daily/weekly/... стоящий в названии задачи ('run weekly planning')."""
        return bool(
            re.search(r"\bevery\s+(" + _WD + r")\b", low)
            or re.search(
                r"\bevery\s+(\d+|two|three|four|other)\s+"
                r"(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months)\b",
                low,
            )
            or re.search(r"\bevery\s+other\b", low)
            or re.search(r"\bevery\s+(?:week\s?day|business\s+day)\b", low)
            or re.search(r"\bon\s+week\s?days\b", low)
            or re.search(r"\b(?:on\s+weekends?|every\s+weekend)\b", low)
            or re.search(r"\bevery\s+month\s+on\s+the\b", low)
        )

    def _recurrence_base(self, low, now):
        # daily/weekly/monthly/yearly adverbs
        # adverb-маркер уступает более специфичному every-паттерну: в
        # «every Monday ... run weekly planning» слово weekly — часть title.
        m = re.search(r"\b(daily|weekly|monthly|yearly)\b", low)
        if m and not self._has_specific_recurrence(low):
            fm = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY", "yearly": "YEARLY"}
            return RecurrenceRule(frequency=fm[m.group(1)]), m.span()
        # every weekday / on weekdays / every business day
        m = re.search(r"\b(?:every\s+(?:week\s?day|business\s+day)|on\s+week\s?days)\b", low)
        if m:
            return RecurrenceRule(frequency="WEEKLY", by_day=RRULE_DAYS[:5]), m.span()
        # on weekends / every weekend → сб+вс
        m = re.search(r"\b(?:on\s+weekends?|every\s+weekend)\b", low)
        if m:
            return RecurrenceRule(frequency="WEEKLY", by_day=["SA", "SU"]), m.span()
        # every other week/day/month
        m = re.search(r"\bevery\s+other\s+(day|week|month)\b", low)
        if m:
            fm = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY"}
            return RecurrenceRule(frequency=fm[m.group(1)], interval=2), m.span()
        # every month on the Nth  |  on the Nth of every month
        m = re.search(
            r"\bevery\s+month\s+on\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", low
        ) or re.search(
            r"\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(?:every|each)\s+month\b", low
        )
        if m:
            return RecurrenceRule(frequency="MONTHLY", by_month_day=[int(m.group(1))]), m.span()
        # every N days/weeks/months [on <weekday>]
        m = re.search(
            r"\bevery\s+(\d+|two|three|four|other)\s+(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months)\b",
            low,
        )
        if m:
            n = {"two": 2, "three": 3, "four": 4, "other": 2}.get(m.group(1))
            n = n if n else int(m.group(1))
            unit = {
                "minute": "MINUTELY",
                "minutes": "MINUTELY",
                "min": "MINUTELY",
                "hour": "HOURLY",
                "hours": "HOURLY",
                "hr": "HOURLY",
                "day": "DAILY",
                "days": "DAILY",
                "week": "WEEKLY",
                "weeks": "WEEKLY",
                "month": "MONTHLY",
                "months": "MONTHLY",
            }[m.group(2)]
            rec = RecurrenceRule(frequency=unit, interval=n)
            end = m.end()
            # on <weekday>[s] после every N недель («every 2 weeks on Mondays»);
            # допускаем мн.ч. и нормализуем перед поиском в WEEKDAYS
            wm = re.search(r"\bon\s+(" + _WD + r")s?\b", low[m.end() :])
            if wm:
                wd_key = wm.group(1).rstrip("s") if wm.group(1) not in WEEKDAYS else wm.group(1)
                if wd_key in WEEKDAYS:
                    rec.by_day = [RRULE_DAYS[WEEKDAYS[wd_key]]]
                    end = m.end() + wm.end()
            return rec, (m.start(), end)
        # every <weekday>
        m = re.search(r"\bevery\s+(" + _WD + r")\b", low)
        if m:
            return (
                RecurrenceRule(frequency="WEEKLY", by_day=[RRULE_DAYS[WEEKDAYS[m.group(1)]]]),
                m.span(),
            )
        # every day/week/month/year
        m = re.search(r"\bevery\s+(day|week|month|year)\b", low)
        if m:
            fm = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}
            return RecurrenceRule(frequency=fm[m.group(1)]), m.span()
        return None, None

    def _recurrence_dtstart(self, rec, base, now, has_time):
        if rec.by_day:
            wds = sorted(RRULE_DAYS.index(d) for d in rec.by_day)
            best = None
            for wd in wds:
                delta = (wd - now.weekday()) % 7
                cand = base + timedelta(days=delta)
                if has_time and delta == 0 and cand <= now:
                    cand += timedelta(days=7)
                if best is None or cand < best:
                    best = cand
            return best
        if has_time and base <= now:
            return base + timedelta(days=1)
        return base

    # ── deadline ────────────────────────────────────────────────────────
    def _deadline(self, low, now):
        m = re.search(
            r"\b(by|before|due)\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?(day|week|month|year|quarter)\b",
            low,
        )
        if m:
            _, e_full = self._period_bounds(m.group(2), now)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e_full,
                has_time=False,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        # by end of <named month>: «by end of March» → 31.03 23:59
        # (паритет с RU «до конца марта»; прошедший месяц → следующий год)
        m = re.search(r"\b(by|before|due)\s+(?:the\s+)?end\s+of\s+(" + _MON + r")\b", low)
        if m:
            mon = MONTHS[m.group(2)[:3] if m.group(2)[:3] in MONTHS else m.group(2)]
            y = now.year
            e = datetime(y, mon, monthrange(y, mon)[1], 23, 59)
            if e < now:
                y += 1
                e = datetime(y, mon, monthrange(y, mon)[1], 23, 59)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e,
                has_time=False,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        # by/before/due <time>
        m = re.search(r"\b(by|before|due)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if re.search(r"\b(by|before|due)\s+noon\b", low):
            mm = re.search(r"\b(by|before|due)\s+noon\b", low)
            e = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if self.nf and e < now:
                e += timedelta(days=1)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=e,
                    has_time=True,
                    is_deadline=True,
                    confidence=0.85,
                ),
                mm.span(),
            )
        # by <weekday|date>
        dm = re.search(
            r"\b(by|before|due)\s+(next|this)?\s*("
            + _WD
            + r"|"
            + _MON
            + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
            low,
        )
        if dm:
            sub = dm.group(0)
            # переиспользуем _date на «хвосте» после by/before/due
            tail = sub.split(None, 1)[1] if " " in sub else sub
            dres = self._date(tail, now)
            if dres is not None:
                d = dres[0]
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=d.replace(hour=23, minute=59),
                    has_time=False,
                    is_deadline=True,
                    confidence=0.85,
                )
                return dt, dm.span()
        if m:
            h = int(m.group(2))
            mn = int(m.group(3) or 0)
            ap = m.group(4)
            # Валидация: с am/pm 1..12, иначе 0..23; минуты 0..59. «by 25:00» → None.
            if ap is not None:
                if not (1 <= h <= 12 and 0 <= mn <= 59):
                    return None
            elif not (0 <= h <= 23 and 0 <= mn <= 59):
                return None
            h = self._ap(h, ap)
            if ap is None and self.nf and 1 <= h <= 7:
                h += 12
            e = now.replace(hour=h % 24, minute=mn, second=0, microsecond=0)
            if self.nf and e < now:
                e += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e,
                has_time=True,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        return None

    # ── relative / duration ───────────────────────────────────────────────
    def _relative(self, low, now):
        _UNITS = r"(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months|year|years)"
        _NUMS = r"(\d+(?:\.\d+)?|a|an|half\s+an?|one|two|three|four|five|six|seven|eight|nine|ten)"

        def _num(w):
            if w in ("a", "an"):
                return 1
            if w.startswith("half"):
                return 0.5
            if re.match(r"^\d+\.\d+$", w):
                return float(w)
            v = NUM_WORDS.get(w)
            return v if v is not None else int(w)

        # «in X and a half <unit>»: in two and a half hours → 2.5
        m = re.search(r"\bin\s+" + _NUMS + r"\s+and\s+a\s+half\s+" + _UNITS + r"\b", low)
        if m:
            n = _num(m.group(1)) + 0.5
            unit = m.group(2)
        else:
            # «in an <unit> and a half»: in an hour and a half → 1.5
            m = re.search(r"\bin\s+an?\s+(minute|hour|day|week|month|year)\s+and\s+a\s+half\b", low)
            if m:
                n = 1.5
                unit = m.group(1)
            else:
                m = re.search(r"\bin\s+" + _NUMS + r"\s+" + _UNITS + r"\b", low)
                if not m:
                    return None
                n = _num(m.group(1))
                unit = m.group(2)
        try:
            if unit.startswith(("minute", "min")):
                target = now + timedelta(minutes=n)
                ht = True
            elif unit.startswith(("hour", "hr")):
                target = now + timedelta(hours=n)
                ht = True
            elif unit.startswith("day"):
                target = now + timedelta(days=n)
                ht = False
            elif unit.startswith("week"):
                target = now + timedelta(weeks=n)
                ht = False
            elif unit.startswith("month"):
                # дробные месяцы: целая часть календарно, половина ≈ 15 дней
                # (паритет с RU «через полтора месяца»)
                target = self._add_months(now, int(n))
                if n != int(n):
                    target += timedelta(days=15)
                ht = False
            else:
                target = self._add_months(now, int(n * 12))
                ht = False
        except (ValueError, OverflowError):
            # «in 999999999 years» — за пределами datetime; честный ответ None
            return None
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=ht,
            all_day=not ht,
            confidence=0.9,
        )
        return dt, m.span()

    def _duration(self, low):
        m = re.search(
            r"\bfor\s+(\d+|half\s+an?|an?|one|two|three|four|five|six)\s+(hour|hours|hr|minute|minutes|min)\b",
            low,
        )
        if not m:
            return None
        w = m.group(1)
        if w.startswith("half"):
            n = 0.5
        else:
            n = NUM_WORDS.get(w)
            n = n if n is not None else int(w)
        if m.group(2).startswith(("hour", "hr")):
            return int(n * 60)
        return int(n)

    # ── helpers ───────────────────────────────────────────────────────────
    def _safe(self, y, mo, d):
        try:
            return datetime(y, mo, d, 0, 0, 0)
        except ValueError:
            return None

    def _add_months(self, dt, months):
        m = dt.month - 1 + months
        y = dt.year + m // 12
        m = m % 12 + 1
        d = min(dt.day, monthrange(y, m)[1])
        return dt.replace(year=y, month=m, day=d)

    def _period_bounds(self, unit, now):
        if unit == "day":
            s = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return s, s.replace(hour=23, minute=59)
        if unit == "week":
            mon = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return mon, (mon + timedelta(days=6)).replace(hour=23, minute=59)
        if unit == "month":
            last = monthrange(now.year, now.month)[1]
            return datetime(now.year, now.month, 1), datetime(now.year, now.month, last, 23, 59)
        if unit == "quarter":
            q = (now.month - 1) // 3
            m1 = q * 3 + 1
            m2 = m1 + 2
            return datetime(now.year, m1, 1), datetime(
                now.year, m2, monthrange(now.year, m2)[1], 23, 59
            )
        return datetime(now.year, 1, 1), datetime(now.year, 12, 31, 23, 59)

    def _part_window(self, unit, part, s_full, e_full):
        pad = 1 if unit == "week" else (4 if unit == "month" else 9)
        if part == "start":
            return s_full, (s_full + timedelta(days=pad)).replace(hour=23, minute=59)
        if part == "end":
            return (e_full - timedelta(days=pad)).replace(hour=0, minute=0), e_full
        mid = s_full + (e_full - s_full) / 2
        return (
            (mid - timedelta(days=pad)).replace(hour=0, minute=0),
            (mid + timedelta(days=pad)).replace(hour=23, minute=59),
        )

    def _title(self, text, spans):
        chars = list(text)
        for s, e in spans:
            for k in range(s, min(e, len(chars))):
                chars[k] = " "
        raw = "".join(chars)
        words = re.findall(r"[A-Za-z][A-Za-z']*", raw)
        temporal = (
            "today",
            "tomorrow",
            "tonight",
            "yesterday",
            "noon",
            "midnight",
            "morning",
            "afternoon",
            "evening",
            "night",
            "am",
            "pm",
            "week",
            "month",
            "year",
            "day",
            "days",
            "hours",
            "hour",
            "minutes",
            "minute",
            "weekday",
            "weekdays",
            "daily",
            "weekly",
            "monthly",
            "yearly",
            "st",
            "nd",
            "rd",
            "th",
            "other",
            "end",
            "beginning",
            "middle",
            "mid",
        )
        kept = []
        filler_only = []
        for w in words:
            lw = w.lower()
            if lw in WEEKDAYS or lw in MONTHS or lw in temporal:
                continue  # временны́е слова — никогда не title
            if lw in _FILLER:
                filler_only.append(w)  # команда/предлог — по возможности убираем
                continue
            kept.append(w)
        title = " ".join(kept).strip()
        if not title and filler_only:
            # если после удаления времени осталось только «reminder/meeting» — сохраняем
            title = " ".join(filler_only).strip()
        return title

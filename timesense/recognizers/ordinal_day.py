"""Распознавание порядковых дней: первый понедельник месяца, последняя суббота каждого месяца"""

from datetime import datetime, timedelta
from calendar import monthrange
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule
from ..dict.keywords import Keywords


class OrdinalDayRecognizer(Recognizer):
    """Распознаёт:
    - первый вторник месяца → конкретная дата (одноразово)
    - последняя суббота каждого месяца → recurrence MONTHLY;BYDAY=-1SA
    - первый вторник каждого января → recurrence YEARLY;BYMONTH=1;BYDAY=1TU
    - первый вторник января → конкретная дата (одноразово)
    + опциональное время ("в 10") или диапазон ("9-10", "с 9 до 11")
    """

    ORDINAL_MAP = {}
    for w in Keywords.ORDINAL_FIRST:
        ORDINAL_MAP[w] = 1
    for w in Keywords.ORDINAL_SECOND:
        ORDINAL_MAP[w] = 2
    for w in Keywords.ORDINAL_THIRD:
        ORDINAL_MAP[w] = 3
    for w in Keywords.ORDINAL_FOURTH:
        ORDINAL_MAP[w] = 4
    for w in Keywords.ORDINAL_LAST:
        ORDINAL_MAP[w] = -1
    for w in ("предпоследний", "предпоследняя", "предпоследнее", "предпоследнюю", "предпоследнего"):
        ORDINAL_MAP[w] = -2

    MONTH_WORDS_TO_NUM = {}
    for mi, mwords in enumerate(Keywords.months()):
        for mw in mwords:
            MONTH_WORDS_TO_NUM[mw] = mi + 1

    EVERY_WORDS = set(Keywords.EVERY)

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_after_day(tokens, i, now)
                or self._try_before_month_end(tokens, i, now)
                or self._try_month_position(tokens, i, now)
                or self._try_ordinal_weekday(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _is_working(self, d):
        """Рабочий день с учётом производственного календаря (если задан)."""
        cal = getattr(self.config, "calendar", None)
        if cal is not None:
            return cal.is_working_day(d)
        return d.weekday() < 5

    def _kind_at(self, tokens, si):
        """→ (kind, wd, next_index) для «<день недели>» или «рабочий/будний день»."""
        wd = self._parse_weekday(tokens[si])
        if wd is not None:
            return ("weekday", wd, si + 1)
        v = tokens[si].value.lower()
        n = tokens[si].normalized
        if n in ("рабочий", "будний") or v in ("рабочий", "рабочего", "будний", "будни"):
            ci = si + 1
            if ci < len(tokens) and (
                tokens[ci].normalized == "день" or tokens[ci].value.lower() in ("день", "дня")
            ):
                ci += 1
            return ("business", None, ci)
        return (None, None, si)

    def _try_after_day(self, tokens, i, now):
        """[первый] <день недели|рабочий день> после N числа → первый такой день > N."""
        from calendar import monthrange

        si = i
        if tokens[si].value.lower() in ("в", "во", "на"):
            si += 1
        if si < len(tokens) and self._ORD_POS.get(tokens[si].value.lower()) == 1:
            si += 1  # опциональное «первый»
        if si >= len(tokens):
            return None
        kind, wd, ci = self._kind_at(tokens, si)
        if kind is None:
            return None
        if ci >= len(tokens) or tokens[ci].value.lower() != "после":
            return None
        if ci + 1 >= len(tokens) or not tokens[ci + 1].value.isdigit():
            return None
        n = int(tokens[ci + 1].value)
        if not (1 <= n <= 31):
            return None
        end_i = ci + 1
        if ci + 2 < len(tokens) and (
            tokens[ci + 2].normalized == "число"
            or tokens[ci + 2].value.lower() in ("число", "числа")
        ):
            end_i = ci + 2

        def compute(year, month):
            dim = monthrange(year, month)[1]
            for d in range(n + 1, dim + 1):
                dt = datetime(year, month, d)
                if (kind == "weekday" and dt.weekday() == wd) or (
                    kind == "business" and self._is_working(dt)
                ):
                    return dt
            return None

        target = compute(now.year, now.month)
        if target is None or target.date() < now.date():
            mo2 = now.month + 1
            y2 = now.year + (1 if mo2 > 12 else 0)
            mo2 = (mo2 - 1) % 12 + 1
            t2 = compute(y2, mo2)
            if t2 is not None:
                target = t2
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=target,
            date_to=target.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            start=tokens[i].start,
            end=tokens[end_i].end,
            confidence=0.9,
        )
        return (dt, end_i - i + 1)

    def _try_before_month_end(self, tokens, i, now):
        """последняя <день недели|рабочий день> перед концом месяца → последний такой день."""
        from calendar import monthrange

        si = i
        if tokens[si].value.lower() in ("в", "во", "на"):
            si += 1
        if si < len(tokens) and self._ORD_POS.get(tokens[si].value.lower()) == -1:
            si += 1  # опциональное «последний/последняя»
        if si >= len(tokens):
            return None
        kind, wd, ci = self._kind_at(tokens, si)
        if kind is None:
            return None
        # «перед концом месяца»
        if ci >= len(tokens) or tokens[ci].value.lower() != "перед":
            return None
        j = ci + 1
        if j >= len(tokens) or tokens[j].value.lower() not in ("концом", "конца", "конец"):
            return None
        end_i = j
        if j + 1 < len(tokens) and (
            tokens[j + 1].normalized in Keywords.MONTH
            or tokens[j + 1].value.lower() in ("месяца", "месяце", "месяц")
        ):
            end_i = j + 1

        def compute(year, month):
            dim = monthrange(year, month)[1]
            for d in range(dim, 0, -1):
                dt = datetime(year, month, d)
                if (kind == "weekday" and dt.weekday() == wd) or (
                    kind == "business" and self._is_working(dt)
                ):
                    return dt
            return None

        target = compute(now.year, now.month)
        if target is None or target.date() < now.date():
            mo2 = now.month + 1
            y2 = now.year + (1 if mo2 > 12 else 0)
            mo2 = (mo2 - 1) % 12 + 1
            t2 = compute(y2, mo2)
            if t2 is not None:
                target = t2
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=target,
            date_to=target.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            start=tokens[i].start,
            end=tokens[end_i].end,
            confidence=0.9,
        )
        return (dt, end_i - i + 1)

    _ORD_POS = {}
    for _w in ("первый", "первая", "первое", "первые", "первым", "первую", "первого"):
        _ORD_POS[_w] = 1
    for _w in ("последний", "последняя", "последнее", "последние", "последнюю", "последнего"):
        _ORD_POS[_w] = -1
    for _w in ("предпоследний", "предпоследняя", "предпоследнее", "предпоследние", "предпоследнюю"):
        _ORD_POS[_w] = -2

    def _try_month_position(self, tokens, i, now):
        """первый/последний рабочий день месяца, первые/последние выходные месяца,
        первая/последняя неделя месяца (+ «каждый …» → MONTHLY с BYSETPOS)."""
        si = i
        every = False
        if tokens[si].value.lower() in ("в", "во", "на"):
            si += 1
        if si < len(tokens) and tokens[si].value.lower() in self.EVERY_WORDS:
            every = True
            si += 1
        if si >= len(tokens):
            return None
        pos = self._ORD_POS.get(tokens[si].value.lower()) or self._ORD_POS.get(
            tokens[si].normalized
        )
        if pos is None:
            return None
        j = si + 1
        if j >= len(tokens):
            return None
        jv = tokens[j].value.lower()
        jn = tokens[j].normalized
        kind = None
        end_i = j
        # рабочий/будний день
        if jn in ("рабочий", "будний") or jv in ("рабочий", "рабочего", "будний", "будни"):
            kind = "business"
            end_i = j
            if j + 1 < len(tokens) and (
                tokens[j + 1].normalized == "день" or tokens[j + 1].value.lower() in ("день", "дня")
            ):
                end_i = j + 1
        elif jn == "выходной" or jv in ("выходные", "выходной", "выходных", "выходным"):
            kind = "weekend"
            end_i = j
        elif jn == "неделя" or jv in ("неделя", "неделю", "недели", "неделе"):
            kind = "week"
            end_i = j
        if kind is None:
            return None
        # опциональное «месяца»
        if end_i + 1 < len(tokens) and (
            tokens[end_i + 1].normalized in Keywords.MONTH
            or tokens[end_i + 1].value.lower() in ("месяца", "месяце", "месяц")
        ):
            end_i += 1
        return self._build_month_position(kind, pos, every, tokens, i, end_i, now)

    def _build_month_position(self, kind, pos, every, tokens, i, end_i, now):
        from calendar import monthrange

        def in_month(year, month):
            dim = monthrange(year, month)[1]
            if kind == "business":
                days = [d for d in range(1, dim + 1) if self._is_working(datetime(year, month, d))]
            elif kind == "weekend":
                days = [
                    d for d in range(1, dim + 1) if datetime(year, month, d).weekday() == 5
                ]  # субботы
            else:
                days = None
            return days, dim

        y, mo = now.year, now.month

        def compute(year, month):
            days, dim = in_month(year, month)
            if kind == "week":
                if pos == 1:
                    s = datetime(year, month, 1)
                    e = datetime(year, month, min(7, dim), 23, 59)
                else:
                    s = datetime(year, month, max(1, dim - 6))
                    e = datetime(year, month, dim, 23, 59)
                return s, e
            idx = pos - 1 if pos > 0 else len(days) + pos
            if not (0 <= idx < len(days)):
                return None, None
            d0 = days[idx]
            if kind == "business":
                s = datetime(year, month, d0)
                e = s.replace(hour=23, minute=59)
            else:  # weekend: суббота + воскресенье
                s = datetime(year, month, d0)
                e = (s + timedelta(days=1)).replace(hour=23, minute=59)
            return s, e

        s, e = compute(y, mo)
        # если уже прошло — следующий месяц
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
            if kind == "business":
                rec = RecurrenceRule(
                    frequency="MONTHLY", by_day=["MO", "TU", "WE", "TH", "FR"], by_set_pos=pos
                )
            elif kind == "weekend":
                rec = RecurrenceRule(frequency="MONTHLY", by_day=["SA", "SU"], by_set_pos=pos)
            else:  # week — повторение «первая/последняя неделя» задаём как MONTHLY BYMONTHDAY
                rec = RecurrenceRule(frequency="MONTHLY")
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=False,
            all_day=True,
            recurrence=rec,
            start=tokens[i].start,
            end=tokens[end_i].end,
            confidence=0.9,
        )
        dt.is_explicit_range = kind in ("weekend", "week")
        return (dt, end_i - i + 1)

    def _try_ordinal_weekday(self, tokens, i, now):
        si = i
        has_every_before = False
        # Необязательный предлог "в"/"во"/"на"
        if tokens[i].value.lower() in ["в", "во", "на"]:
            si = i + 1
        # Проверяем "каждый" / "каждую" перед ordinal
        if si < len(tokens) and tokens[si].value.lower() in self.EVERY_WORDS:
            has_every_before = True
            si += 1
        if si >= len(tokens):
            return None

        # 1. Ordinal
        ordinal = self._parse_ordinal(tokens[si])
        if ordinal is None:
            return None

        # 1b. «(каждый) последний день [месяца]» → MONTHLY;BYMONTHDAY=-1
        if ordinal == -1 and si + 1 < len(tokens):
            dv = tokens[si + 1].value.lower()
            dn = tokens[si + 1].normalized
            if dn == "день" or dv in ("день", "дня"):
                ci = si + 2
                if ci < len(tokens) and (
                    tokens[ci].normalized in Keywords.MONTH
                    or tokens[ci].value.lower() in ["месяц", "месяца", "месяцев"]
                ):
                    ci += 1
                last = monthrange(now.year, now.month)[1]
                target = now.replace(day=last, hour=0, minute=0, second=0, microsecond=0)
                rec = (
                    RecurrenceRule(frequency="MONTHLY", by_month_day=[-1])
                    if has_every_before
                    else None
                )
                ei = ci - 1
                time_r = self._find_time(tokens, ci, now)
                if time_r:
                    h, m, tei = time_r
                    target = target.replace(hour=h, minute=m)
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=target,
                        date_to=target,
                        has_time=True,
                        recurrence=rec,
                        start=tokens[i].start,
                        end=tokens[tei].end,
                        confidence=0.95,
                    )
                    return (dt, tei - i + 1)
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD if rec else DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=tokens[max(i, ei)].end,
                    confidence=0.9,
                )
                return (dt, max(1, ei - i + 1))

        # 2. Weekday
        if si + 1 >= len(tokens):
            return None
        weekday = self._parse_weekday(tokens[si + 1])
        if weekday is None:
            return None

        ci = si + 2
        has_recurrence = has_every_before
        month_num = None

        # 3. Ищем "месяца"/"каждого месяца"/"каждого января"/month_name
        if ci < len(tokens):
            tv = tokens[ci].value.lower()
            tn = tokens[ci].normalized

            if tv in self.EVERY_WORDS:
                has_recurrence = True
                if ci + 1 < len(tokens):
                    nv = tokens[ci + 1].value.lower()
                    nn = tokens[ci + 1].normalized
                    if nn in Keywords.MONTH or nv in ["месяц", "месяца", "месяцев"]:
                        ci += 2
                    elif nv in self.MONTH_WORDS_TO_NUM:
                        month_num = self.MONTH_WORDS_TO_NUM[nv]
                        ci += 2
                    else:
                        ci += 1
                else:
                    ci += 1
            elif tn in Keywords.MONTH or tv in ["месяц", "месяца", "месяцев"]:
                ci += 1
            elif tv in self.MONTH_WORDS_TO_NUM:
                month_num = self.MONTH_WORDS_TO_NUM[tv]
                ci += 1

        # 4. Определяем rrule
        rrule_day = Keywords.RRULE_DAYS[weekday]
        ordinal_day = f"{ordinal}{rrule_day}"

        recurrence = None
        if has_recurrence:
            if month_num:
                recurrence = RecurrenceRule(
                    frequency="YEARLY", by_day=[ordinal_day], by_month=[month_num]
                )
            else:
                recurrence = RecurrenceRule(frequency="MONTHLY", by_day=[ordinal_day])

        # 5. Вычисляем конкретную дату
        target_date = self._compute_ordinal_weekday_date(ordinal, weekday, month_num, now)

        # 6. Ищем время или диапазон
        ei = ci - 1
        range_r = self._find_range(tokens, ci, now)
        time_r = self._find_time(tokens, ci, now)

        if range_r:
            sh, sm, eh, em, range_ei = range_r
            target_start = target_date.replace(hour=sh, minute=sm)
            target_end = target_date.replace(hour=eh, minute=em)
            if target_end <= target_start:
                target_end += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=target_start,
                date_to=target_end,
                has_time=True,
                recurrence=recurrence,
                start=tokens[i].start,
                end=tokens[range_ei].end,
                confidence=0.95,
            )
            dt.is_explicit_range = True
            return (dt, range_ei - i + 1)
        elif time_r:
            h, m, time_ei = time_r
            target_date = target_date.replace(hour=h, minute=m)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=target_date,
                date_to=target_date,
                has_time=True,
                recurrence=recurrence,
                start=tokens[i].start,
                end=tokens[time_ei].end,
                confidence=0.95,
            )
            return (dt, time_ei - i + 1)
        else:
            dt = DateTimeToken(
                type=DateTimeType.FIXED if not recurrence else DateTimeType.PERIOD,
                date_from=target_date,
                date_to=target_date.replace(hour=23, minute=59),
                has_time=False,
                all_day=True,
                recurrence=recurrence,
                start=tokens[i].start,
                end=tokens[max(i, ei)].end,
                confidence=0.9,
            )
            return (dt, max(1, ei - i + 1))

    def _parse_ordinal(self, token):
        v = token.value.lower()
        n = token.normalized
        if v in self.ORDINAL_MAP:
            return self.ORDINAL_MAP[v]
        if n in self.ORDINAL_MAP:
            return self.ORDINAL_MAP[n]
        m = re.match(r"^(\d+)-[йяе]$", v)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 5:
                return num
        return None

    def _parse_weekday(self, token):
        v = token.value.lower()
        n = token.normalized
        for wi, days in enumerate(Keywords.days_of_week()):
            if v in days or n in days:
                return wi
        return None

    def _compute_ordinal_weekday_date(self, ordinal, weekday, month_num, now):
        if month_num:
            year = now.year
            if month_num < now.month:
                year += 1
            elif month_num == now.month:
                candidate = self._nth_weekday_of_month(year, month_num, weekday, ordinal)
                if candidate and candidate.date() < now.date():
                    year += 1
            return self._nth_weekday_of_month(year, month_num, weekday, ordinal) or now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            candidate = self._nth_weekday_of_month(now.year, now.month, weekday, ordinal)
            if candidate and candidate.date() >= now.date():
                return candidate
            next_month = now.month + 1
            next_year = now.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            return self._nth_weekday_of_month(
                next_year, next_month, weekday, ordinal
            ) or now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _nth_weekday_of_month(self, year, month, weekday, ordinal):
        _, days_in_month = monthrange(year, month)
        matches = [
            d for d in range(1, days_in_month + 1) if datetime(year, month, d).weekday() == weekday
        ]
        if not matches:
            return None
        if ordinal < 0:
            idx = len(matches) + ordinal  # -1 → последний, -2 → предпоследний
            if 0 <= idx < len(matches):
                return datetime(year, month, matches[idx], 0, 0, 0)
            return None
        if 1 <= ordinal <= len(matches):
            return datetime(year, month, matches[ordinal - 1], 0, 0, 0)
        return None

    def _find_time(self, tokens, start, now):
        for j in range(start, min(start + 4, len(tokens))):
            tn = tokens[j].normalized
            if tn in Keywords.TIME_FROM or tn in Keywords.TIME_BY:
                if j + 1 < len(tokens):
                    tt = tokens[j + 1]
                    m = re.match(r"(\d{1,2})[:.-](\d{2})", tt.value)
                    if m:
                        return (int(m.group(1)), int(m.group(2)), j + 1)
                    if tt.value.isdigit():
                        h = int(tt.value)
                        if 0 <= h <= 23:
                            if 1 <= h <= 7:
                                h += 12
                            return (h, 0, j + 1)
                    h = Keywords.parse_number_word(tt.value, self.morph)
                    if h is not None and 0 <= h <= 23:
                        if 1 <= h <= 7:
                            h += 12
                        return (h, 0, j + 1)
        return None

    def _find_range(self, tokens, start, now):
        for j in range(start, min(start + 4, len(tokens))):
            m = re.match(r"^(\d{1,2}):?(\d{2})?-(\d{1,2}):?(\d{2})?$", tokens[j].value)
            if m:
                h1 = int(m.group(1))
                m1 = int(m.group(2)) if m.group(2) else 0
                h2 = int(m.group(3))
                m2 = int(m.group(4)) if m.group(4) else 0
                if 0 <= h1 <= 23 and 0 <= h2 <= 23:
                    if 1 <= h1 <= 7:
                        h1 += 12
                    if 1 <= h2 <= 7:
                        h2 += 12
                    return (h1, m1, h2, m2, j)
            if tokens[j].value.lower() in ["с", "со"] and j + 3 < len(tokens):
                h1 = self._ptv(tokens[j + 1])
                if h1 is not None:
                    if j + 2 < len(tokens) and tokens[j + 2].normalized in Keywords.TIME_TO:
                        h2 = self._ptv(tokens[j + 3])
                        if h2 is not None:
                            if 1 <= h1 <= 7:
                                h1 += 12
                            if 1 <= h2 <= 7:
                                h2 += 12
                            return (h1, 0, h2, 0, j + 3)
        return None

    def _ptv(self, token):
        if token.value.isdigit():
            h = int(token.value)
            return h if 0 <= h <= 23 else None
        m = re.match(r"^(\d{1,2}):(\d{2})$", token.value)
        if m:
            return int(m.group(1))
        return Keywords.parse_number_word(token.value, self.morph)

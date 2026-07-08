"""Повторяющиеся события: каждый понедельник, ежедневно, раз в неделю"""

from datetime import datetime, timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule
from ..dict.keywords import Keywords


class RecurrenceRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_every(tokens, i, now)
                or self._try_by_weekdays(tokens, i, now)
                or self._try_interval(tokens, i, now)
                or self._try_adverb(tokens, i, now)
            )
            if r:
                dt0, cons = r
                if getattr(dt0, "recurrence", None) is not None:
                    add = self._scan_count_until(tokens, i + cons, dt0.recurrence, now)
                    if add > 0:
                        dt0.end = tokens[i + cons + add - 1].end  # съесть «5 раз»/«до …» в title
                        cons += add
                results.append(dt0)
                i += cons
            else:
                i += 1
        return results

    def _scan_count_until(self, tokens, s, rec, now):
        """После правила повторения ищет COUNT («5 раз») и UNTIL («до конца
        месяца», «до пятницы», «до 20 марта»). Возвращает число съеденных токенов."""
        from calendar import monthrange

        consumed = 0
        if s >= len(tokens):
            return consumed
        # COUNT: «N раз/раза»
        num, ncons = Keywords.parse_cardinal(tokens, s, self.morph)
        if num is not None and s + ncons < len(tokens):
            rw = tokens[s + ncons].value.lower()
            if rw in ("раз", "раза"):
                rec.count = num
                return ncons + 1
        # UNTIL: «до ...»
        if tokens[s].value.lower() in ("до", "по") and s + 1 < len(tokens):
            j = s + 1
            # до конца месяца / недели
            if j + 1 < len(tokens) and tokens[j].value.lower() in ("конца", "конец"):
                what = tokens[j + 1].value.lower()
                wn = tokens[j + 1].normalized
                if wn in Keywords.MONTH or what in ("месяца", "месяц"):
                    last = monthrange(now.year, now.month)[1]
                    rec.until = now.replace(day=last, hour=23, minute=59, second=0, microsecond=0)
                    return (j + 1) - s + 1
                if wn in Keywords.WEEK or what in ("недели", "неделя"):
                    end = now + timedelta(days=(6 - now.weekday()))
                    rec.until = end.replace(hour=23, minute=59, second=0, microsecond=0)
                    return (j + 1) - s + 1
            # до <день недели>
            for wi, days in enumerate(Keywords.days_of_week() + Keywords.days_of_week_dative()):
                if tokens[j].value.lower() in days or tokens[j].normalized in days:
                    delta = ((wi % 7) - now.weekday()) % 7
                    delta = delta or 7
                    end = now + timedelta(days=delta)
                    rec.until = end.replace(hour=23, minute=59, second=0, microsecond=0)
                    return j - s + 1
            # до <N> <месяц>
            dm = self._find_day_month(tokens, j)
            if dm is not None:
                d, mon, ei = dm
                y = now.year if (mon, d) >= (now.month, now.day) else now.year + 1
                try:
                    rec.until = datetime(y, mon, d, 23, 59)
                    return ei - s + 1
                except ValueError:
                    pass
        return consumed

    def _try_adverb(self, tokens, i, now):
        v = tokens[i].value.lower()
        fm = {
            "ежедневно": "DAILY",
            "еженедельно": "WEEKLY",
            "ежемесячно": "MONTHLY",
            "ежегодно": "YEARLY",
        }
        if v in fm:
            rec = RecurrenceRule(frequency=fm[v])
            date_from = now
            end_i = i
            if fm[v] == "YEARLY":
                dm = self._find_day_month(tokens, i + 1)
                if dm is not None:
                    d, mon, ei = dm
                    rec.by_month = [mon]
                    rec.by_month_day = [d]
                    date_from = self._nearest_annual(now, mon, d)
                    end_i = ei
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=date_from,
                    date_to=date_from,
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=tokens[end_i].end,
                    confidence=0.9,
                ),
                end_i - i + 1,
            )
        return None

    @staticmethod
    def _find_day_month(tokens, start):
        """Ищет «N <месяц>» или «<месяц> N» в небольшом окне → (day, month, end_index)."""
        ml = {}
        for idx, variants in enumerate(Keywords.months()):
            for v in variants:
                ml[v] = idx + 1
        for j in range(start, min(start + 6, len(tokens))):
            mon = ml.get(tokens[j].value.lower()) or ml.get(tokens[j].normalized)
            if mon:
                for k in (j - 1, j + 1):
                    if 0 <= k < len(tokens) and tokens[k].value.isdigit():
                        d = int(tokens[k].value)
                        if 1 <= d <= 31:
                            return (d, mon, max(j, k))
        return None

    @staticmethod
    def _nearest_annual(now, mon, day):
        from datetime import datetime
        from calendar import monthrange

        y = now.year
        if day > monthrange(y, mon)[1]:
            day = monthrange(y, mon)[1]
        cand = datetime(y, mon, day)
        if cand.date() < now.date():
            cand = datetime(y + 1, mon, min(day, monthrange(y + 1, mon)[1]))
        return cand

    def _try_every(self, tokens, i, now):
        if tokens[i].value.lower() not in Keywords.EVERY:
            return None
        if i + 1 >= len(tokens):
            return None
        nt = tokens[i + 1]
        nv = nt.value.lower()
        nn = nt.normalized
        # каждый <день недели>
        for wi, days in enumerate(Keywords.days_of_week()):
            if nn in days or nv in days:
                rec = RecurrenceRule(frequency="WEEKLY", by_day=[Keywords.RRULE_DAYS[wi]])
                target = now + timedelta(days=((wi - now.weekday()) % 7) or 7)
                target = target.replace(hour=9, minute=0, second=0, microsecond=0)
                # Ищем время ИЛИ диапазон после дня недели
                range_r = self._find_range(tokens, i + 2, now)
                if range_r:
                    sh, sm, eh, em, ei = range_r
                    target = target.replace(hour=sh, minute=sm)
                    target_end = target.replace(hour=eh, minute=em)
                    if target_end <= target:
                        target_end += timedelta(days=1)
                    dt = DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=target,
                        date_to=target_end,
                        has_time=True,
                        recurrence=rec,
                        start=tokens[i].start,
                        end=tokens[ei].end,
                        confidence=0.95,
                    )
                    dt.is_explicit_range = True
                    return (dt, ei - i + 1)
                h, m, ht, ei = self._find_time(tokens, i + 2, now)
                if ht:
                    target = target.replace(hour=h, minute=m)
                return (
                    DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=target,
                        date_to=target,
                        has_time=ht,
                        all_day=not ht,
                        recurrence=rec,
                        start=tokens[i].start,
                        end=tokens[ei].end if ht else nt.end,
                        confidence=0.95,
                    ),
                    ei - i + 1 if ht else 2,
                )
        # каждый будний день → WEEKLY BYDAY=MO..FR
        if nn == "будний" or nv in Keywords.WEEKDAYS:
            rec = RecurrenceRule(
                frequency="WEEKLY", by_day=[Keywords.RRULE_DAYS[d] for d in range(5)]
            )
            # пропускаем «день» если он идёт следом
            tstart = i + 2
            if tstart < len(tokens) and (
                tokens[tstart].normalized == "день"
                or tokens[tstart].value.lower() in ["день", "дня"]
            ):
                tstart += 1
            mon = now + timedelta(days=((0 - now.weekday()) % 7) or 7)
            target = mon.replace(hour=9, minute=0, second=0, microsecond=0)
            h, m, ht, ei = self._find_time(tokens, tstart, now)
            if ht:
                target = target.replace(hour=h, minute=m)
            end = tokens[ei].end if ht else tokens[tstart - 1].end
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target,
                    has_time=ht,
                    all_day=not ht,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=end,
                    confidence=0.92,
                ),
                (ei - i + 1) if ht else (tstart - i),
            )
        # каждый день
        if nn in Keywords.DAY or nv in ["день", "дня", "дней"]:
            rec = RecurrenceRule(frequency="DAILY")
            range_r = self._find_range(tokens, i + 2, now)
            if range_r:
                sh, sm, eh, em, ei = range_r
                target = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                target_end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
                if target_end <= target:
                    target_end += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=target,
                    date_to=target_end,
                    has_time=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=tokens[ei].end,
                    confidence=0.95,
                )
                dt.is_explicit_range = True
                return (dt, ei - i + 1)
            h, m, ht, ei = self._find_time(tokens, i + 2, now)
            target = now.replace(second=0, microsecond=0)
            if ht:
                target = target.replace(hour=h, minute=m)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target,
                    has_time=ht,
                    all_day=not ht,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=tokens[ei].end if ht else nt.end,
                    confidence=0.95,
                ),
                ei - i + 1 if ht else 2,
            )
        # каждую неделю/месяц
        if nn in Keywords.WEEK or nv in ["неделю", "неделя"]:
            # «каждую неделю с пн по пт …» — правило задаёт диапазон дней недели
            # (его соберёт RangeRecognizer с BYDAY); generic WEEKLY здесь лишний.
            if i + 2 < len(tokens) and tokens[i + 2].value.lower() in ("с", "со"):
                for k in range(i + 3, min(i + 7, len(tokens))):
                    if tokens[k].value.lower() == "по":
                        return None
            rec = RecurrenceRule(frequency="WEEKLY")
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=now,
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=nt.end,
                    confidence=0.9,
                ),
                2,
            )
        if nn in Keywords.MONTH or nv in ["месяц", "месяца"]:
            rec = RecurrenceRule(frequency="MONTHLY")
            end_i = i + 1
            # «каждый месяц 15 числа» → BYMONTHDAY=15
            md, mdi = self._find_month_day(tokens, i + 2)
            if md is not None:
                rec.by_month_day = [md]
                end_i = mdi
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=now,
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=tokens[end_i].end,
                    confidence=0.9,
                ),
                end_i - i + 1,
            )
        # каждые N единиц (число цифрой или словами, в т.ч. составное)
        num, consumed = Keywords.parse_cardinal(tokens, i + 1, self.morph)
        if num is not None:
            ui = i + 1 + consumed
            # каждое N число → MONTHLY BYMONTHDAY=N
            if (
                ui < len(tokens)
                and (
                    tokens[ui].normalized in ["число"]
                    or tokens[ui].value.lower() in ["число", "числа"]
                )
                and 1 <= num <= 31
            ):
                rec = RecurrenceRule(frequency="MONTHLY", by_month_day=[num])
                return (
                    DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=now,
                        date_to=now,
                        has_time=False,
                        all_day=True,
                        recurrence=rec,
                        start=tokens[i].start,
                        end=tokens[ui].end,
                        confidence=0.9,
                    ),
                    ui - i + 1,
                )
            if ui < len(tokens):
                ut = tokens[ui]
                uv = ut.value.lower()
                un = ut.normalized
                if un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
                    rec = RecurrenceRule(frequency="MINUTELY", interval=num)
                    return (
                        DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=now,
                            date_to=now,
                            has_time=True,
                            recurrence=rec,
                            start=tokens[i].start,
                            end=ut.end,
                            confidence=0.85,
                        ),
                        ui - i + 1,
                    )
                if un in Keywords.HOUR or uv in ["час", "часа", "часов"]:
                    rec = RecurrenceRule(frequency="HOURLY", interval=num)
                    return (
                        DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=now,
                            date_to=now,
                            has_time=True,
                            recurrence=rec,
                            start=tokens[i].start,
                            end=ut.end,
                            confidence=0.85,
                        ),
                        ui - i + 1,
                    )
                if un in Keywords.DAY or uv in ["день", "дня", "дней"]:
                    rec = RecurrenceRule(frequency="DAILY", interval=num)
                    return (
                        DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=now,
                            date_to=now,
                            has_time=False,
                            all_day=True,
                            recurrence=rec,
                            start=tokens[i].start,
                            end=ut.end,
                            confidence=0.9,
                        ),
                        ui - i + 1,
                    )
                if un in Keywords.WEEK or uv in ["неделю", "недели", "недель"]:
                    rec = RecurrenceRule(frequency="WEEKLY", interval=num)
                    end_i = ui
                    wd, wdi = self._find_weekday_after(tokens, ui + 1)
                    target = now
                    ht = False
                    if wd is not None:
                        rec.by_day = [Keywords.RRULE_DAYS[wd]]
                        end_i = wdi
                        # старт — ближайший будущий этот день недели
                        base = now + timedelta(days=((wd - now.weekday()) % 7) or 7)
                        target = base.replace(hour=9, minute=0, second=0, microsecond=0)
                        # время после дня недели: «... в 12:00»
                        h, m, ht, ei = self._find_time(tokens, wdi + 1, now)
                        if ht:
                            target = target.replace(hour=h, minute=m)
                            end_i = ei
                    return (
                        DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=target,
                            date_to=target,
                            has_time=ht,
                            all_day=not ht,
                            recurrence=rec,
                            start=tokens[i].start,
                            end=tokens[end_i].end,
                            confidence=0.9,
                        ),
                        end_i - i + 1,
                    )
                if un in Keywords.MONTH or uv in ["месяц", "месяца", "месяцев"]:
                    rec = RecurrenceRule(frequency="MONTHLY", interval=num)
                    return (
                        DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=now,
                            date_to=now,
                            has_time=False,
                            all_day=True,
                            recurrence=rec,
                            start=tokens[i].start,
                            end=ut.end,
                            confidence=0.9,
                        ),
                        ui - i + 1,
                    )
        return None

    def _find_month_day(self, tokens, start):
        """N числа/число → (day, index) для BYMONTHDAY."""
        for j in range(start, min(start + 3, len(tokens))):
            if tokens[j].value.isdigit():
                d = int(tokens[j].value)
                if (
                    1 <= d <= 31
                    and j + 1 < len(tokens)
                    and (
                        tokens[j + 1].normalized == "число"
                        or tokens[j + 1].value.lower() in ["число", "числа"]
                    )
                ):
                    return d, j + 1
        return None, start

    def _find_weekday_after(self, tokens, start):
        """[в|по] <день недели> → (weekday_index, end_index). Понимает дательный
        падеж («по понедельникам») и именительный."""
        for j in range(start, min(start + 3, len(tokens))):
            if tokens[j].value.lower() in ("в", "во", "по"):
                continue
            for wi, days in enumerate(Keywords.days_of_week_dative()):
                if tokens[j].normalized in days or tokens[j].value.lower() in days:
                    return wi, j
            for wi, days in enumerate(Keywords.days_of_week()):
                if tokens[j].normalized in days or tokens[j].value.lower() in days:
                    return wi, j
            break
        return None, start

    def _try_by_weekdays(self, tokens, i, now):
        """по понедельникам, по вторникам и четвергам"""
        if tokens[i].value.lower() != "по":
            return None
        if i + 1 >= len(tokens):
            return None
        # Skip if this "по" is part of "с <weekday> по <weekday>" range
        if i >= 2:
            if tokens[i - 2].value.lower() in ["с", "со"]:
                for days in Keywords.days_of_week():
                    if tokens[i - 1].normalized in days or tokens[i - 1].value.lower() in days:
                        return None  # This is a weekday range, not recurrence
        days_found = []
        j = i + 1
        # «по будням» → все будни
        if tokens[j].value.lower() in Keywords.WEEKDAYS or tokens[j].normalized == "будний":
            days_found = [0, 1, 2, 3, 4]
            j += 1
        while j < len(tokens):
            found = False
            for wi, dat in enumerate(Keywords.days_of_week_dative()):
                if tokens[j].value.lower() in dat or tokens[j].normalized in dat:
                    days_found.append(wi)
                    found = True
                    break
            if not found:
                for wi, forms in enumerate(Keywords.days_of_week()):
                    if tokens[j].normalized in forms or tokens[j].value.lower() in forms:
                        days_found.append(wi)
                        found = True
                        break
            if not found:
                if tokens[j].value.lower() in ["и", ","]:
                    j += 1
                    continue
                break
            j += 1
        if not days_found:
            return None
        by_day = [Keywords.RRULE_DAYS[d] for d in days_found]
        rec = RecurrenceRule(frequency="WEEKLY", by_day=by_day)
        nearest = min(days_found, key=lambda d: ((d - now.weekday()) % 7) or 7)
        target = now + timedelta(days=((nearest - now.weekday()) % 7) or 7)
        target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        # Check for range after weekdays
        range_r = self._find_range(tokens, j, now)
        if range_r:
            sh, sm, eh, em, ei = range_r
            target = target.replace(hour=sh, minute=sm)
            target_end = target.replace(hour=eh, minute=em)
            if target_end <= target:
                target_end += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=target,
                date_to=target_end,
                has_time=True,
                recurrence=rec,
                start=tokens[i].start,
                end=tokens[ei].end,
                confidence=0.9,
            )
            dt.is_explicit_range = True
            return (dt, ei - i + 1)
        h, m, ht, ei = self._find_time(tokens, j, now)
        if ht:
            target = target.replace(hour=h, minute=m)
        return (
            DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=target,
                date_to=target,
                has_time=ht,
                all_day=not ht,
                recurrence=rec,
                start=tokens[i].start,
                end=tokens[ei].end if ht else tokens[j - 1].end,
                confidence=0.9,
            ),
            (ei - i + 1) if ht else (j - i),
        )

    def _try_interval(self, tokens, i, now):
        """раз в неделю, раз в 2 дня"""
        if tokens[i].value.lower() != "раз":
            return None
        if i + 2 >= len(tokens):
            return None
        if tokens[i + 1].normalized != "в":
            return None
        nt = tokens[i + 2]
        nv = nt.value.lower()
        nn = nt.normalized
        if nn in Keywords.WEEK or nv in ["неделю", "неделя"]:
            rec = RecurrenceRule(frequency="WEEKLY")
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=now,
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=nt.end,
                    confidence=0.85,
                ),
                3,
            )
        if nn in Keywords.MONTH or nv in ["месяц", "месяца"]:
            rec = RecurrenceRule(frequency="MONTHLY")
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=now,
                    has_time=False,
                    all_day=True,
                    recurrence=rec,
                    start=tokens[i].start,
                    end=nt.end,
                    confidence=0.85,
                ),
                3,
            )
        num = int(nv) if nt.value.isdigit() else Keywords.parse_number_word(nv, self.morph)
        if num and i + 3 < len(tokens):
            ut = tokens[i + 3]
            if ut.normalized in Keywords.DAY or ut.value.lower() in ["день", "дня", "дней"]:
                rec = RecurrenceRule(frequency="DAILY", interval=num)
                return (
                    DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=now,
                        date_to=now,
                        has_time=False,
                        all_day=True,
                        recurrence=rec,
                        start=tokens[i].start,
                        end=ut.end,
                        confidence=0.85,
                    ),
                    4,
                )
        return None

    def _find_time(self, tokens, start, now):
        for j in range(start, min(start + 4, len(tokens))):
            if tokens[j].normalized in Keywords.TIME_FROM and j + 1 < len(tokens):
                tt = tokens[j + 1]
                m = re.match(r"(\d{1,2})[:.-](\d{2})", tt.value)
                if m:
                    return (int(m.group(1)), int(m.group(2)), True, j + 1)
                if tt.value.isdigit():
                    h = int(tt.value)
                    if 0 <= h <= 23:
                        if 1 <= h <= 7:
                            h += 12
                        return (h, 0, True, j + 1)
        return (0, 0, False, start)

    def _find_range(self, tokens, start, now):
        """Ищет диапазон времени: 'X-Y', 'с X до Y' после start."""
        for j in range(start, min(start + 4, len(tokens))):
            # Дефис-диапазон: 9-10, 10:00-11:00
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
            # "с X до Y"
            if tokens[j].value.lower() in ["с", "со"] and j + 3 < len(tokens):
                h1, m1_v, ci = self._parse_tv(tokens, j + 1)
                if h1 is not None:
                    di = ci + 1
                    if di < len(tokens) and tokens[di].normalized in Keywords.TIME_TO:
                        h2, m2_v, ei = self._parse_tv(tokens, di + 1)
                        if h2 is not None:
                            if 1 <= h1 <= 7:
                                h1 += 12
                            if 1 <= h2 <= 7:
                                h2 += 12
                            return (h1, m1_v, h2, m2_v, ei)
        return None

    def _parse_tv(self, tokens, i):
        if i >= len(tokens):
            return (None, 0, i)
        m = re.match(r"^(\d{1,2}):(\d{2})$", tokens[i].value)
        if m:
            return (int(m.group(1)), int(m.group(2)), i)
        if tokens[i].value.isdigit():
            h = int(tokens[i].value)
            if 0 <= h <= 23:
                return (h, 0, i)
        h = Keywords.parse_number_word(tokens[i].value, self.morph)
        if h is not None and 0 <= h <= 23:
            return (h, 0, i)
        return (None, 0, i)

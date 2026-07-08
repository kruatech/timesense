"""Распознавание периодов: на выходных, в будни, на неделе"""

from datetime import datetime, timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class PeriodRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_parse(tokens, i, now)
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_parse(self, tokens, i, now):
        r = (
            self._try_week_modifier(tokens, i, now)
            or self._try_prev_month_day(tokens, i, now)
            or self._try_na_dnyah(tokens, i, now)
            or self._try_part_of_month(tokens, i, now)
        )
        if r:
            return r
        t = tokens[i]
        v = t.value.lower()
        n = t.normalized
        # на выходных / в выходные
        if v in Keywords.WEEKEND or n in ["выходной"]:
            wd = now.weekday()
            sat = now + timedelta(days=(5 - wd) % 7)
            if wd >= 5:
                sat = now
            sat = sat.replace(hour=0, minute=0, second=0, microsecond=0)
            sun = sat + timedelta(days=1)
            return (
                DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=sat,
                    date_to=sun.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.85,
                ),
                1,
            )
        # в будни
        if v in Keywords.WEEKDAYS or n in ["будний"]:
            wd = now.weekday()
            if wd < 5:
                mon = now - timedelta(days=wd)
            else:
                mon = now + timedelta(days=(7 - wd))
            mon = mon.replace(hour=0, minute=0, second=0, microsecond=0)
            fri = mon + timedelta(days=4)
            return (
                DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=mon,
                    date_to=fri.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.8,
                ),
                1,
            )
        # на неделе
        if (
            (v in Keywords.WEEK or n in Keywords.WEEK)
            and i > 0
            and tokens[i - 1].normalized in ["на", "этот"]
        ):
            wd = now.weekday()
            mon = now - timedelta(days=wd)
            mon = mon.replace(hour=0, minute=0, second=0, microsecond=0)
            sun = mon + timedelta(days=6)
            return (
                DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=mon,
                    date_to=sun.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=tokens[i - 1].start,
                    end=t.end,
                    confidence=0.8,
                ),
                1,
            )
        return None

    def _week_bounds(self, ref):
        mon = (ref - timedelta(days=ref.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sun = (mon + timedelta(days=6)).replace(hour=23, minute=59, second=0, microsecond=0)
        return mon, sun

    def _prev_period_refine(self, tokens, after_i):
        """Что стоит после «на прошлой неделе»/«в прошлом месяце» и т.п.
        → ('weekday', wd, end_i) конкретный день недели;
          ('ambiguous', None, after_i) день недели/время без однозначности;
          ('bare', None, after_i) ничего временного (чистый период).
        Пропускает предлог «в/во» перед уточнением."""
        import re as _re
        j = after_i
        if j < len(tokens) and tokens[j].value.lower() in ("в", "во", "на"):
            j += 1
        if j >= len(tokens):
            return ("bare", None, after_i)
        # день недели?
        for wd, days in enumerate(Keywords.days_of_week()):
            if tokens[j].normalized in days or tokens[j].value.lower() in days:
                return ("weekday", wd, j)
        # время (H:MM или «в N [часов]») без дня → неоднозначно
        if _re.match(r"^\d{1,2}:\d{2}$", tokens[j].value):
            return ("ambiguous", None, j)
        if tokens[j].value.isdigit():
            # это может быть «15 числа» — обрабатывается отдельно для месяца;
            # здесь (для недели) голое число трактуем как неоднозначное время
            return ("ambiguous", None, j)
        return ("bare", None, after_i)

    def _time_after_weekday(self, tokens, wd_i):
        """Время сразу после дня недели: «четверг в 14:40» → (h, m, end_i) | None."""
        import re as _re
        j = wd_i + 1
        if j < len(tokens) and tokens[j].value.lower() in ("в", "во"):
            j += 1
        if j >= len(tokens):
            return None
        mm = _re.match(r"^(\d{1,2}):(\d{2})$", tokens[j].value)
        if mm:
            h, m = int(mm.group(1)), int(mm.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59:
                return (h, m, j)
        return None

    def _try_week_modifier(self, tokens, i, now):
        """на следующей неделе / на прошлой неделе / на этой неделе"""
        t = tokens[i]
        v = t.value.lower()
        n = t.normalized
        if not (v in Keywords.WEEK or n in Keywords.WEEK):
            return None
        if i == 0:
            return None
        mod = tokens[i - 1].value.lower()
        start_i = i - 1
        # опциональный предлог "на"/"в" перед модификатором
        if i - 2 >= 0 and tokens[i - 2].value.lower() in ("на", "в"):
            start_i = i - 2
        if mod in Keywords.NEXT:
            ref = now + timedelta(weeks=1)
        elif mod in Keywords.PREVIOUS_MOD:
            # prev-weekday refine wired: «на прошлой неделе в четверг» →
            # конкретный прошлый <день> (формула is_prev), + опц. время.
            # «на прошлой неделе в 14:30» (только время) → None (неоднозначно).
            refine = self._prev_period_refine(tokens, i + 1)
            if refine[0] == "weekday":
                wd = refine[1]
                wd_i = refine[2]
                cwd = now.weekday()
                db = (cwd - wd) % 7
                if db == 0:
                    db = 7
                target = (now + timedelta(days=-db)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                tafter = self._time_after_weekday(tokens, wd_i)
                if tafter is not None:
                    th, tm, tend = tafter
                    target = target.replace(hour=th, minute=tm)
                    end_tok = tend
                    ht = True
                else:
                    end_tok = wd_i
                    ht = False
                return (
                    DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=target,
                        date_to=target if ht else target.replace(hour=23, minute=59),
                        has_time=ht,
                        all_day=not ht,
                        start=tokens[start_i].start,
                        end=tokens[end_tok].end,
                        confidence=0.9,
                        is_past=True,
                    ),
                    end_tok - start_i + 1,
                )
            if refine[0] == "ambiguous":
                return None  # «на прошлой неделе в 14:30» — неоднозначно
            ref = now - timedelta(weeks=1)
        elif mod in Keywords.CURRENT or mod in Keywords.CURRENT_NEXT:
            ref = now
        else:
            return None
        mon, sun = self._week_bounds(ref)
        is_past = sun < now
        return (
            DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=mon,
                date_to=sun,
                has_time=False,
                all_day=True,
                fuzzy=True,
                start=tokens[start_i].start,
                end=t.end,
                confidence=0.82,
                is_past=is_past,
            ),
            1,
        )

    def _try_prev_month_day(self, tokens, i, now):
        """«в прошлом месяце N числа» → N-е прошлого месяца, is_past.
        Требуется явное число (день месяца); квартал/год/только-время сюда не
        попадают (их отсекает hard-fail в parser). Невалидный день (июнь 31) →
        не срабатывает."""
        from calendar import monthrange

        t = tokens[i]
        v = t.value.lower()
        n = t.normalized
        if not (v in Keywords.MONTH or n in Keywords.MONTH):
            return None
        if i == 0:
            return None
        mod = tokens[i - 1].value.lower()
        modn = tokens[i - 1].normalized
        if not (mod in Keywords.PREVIOUS_MOD or modn in Keywords.PREVIOUS_MOD):
            return None
        start_i = i - 1
        if i - 2 >= 0 and tokens[i - 2].value.lower() in ("на", "в", "во"):
            start_i = i - 2
        # ищем число (день) справа: «N числа» или просто N
        import re as _re
        day = None
        end_i = i
        for j in range(i + 1, min(i + 4, len(tokens))):
            mm = _re.match(r"^(\d{1,2})$", tokens[j].value)
            if mm:
                day = int(mm.group(1))
                end_i = j
                # если дальше «числа» — включим в спан
                if j + 1 < len(tokens) and tokens[j + 1].value.lower() in ("числа", "число"):
                    end_i = j + 1
                break
            # порядковое словом («пятнадцатого»)
            ov = Keywords.parse_ordinal_day(tokens[j].value)
            if ov is not None:
                day = ov
                end_i = j
                break
        if day is None:
            return None
        m = now.month - 1
        y = now.year
        if m < 1:
            m = 12
            y -= 1
        if day < 1 or day > monthrange(y, m)[1]:
            return None  # несуществующий день прошлого месяца
        target = datetime(y, m, day, 0, 0, 0, 0)
        return (
            DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=target,
                date_to=target.replace(hour=23, minute=59),
                has_time=False,
                all_day=True,
                start=tokens[start_i].start,
                end=tokens[end_i].end,
                confidence=0.9,
                is_past=True,
            ),
            1,
        )

    def _try_na_dnyah(self, tokens, i, now):
        """на днях — ближайшие несколько дней (нечётко)"""
        if tokens[i].value.lower() != "на":
            return None
        if i + 1 >= len(tokens):
            return None
        if tokens[i + 1].value.lower() != "днях":
            return None
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        e = (now + timedelta(days=3)).replace(hour=23, minute=59, second=0, microsecond=0)
        return (
            DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=s,
                date_to=e,
                has_time=False,
                all_day=True,
                fuzzy=True,
                start=tokens[i].start,
                end=tokens[i + 1].end,
                confidence=0.6,
            ),
            2,
        )

    def _period_bounds(self, unit, now):
        """Полные границы текущего периода (start_dt 00:00, end_dt 23:59)."""
        from calendar import monthrange

        if unit == "day":
            s = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return s, s.replace(hour=23, minute=59)
        if unit == "week":
            return self._week_bounds(now)
        if unit == "month":
            last = monthrange(now.year, now.month)[1]
            return (datetime(now.year, now.month, 1), datetime(now.year, now.month, last, 23, 59))
        if unit == "quarter":
            q = (now.month - 1) // 3
            m1 = q * 3 + 1
            m2 = m1 + 2
            last = monthrange(now.year, m2)[1]
            return (datetime(now.year, m1, 1), datetime(now.year, m2, last, 23, 59))
        if unit == "year":
            return (datetime(now.year, 1, 1), datetime(now.year, 12, 31, 23, 59))
        return None

    def _part_window(self, unit, part, s_full, e_full):
        """Окно начала/середины/конца внутри периода."""
        if unit == "day":
            if part == "start":
                return s_full.replace(hour=6), s_full.replace(hour=10)
            if part == "middle":
                return s_full.replace(hour=12), s_full.replace(hour=15)
            return s_full.replace(hour=18), e_full  # end
        # дневные периоды: окно в днях
        span = (e_full.date() - s_full.date()).days
        if unit == "week":
            pad = 1
        elif unit == "month":
            pad = 4
        else:  # quarter, year
            pad = max(9, span // 9)
        if part == "start":
            return s_full, (s_full + timedelta(days=pad)).replace(hour=23, minute=59)
        if part == "end":
            return (e_full - timedelta(days=pad)).replace(hour=0, minute=0), e_full
        mid = s_full + (e_full - s_full) / 2
        return (
            (mid - timedelta(days=pad // 2 + 1)).replace(hour=0, minute=0),
            (mid + timedelta(days=pad // 2 + 1)).replace(hour=23, minute=59),
        )

    def _try_part_of_month(self, tokens, i, now):
        """в начале/середине/конце <дня|недели|месяца|года|квартала|марта>;
        до конца <периода> → дедлайн."""
        t = tokens[i]
        v = t.value.lower()
        n = t.normalized
        if v in Keywords.START_OF or n in Keywords.START_OF:
            part = "start"
        elif v in Keywords.END_OF or n in Keywords.END_OF:
            part = "end"
        elif v in Keywords.MIDDLE_OF or n in Keywords.MIDDLE_OF:
            part = "middle"
        else:
            return None
        if i + 1 >= len(tokens):
            return None
        nxt = tokens[i + 1]
        nv = nxt.value.lower()
        nn = nxt.normalized
        # определяем единицу периода
        unit = None
        month = None
        if nv in Keywords.MONTH or nn in Keywords.MONTH:
            unit = "month"
        elif nv in Keywords.WEEK or nn in Keywords.WEEK:
            unit = "week"
        elif nv in Keywords.YEAR or nn in Keywords.YEAR:
            unit = "year"
        elif nv in Keywords.QUARTER or nn in Keywords.QUARTER:
            unit = "quarter"
        elif nv in Keywords.DAY or nn == "день":
            unit = "day"
        else:
            for mi, mw in enumerate(Keywords.months()):
                if nn in mw or nv in mw:
                    month = mi + 1
                    unit = "named_month"
                    break
        if unit is None:
            return None

        start_i = i
        if i - 1 >= 0 and tokens[i - 1].value.lower() in ("в", "во"):
            start_i = i - 1
        lead_deadline = (
            part == "end" and i - 1 >= 0 and tokens[i - 1].normalized in Keywords.TIME_TO
        )
        if lead_deadline:
            start_i = i - 1
        # «начало/середина дня» пересекается с частью суток («дня») — не трогаем,
        # поддерживаем только дедлайн «до конца дня».
        if unit == "day" and not lead_deadline:
            return None

        if unit == "named_month":
            from calendar import monthrange

            year = now.year
            last = monthrange(year, month)[1]
            s_full = datetime(year, month, 1)
            e_full = datetime(year, month, last, 23, 59)
            if self.config.prefer_nearest_future and e_full < now:
                year += 1
                last = monthrange(year, month)[1]
                s_full = datetime(year, month, 1)
                e_full = datetime(year, month, last, 23, 59)
            unit = "month"
        else:
            s_full, e_full = self._period_bounds(unit, now)
            if self.config.prefer_nearest_future and e_full < now and unit != "day":
                if unit == "week":
                    s_full, e_full = self._week_bounds(now + timedelta(weeks=1))
                elif unit == "year":
                    s_full = datetime(now.year + 1, 1, 1)
                    e_full = datetime(now.year + 1, 12, 31, 23, 59)
                elif unit in ("month", "quarter"):
                    s_full, e_full = self._period_bounds(
                        unit, now.replace(day=1) + timedelta(days=32)
                    )

        if lead_deadline:
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=e_full,
                    has_time=False,
                    is_deadline=True,
                    start=tokens[start_i].start,
                    end=nxt.end,
                    confidence=0.85,
                ),
                (i + 1) - start_i + 1,
            )

        s, e = self._part_window(unit, part, s_full, e_full)
        return (
            DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=s,
                date_to=e,
                has_time=False,
                all_day=True,
                fuzzy=True,
                start=tokens[start_i].start,
                end=nxt.end,
                confidence=0.7,
            ),
            (i + 1) - start_i + 1,
        )

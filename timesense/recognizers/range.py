"""Распознавание диапазонов: с 10 до 11, 9-10, с утра до вечера, с понедельника по пятницу"""

from datetime import datetime, timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule
from ..dict.keywords import Keywords


class RangeRecognizer(Recognizer):
    PARTS = {
        "утро": 9,
        "утром": 9,
        "утра": 9,
        "обед": 13,
        "обеда": 13,
        "день": 15,
        "дня": 15,
        "днём": 15,
        "днем": 15,
        "вечер": 19,
        "вечером": 19,
        "вечера": 19,
        "ночь": 23,
        "ночью": 23,
        "ночи": 23,
    }

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_weekday_range(tokens, i, now)
                or self._try_between(tokens, i, now)
                or self._try_date_range(tokens, i, now)
                or self._try_time_range(tokens, i, now)
                or self._try_time_to_weekday(tokens, i, now)
                or self._try_dash_range(tokens, i, now)
                or self._try_day_part_range(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_weekday_range(self, tokens, i, now):
        """с понедельника по пятницу [+ время/диапазон]"""
        if tokens[i].value.lower() not in ["с", "со"]:
            return None
        if i + 3 >= len(tokens):
            return None
        # Ищем начальный день недели
        start_wd = None
        for wi, days in enumerate(Keywords.days_of_week()):
            if tokens[i + 1].normalized in days or tokens[i + 1].value.lower() in days:
                start_wd = wi
                break
        if start_wd is None:
            return None
        # Ищем "до"/"по"
        if tokens[i + 2].normalized not in Keywords.TIME_TO:
            return None
        # Ищем конечный день недели
        end_wd = None
        for wi, days in enumerate(Keywords.days_of_week()):
            if tokens[i + 3].normalized in days or tokens[i + 3].value.lower() in days:
                end_wd = wi
                break
        if end_wd is None:
            return None

        # Вычисляем даты
        days_to_start = (start_wd - now.weekday()) % 7
        if days_to_start == 0 and now.hour >= 23:
            days_to_start = 7
        start_date = (now + timedelta(days=days_to_start)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if end_wd >= start_wd:
            span_days = end_wd - start_wd
        else:
            span_days = 7 - start_wd + end_wd
        end_date = start_date + timedelta(days=span_days)
        end_date = end_date.replace(hour=23, minute=59)

        ei = i + 3
        # Генерируем recurrence by_day
        if end_wd >= start_wd:
            wd_list = list(range(start_wd, end_wd + 1))
        else:
            wd_list = list(range(start_wd, 7)) + list(range(0, end_wd + 1))
        by_day = [Keywords.RRULE_DAYS[d] for d in wd_list]

        # Проверяем — есть ли время после диапазона дней?
        time_result = self._find_time_after(tokens, ei + 1, now)
        range_result = self._find_range_after(tokens, ei + 1, now)

        # «каждую неделю с пн по пт» → бесконечная серия; «с пн по пт» → конечная (эта неделя)
        has_every = any(
            t.value.lower().startswith("кажд") or (t.normalized or "").startswith("кажд")
            for t in tokens[:i]
        )

        if range_result:
            # "с пн по пт 9-10" → CalendarResult + КОНЕЧНАЯ recurrence (UNTIL = конец диапазона)
            sh, sm, eh, em, time_ei = range_result
            target_date = start_date.replace(hour=sh, minute=sm)
            target_end = start_date.replace(hour=eh, minute=em)
            if target_end <= target_date:
                target_end += timedelta(days=1)
            rec = RecurrenceRule(frequency="WEEKLY", by_day=by_day)
            if not has_every:
                rec.until = end_date
            dt = DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=target_date,
                date_to=target_end,
                has_time=True,
                recurrence=rec,
                start=tokens[i].start,
                end=tokens[time_ei].end,
                confidence=0.95,
            )
            dt.is_explicit_range = True
            return (dt, time_ei - i + 1)
        elif time_result:
            # "с пн по пт в 10" → FIXED + КОНЕЧНАЯ recurrence (UNTIL)
            h, m, time_ei = time_result
            target_date = start_date.replace(hour=h, minute=m)
            rec = RecurrenceRule(frequency="WEEKLY", by_day=by_day)
            if not has_every:
                rec.until = end_date
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=target_date,
                date_to=target_date,
                has_time=True,
                recurrence=rec,
                start=tokens[i].start,
                end=tokens[time_ei].end,
                confidence=0.95,
            )
            return (dt, time_ei - i + 1)
        else:
            # "с пн по пт" — многодневный период, no recurrence
            dt = DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=start_date,
                date_to=end_date,
                has_time=False,
                all_day=True,
                start=tokens[i].start,
                end=tokens[ei].end,
                confidence=0.9,
            )
            return (dt, ei - i + 1)

    def _find_time_after(self, tokens, start, now):
        """Ищет 'в X' / 'в X:YY' / 'к X' после индекса start."""
        if start >= len(tokens):
            return None
        if (
            tokens[start].normalized not in Keywords.TIME_FROM
            and tokens[start].normalized not in Keywords.TIME_BY
        ):
            return None
        if start + 1 >= len(tokens):
            return None
        tt = tokens[start + 1]
        m = re.match(r"(\d{1,2})[:.-](\d{2})", tt.value)
        if m:
            return (int(m.group(1)), int(m.group(2)), start + 1)
        if tt.value.isdigit():
            h = int(tt.value)
            if 0 <= h <= 23:
                if 1 <= h <= 7 and self.config.prefer_nearest_future:
                    h += 12
                return (h, 0, start + 1)
        h = Keywords.parse_number_word(tt.value, self.morph)
        if h is not None and 0 <= h <= 23:
            if 1 <= h <= 7 and self.config.prefer_nearest_future:
                h += 12
            return (h, 0, start + 1)
        return None

    def _find_range_after(self, tokens, start, now):
        """Ищет диапазон времени: 'X-Y', 'с X до Y' после индекса start."""
        if start >= len(tokens):
            return None
        # Дефис-диапазон: 9-10
        m = re.match(r"^(\d{1,2}):?(\d{2})?-(\d{1,2}):?(\d{2})?$", tokens[start].value)
        if m:
            h1 = int(m.group(1))
            m1 = int(m.group(2)) if m.group(2) else 0
            h2 = int(m.group(3))
            m2 = int(m.group(4)) if m.group(4) else 0
            if 0 <= h1 <= 23 and 0 <= h2 <= 23:
                h1, h2 = self._ampm_pair(h1, h2)
                return (h1, m1, h2, m2, start)
        # "с X до Y"
        if tokens[start].value.lower() in ["с", "со"] and start + 3 < len(tokens):
            h1, m1, ci, _p1 = self._parse_time_val(tokens, start + 1)
            if h1 is not None:
                di = ci + 1
                if di < len(tokens) and tokens[di].normalized in Keywords.TIME_TO:
                    h2, m2, ei, _p2 = self._parse_time_val(tokens, di + 1)
                    if h2 is not None:
                        h1, h2 = self._ampm_pair(h1, h2)
                        return (h1, m1, h2, m2, ei)
        return None

    def _try_between(self, tokens, i, now):
        """между 10 и 12 [встреча] → диапазон времени"""
        if tokens[i].value.lower() != "между":
            return None
        if i + 3 >= len(tokens):
            return None
        h1, m1, ci, _pb1 = self._parse_time_val(tokens, i + 1)
        if h1 is None:
            return None
        di = ci + 1
        if di >= len(tokens) or tokens[di].value.lower() not in ["и", "до"]:
            return None
        h2, m2, ei, _pb2 = self._parse_time_val(tokens, di + 1)
        if h2 is None:
            return None
        h1, h2 = self._ampm_pair(h1, h2)
        s = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        e = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if self.config.prefer_nearest_future and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.9,
        )
        dt.is_explicit_range = True
        return (dt, ei - i + 1)

    def _try_date_range(self, tokens, i, now):
        """«с <день1> [месяц1] по <день2> [месяц2]» → период дат.
        Месяц1 опционален (с 1 по 5 августа); допускается переход через
        год (с 25 декабря по 5 января). День — цифрой, «N-го» или словом
        (первого/пятнадцатое). Ставится ДО _try_time_range, чтобы числа
        не были распознаны как часы."""
        from calendar import monthrange

        if tokens[i].value.lower() not in ["с", "со"]:
            return None
        if i + 3 >= len(tokens):
            return None

        def parse_day(idx):
            if idx >= len(tokens):
                return None
            import re as _re
            v = tokens[idx].value
            m = _re.match(r"^(\d{1,2})-?(?:го|е)?$", v)
            if m:
                d = int(m.group(1))
                return d if 1 <= d <= 31 else None
            if v.isdigit():
                d = int(v)
                return d if 1 <= d <= 31 else None
            d = Keywords.parse_ordinal_day(v)
            return d if d and 1 <= d <= 31 else None

        def parse_month(idx):
            if idx >= len(tokens):
                return None
            for mi, mw in enumerate(Keywords.months()):
                if tokens[idx].normalized in mw or tokens[idx].value.lower() in mw:
                    return mi + 1
            return None

        d1 = parse_day(i + 1)
        if d1 is None:
            return None
        # опциональный месяц1 сразу после дня1
        j = i + 2
        mon1 = parse_month(j)
        if mon1 is not None:
            j += 1
        # должно идти «по/до»
        if j >= len(tokens) or tokens[j].normalized not in Keywords.TIME_TO:
            return None
        d2 = parse_day(j + 1)
        if d2 is None:
            return None
        mon2 = parse_month(j + 2)
        if mon2 is None:
            return None
        end_i = j + 2
        if mon1 is None:
            mon1 = mon2

        def safe(y, m, d):
            return None if not (1 <= d <= monthrange(y, m)[1]) else datetime(y, m, d)

        year = now.year
        start = safe(year, mon1, d1)
        if start is None:
            return None
        if self.config.prefer_nearest_future and start.date() < now.date():
            start = safe(year + 1, mon1, d1)
            if start is None:
                return None
        end = safe(start.year, mon2, d2)
        if end is None:
            return None
        if end.date() < start.date():
            end = safe(start.year + 1, mon2, d2)
        if end is None:
            return None
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end.replace(hour=23, minute=59, second=0, microsecond=0)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=start,
            date_to=end,
            has_time=False,
            all_day=True,
            start=tokens[i].start,
            end=tokens[end_i].end,
            confidence=0.95,
        )
        dt.is_explicit_range = True
        return (dt, end_i - i + 1)

    def _try_time_range(self, tokens, i, now):
        """с 10 до 11, с 10:00 до 11:30, с десяти до одиннадцати, с девяти утра до шести вечера"""
        if tokens[i].value.lower() not in ["с", "со"]:
            return None
        if i + 3 >= len(tokens):
            return None
        h1, m1, ci, pod1 = self._parse_time_val(tokens, i + 1)
        if h1 is None:
            return None
        di = ci + 1
        if di >= len(tokens) or tokens[di].normalized not in Keywords.TIME_TO:
            return None
        h2, m2, ei, pod2 = self._parse_time_val(tokens, di + 1)
        if h2 is None:
            return None
        if pod1 or pod2:
            h1 = self._apply_pod(h1, pod1)
            h2 = self._apply_pod(h2, pod2)
        else:
            h1, h2 = self._ampm_pair(h1, h2)
        s = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        e = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if self.config.prefer_nearest_future and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.95,
        )
        dt.is_explicit_range = True
        return (dt, ei - i + 1)

    def _try_time_to_weekday(self, tokens, i, now):
        """«с <время> до <день недели>» → дедлайн-диапазон:
        start = ближайшее будущее <время>, deadline = ближайший будущий
        <день недели> 23:59. Пример: «с 10 до пятницы» (пн) →
        start=завтра 10:00, deadline=пятница 23:59.
        Числовой диапазон «с 10 до 12» перехватывает _try_time_range раньше."""
        if tokens[i].value.lower() not in ["с", "со"]:
            return None
        if i + 3 >= len(tokens):
            return None
        h1, m1, ci, pod1 = self._parse_time_val(tokens, i + 1)
        if h1 is None:
            return None
        di = ci + 1
        if di >= len(tokens) or tokens[di].normalized not in Keywords.TIME_TO:
            return None
        # за «до» должен идти ДЕНЬ НЕДЕЛИ (а не время — то ловит _try_time_range)
        wi_tok = di + 1
        if wi_tok >= len(tokens):
            return None
        weekday = None
        for wd, days in enumerate(Keywords.days_of_week()):
            if tokens[wi_tok].normalized in days or tokens[wi_tok].value.lower() in days:
                weekday = wd
                break
        if weekday is None:
            return None
        if pod1:
            h1 = self._apply_pod(h1, pod1)
        start = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        if self.config.prefer_nearest_future and start < now:
            start += timedelta(days=1)
        da = (weekday - now.weekday()) % 7
        if da == 0:
            da = 7
        deadline = (now + timedelta(days=da)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=start,
            date_to=deadline,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[wi_tok].end,
            confidence=0.9,
        )
        return (dt, wi_tok - i + 1)

    def _try_dash_range(self, tokens, i, now):
        """9-10, 10:00-11:00"""
        m = re.match(r"^(\d{1,2}):?(\d{2})?-(\d{1,2}):?(\d{2})?$", tokens[i].value)
        if not m:
            return None
        h1 = int(m.group(1))
        m1 = int(m.group(2)) if m.group(2) else 0
        h2 = int(m.group(3))
        m2 = int(m.group(4)) if m.group(4) else 0
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23):
            return None
        s = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        e = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
        if self.config.prefer_nearest_future and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=True,
            start=tokens[i].start,
            end=tokens[i].end,
            confidence=0.9,
        )
        dt.is_explicit_range = True
        return (dt, 1)

    def _try_day_part_range(self, tokens, i, now):
        """с утра до вечера, с обеда до ночи"""
        if i + 3 >= len(tokens):
            return None
        if tokens[i].value.lower() not in ["с", "со"]:
            return None
        sv = tokens[i + 1].value.lower()
        if sv not in self.PARTS:
            return None
        if tokens[i + 2].normalized not in Keywords.TIME_TO:
            return None
        ev = tokens[i + 3].value.lower()
        if ev not in self.PARTS:
            return None
        sh = self.PARTS[sv]
        eh = self.PARTS[ev]
        s = now.replace(hour=sh, minute=0, second=0, microsecond=0)
        e = now.replace(hour=eh, minute=0, second=0, microsecond=0)
        if self.config.prefer_nearest_future and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=True,
            start=tokens[i].start,
            end=tokens[i + 3].end,
            confidence=0.85,
        )
        dt.is_explicit_range = True
        return (dt, 4)

    def _ampm_pair(self, h1, h2):
        """AM/PM для пары часов диапазона. Ночной переход через полночь
        (старт вечером/ночью, конец 1-7) оставляет конец буквальным —
        он попадёт на следующий день при e<=s. При prefer_nearest_future=False
        часы берутся буквально (как в EN-локали)."""
        if not self.config.prefer_nearest_future:
            return h1, h2
        night = h1 >= 18 and 1 <= h2 <= 7
        a1 = h1 + 12 if 1 <= h1 <= 7 else h1
        a2 = h2 if night else (h2 + 12 if 1 <= h2 <= 7 else h2)
        return a1, a2

    _POD = {
        "утро": "am",
        "утром": "am",
        "утра": "am",
        "день": "day",
        "дня": "day",
        "днём": "day",
        "днем": "day",
        "вечер": "eve",
        "вечером": "eve",
        "вечера": "eve",
        "ночь": "night",
        "ночью": "night",
        "ночи": "night",
    }

    @staticmethod
    def _apply_pod(h, pod):
        if pod == "am":
            return 0 if h == 12 else h
        if pod == "day":
            return h if h >= 12 else h + 12
        if pod == "eve":
            return h + 12 if 1 <= h <= 11 else h
        if pod == "night":
            return h if 0 <= h <= 6 else (0 if h == 12 else h)
        return h

    def _parse_time_val(self, tokens, i):
        """→ (hour, minute, end_index, pod). Поддерживает H:MM, цифру, слово
        (в т.ч. родительный: «десяти», «одиннадцати»), «половина <порядковое>»
        и уточнение утра/вечера/дня/ночи."""
        if i >= len(tokens):
            return (None, 0, i, None)
        # «половины четвёртого» → 3:30 (половина N = (N-1):30)
        if tokens[i].value.lower() in ("половина", "половины", "пол") and i + 1 < len(tokens):
            nxt = tokens[i + 1].value.lower()
            ordv = Keywords.parse_ordinal_day(nxt)
            if ordv is None:
                ordv = Keywords._NORMALIZED_TO_NUMBER.get(nxt)
            if ordv is not None and 1 <= ordv <= 12:
                h = (ordv - 1) % 24
                pod = self._pod_after(tokens, i + 1)
                return (h, 30, i + 1 + (1 if pod else 0), pod)
        m = re.match(r"^(\d{1,2}):(\d{2})$", tokens[i].value)
        if m:
            end = i
            pod = self._pod_after(tokens, end)
            if pod:
                end += 1
            return (int(m.group(1)), int(m.group(2)), end, pod)
        h = None
        if tokens[i].value.isdigit():
            hv = int(tokens[i].value)
            if 0 <= hv <= 23:
                h = hv
        if h is None:
            v = Keywords._cardinal_value(tokens[i].value, self.morph)
            if v is not None and 0 <= v <= 23:
                h = v
        if h is None:
            return (None, 0, i, None)
        end = i
        pod = self._pod_after(tokens, end)
        if pod:
            end += 1
        return (h, 0, end, pod)

    def _pod_after(self, tokens, idx):
        if idx + 1 < len(tokens):
            nv = tokens[idx + 1].value.lower()
            nn = tokens[idx + 1].normalized
            return self._POD.get(nv) or self._POD.get(nn)
        return None

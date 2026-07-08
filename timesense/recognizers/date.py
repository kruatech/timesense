"""Распознавание дат: 10 января, в пятницу"""

from datetime import datetime, timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class DateRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_weekday(tokens, i, now)
                or self._try_date_month(tokens, i, now)
                or self._try_day_of_month(tokens, i, now)
                or self._try_relative(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _deadline_time_after(self, tokens, si):
        """Ищет время сразу после дня недели: «пятнице 18:00», «пятнице в 18».
        → (hour, minute, end_index) или None. Час 1-7 без уточнения → +12."""
        import re as _re
        j = si + 1
        if j < len(tokens) and tokens[j].normalized in Keywords.TIME_FROM:
            j += 1  # пропускаем предлог «в»
        if j >= len(tokens):
            return None
        mm = _re.match(r"^(\d{1,2}):(\d{2})$", tokens[j].value)
        if mm:
            h, mi = int(mm.group(1)), int(mm.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                return (h, mi, j)
            return None
        if tokens[j].value.isdigit():
            h = int(tokens[j].value)
            if 0 <= h <= 23:
                if 1 <= h <= 7:
                    h += 12
                return (h, 0, j)
        return None

    def _try_weekday(self, tokens, i, now):
        """в пятницу, на среду (период); до/к пятнице (дедлайн)"""
        is_deadline = False
        si = i
        lead = tokens[i].normalized
        if lead in Keywords.TIME_FROM + Keywords.TIME_ON:
            si = i + 1
        elif lead in Keywords.TIME_TO or lead in Keywords.TIME_BY:
            # «до пятницы» / «к пятнице» → дедлайн (а не период)
            is_deadline = True
            si = i + 1
        if si >= len(tokens):
            return None
        t = tokens[si]
        for wi, days in enumerate(Keywords.days_of_week()):
            if t.normalized in days or t.value.lower() in days:
                days_ahead = (wi - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target = now + timedelta(days=days_ahead)
                target = target.replace(hour=0, minute=0, second=0, microsecond=0)
                if is_deadline:
                    tafter = self._deadline_time_after(tokens, si)
                    if tafter is not None:
                        th, tm, tend = tafter
                        dl = target.replace(hour=th, minute=tm)
                        dt = DateTimeToken(
                            type=DateTimeType.FIXED,
                            date_from=now,
                            date_to=dl,
                            has_time=True,
                            is_deadline=True,
                            start=tokens[i].start,
                            end=tokens[tend].end,
                            confidence=0.92,
                        )
                        return (dt, tend - i + 1)
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=now,
                        date_to=target.replace(hour=23, minute=59),
                        has_time=False,
                        is_deadline=True,
                        start=tokens[i].start,
                        end=t.end,
                        confidence=0.9,
                    )
                else:
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=target,
                        date_to=target.replace(hour=23, minute=59),
                        has_time=False,
                        all_day=True,
                        start=tokens[i].start,
                        end=t.end,
                        confidence=0.9,
                    )
                return (dt, si - i + 1)
        return None

    def _try_date_month(self, tokens, i, now):
        """10 января, 5-го марта, первого сентября"""
        from calendar import monthrange

        t = tokens[i]
        day = None
        month_tok = i + 1  # индекс токена, где ожидается месяц
        m = re.match(r"^(\d+)-?(?:го|е)?$", t.value)
        if m:
            day = int(m.group(1))
        elif t.value.isdigit():
            day = int(t.value)
        else:
            # составное порядковое: «двадцать девятого»=29, «тридцать первого»=31
            if i + 1 < len(tokens):
                comp = Keywords.parse_ordinal_day_2(t.value, tokens[i + 1].value)
                if comp is not None:
                    day = comp
                    month_tok = i + 2
            if day is None:
                day = Keywords.parse_ordinal_day(t.value)
        if day is None or not (1 <= day <= 31):
            return None
        if month_tok >= len(tokens):
            return None
        # числа
        if tokens[month_tok].value.lower() in Keywords.DAY_IN_MONTH:
            return None
        for mi, mw in enumerate(Keywords.months()):
            if tokens[month_tok].normalized in mw or tokens[month_tok].value.lower() in mw:
                month = mi + 1
                end_i = month_tok
                # явный год сразу за месяцем («29 февраля 2024»)
                explicit_year = None
                if month_tok + 1 < len(tokens) and tokens[month_tok + 1].value.isdigit():
                    yv = int(tokens[month_tok + 1].value)
                    if 2020 <= yv <= 2100:
                        explicit_year = yv
                        end_i = month_tok + 1
                if explicit_year is not None:
                    # валидируем строго против указанного года
                    target = self._safe_date(explicit_year, month, day)
                    if target is None:
                        return None  # 29 февраля 2025 / 31 апреля 2026 → отклоняем
                else:
                    year = now.year
                    # дата невозможна для месяца ни в этом, ни в следующем году → отклоняем
                    if day > monthrange(year, month)[1] and day > monthrange(year + 1, month)[1]:
                        return None
                    target = self._safe_date(year, month, day)
                    if target is None or (
                        self.config.prefer_nearest_future and target.date() < now.date()
                    ):
                        nt = self._safe_date(year + 1, month, day)
                        if nt is not None:
                            target = nt
                    if target is None:
                        return None
                lead_deadline = i > 0 and tokens[i - 1].normalized in (
                    Keywords.TIME_TO + Keywords.TIME_BY
                )
                if lead_deadline:
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=now,
                        date_to=target.replace(hour=23, minute=59),
                        has_time=False,
                        is_deadline=True,
                        start=tokens[i - 1].start,
                        end=tokens[end_i].end,
                        confidence=0.92,
                    )
                    return (dt, end_i - i + 1)
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=tokens[i].start,
                    end=tokens[end_i].end,
                    confidence=0.95,
                )
                return (dt, end_i - i + 1)
        return None

    @staticmethod
    def _safe_date(year, month, day):
        try:
            return datetime(year, month, day, 0, 0, 0)
        except ValueError:
            return None

    # Слова-маркеры времени, после/перед которыми порядковое слово — это НЕ день месяца
    _TIME_MARKERS = {"пол", "половина", "половине", "половину", "четверть", "четверти", "без"}

    def _try_day_of_month(self, tokens, i, now):
        """15 числа | 15-го числа | 15-го | пятнадцатого — день текущего/следующего месяца.

        Голый порядковый день (без 'числа') принимается только для явных форм
        (порядковое слово или 'N-го'), и только если дальше не идёт месяц/день
        недели (это другие конструкции) и рядом нет маркеров времени (пол/четверть/без).
        """
        t = tokens[i]
        v = t.value.lower()
        day = None
        explicit = False  # ordinal word или 'N-го' (а не голая цифра)
        m = re.match(r"^(\d+)-(?:го|е)$", v)
        if m:
            day = int(m.group(1))
            explicit = True
        else:
            comp = Keywords.parse_ordinal_day_2(v, tokens[i + 1].value) if i + 1 < len(tokens) else None
            ow = Keywords.parse_ordinal_day(v)
            if comp is not None:
                day = comp
                explicit = True
                _compound = True
            elif ow is not None:
                day = ow
                explicit = True
            elif v.isdigit():
                day = int(v)
        if day is None or not (1 <= day <= 31):
            return None

        _compound = locals().get("_compound", False)
        base_i = i + 1 if _compound else i  # составное порядковое занимает 2 токена
        has_chislo = base_i + 1 < len(tokens) and tokens[base_i + 1].value.lower() in Keywords.DAY_IN_MONTH
        end_i = base_i
        if has_chislo:
            end_i = base_i + 1
        else:
            # без 'числа' — только явные формы
            if not explicit:
                return None
            # рядом маркер времени → это время (пол первого / без четверти первого), не день
            if i > 0 and tokens[i - 1].value.lower() in self._TIME_MARKERS:
                return None
            nxt = tokens[base_i + 1] if base_i + 1 < len(tokens) else None
            if nxt is not None:
                nv = nxt.value.lower()
                nn = nxt.normalized
                # дальше месяц → обрабатывается _try_date_month
                if any(nv in mw or nn in mw for mw in Keywords.months()):
                    return None
                # дальше день недели → ordinal+weekday (OrdinalDayRecognizer)
                for days in Keywords.days_of_week():
                    if nv in days or nn in days:
                        return None

        year, month = now.year, now.month
        target = self._safe_date(year, month, day)
        if target is None or (self.config.prefer_nearest_future and target.date() < now.date()):
            nm, ny = (month + 1, year) if month < 12 else (1, year + 1)
            # ищем ближайший месяц, где такой день существует
            for _ in range(13):
                cand = self._safe_date(ny, nm, day)
                if cand is not None:
                    target = cand
                    break
                nm, ny = (nm + 1, ny) if nm < 12 else (1, ny + 1)
        if target is None:
            return None
        lead_deadline = i > 0 and tokens[i - 1].normalized in (Keywords.TIME_TO + Keywords.TIME_BY)
        if lead_deadline:
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=target.replace(hour=23, minute=59),
                has_time=False,
                is_deadline=True,
                start=tokens[i - 1].start,
                end=tokens[end_i].end,
                confidence=0.9,
            )
            return (dt, end_i - i + 1)
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=target,
            date_to=target.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            start=t.start,
            end=tokens[end_i].end,
            confidence=0.88,
        )
        return (dt, end_i - i + 1)

    def _try_relative(self, tokens, i, now):
        """сегодня, завтра, послезавтра, вчера"""
        t = tokens[i]
        v = t.value.lower()
        n = t.normalized
        if v in Keywords.TODAY or n in Keywords.TODAY:
            target = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.99,
                ),
                1,
            )
        if v in Keywords.TOMORROW or n in Keywords.TOMORROW:
            target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.99,
                ),
                1,
            )
        if v in Keywords.AFTER_TOMORROW or n in Keywords.AFTER_TOMORROW:
            target = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.99,
                ),
                1,
            )
        if v in Keywords.YESTERDAY or n in Keywords.YESTERDAY:
            target = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.99,
                    is_past=True,
                ),
                1,
            )
        if v in Keywords.BEFORE_YESTERDAY or n in Keywords.BEFORE_YESTERDAY:
            target = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.99,
                    is_past=True,
                ),
                1,
            )
        return None

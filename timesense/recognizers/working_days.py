"""Через N рабочих дней"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class WorkingDaysRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_before_end_of_month(tokens, i, now) or self._try_parse(tokens, i, now)
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _is_working_day(self, d):
        cal = getattr(self.config, "calendar", None)
        if cal is not None:
            return cal.is_working_day(d.date() if hasattr(d, "date") else d)
        return d.weekday() < 5

    def _try_before_end_of_month(self, tokens, i, now):
        """за N [рабочих] дн(я|ей) до конца месяца → отступить N (рабочих) дней
        назад от последнего дня месяца (строго ДО него). Цель 09:00.
        Рабочие дни учитывают WorkingCalendar (праздники, рабочие субботы)."""
        from calendar import monthrange
        if tokens[i].value.lower() != "за":
            return None
        if i + 4 >= len(tokens):
            return None
        num = (
            int(tokens[i + 1].value)
            if tokens[i + 1].value.isdigit()
            else Keywords.parse_number_word(tokens[i + 1].value, self.morph)
        )
        if num is None:
            return None
        # «за 2 рабочих дня …» или «за 2 дня …» (календарные)
        business = tokens[i + 2].value.lower() in Keywords.WORKING
        k = i + 3 if business else i + 2
        if k + 2 >= len(tokens):
            return None
        if tokens[k].normalized not in Keywords.DAY and tokens[k].value.lower() not in (
            "день",
            "дня",
            "дней",
        ):
            return None
        # «до конца месяца»
        if tokens[k + 1].value.lower() not in Keywords.TIME_TO:
            return None
        if tokens[k + 2].value.lower() not in ("конца", "конце", "конец"):
            return None
        end_i = k + 2
        if k + 3 < len(tokens) and (
            tokens[k + 3].normalized in Keywords.MONTH
            or tokens[k + 3].value.lower() in Keywords.MONTH
        ):
            end_i = k + 3
        else:
            return None  # «за 2 дня до конца недели/года» — не этот случай
        # последний день текущего месяца (если прошёл — следующий)
        year, month = now.year, now.month
        last = monthrange(year, month)[1]
        target = now.replace(
            year=year, month=month, day=last, hour=9, minute=0, second=0, microsecond=0
        )
        if target.date() < now.date():
            month2 = month + 1
            year2 = year + (1 if month2 > 12 else 0)
            month2 = (month2 - 1) % 12 + 1
            last2 = monthrange(year2, month2)[1]
            target = target.replace(year=year2, month=month2, day=last2)
        # отступаем N (рабочих) дней строго назад
        if business:
            stepped = 0
            while stepped < num:
                target -= timedelta(days=1)
                if self._is_working_day(target):
                    stepped += 1
        else:
            target -= timedelta(days=num)
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=False,
            all_day=True,
            start=tokens[i].start,
            end=tokens[end_i].end,
            confidence=0.9,
        )
        return (dt, end_i - i + 1)

    def _try_parse(self, tokens, i, now):
        if tokens[i].value.lower() not in Keywords.AFTER:
            return None
        if i + 3 >= len(tokens):
            return None
        num = (
            int(tokens[i + 1].value)
            if tokens[i + 1].value.isdigit()
            else Keywords.parse_number_word(tokens[i + 1].value, self.morph)
        )
        if num is None:
            return None
        if tokens[i + 2].value.lower() not in Keywords.WORKING:
            return None
        if tokens[i + 3].normalized not in Keywords.DAY and tokens[i + 3].value.lower() not in [
            "день",
            "дня",
            "дней",
        ]:
            return None
        target = now
        added = 0
        while added < num:
            target += timedelta(days=1)
            if target.weekday() < 5:
                added += 1
        target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=False,
            all_day=True,
            start=tokens[i].start,
            end=tokens[i + 3].end,
            confidence=0.9,
        )
        return (dt, 4)

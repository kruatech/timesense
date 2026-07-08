"""не позднее пятницы, крайний срок - пятница"""

from datetime import datetime, timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class DeadlineSynonymRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_no_later(tokens, i, now)
                or self._try_term(tokens, i, now)
                or self._try_during(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_during(self, tokens, i, now):
        """в течение часа / в течение 2 дней — дедлайн = now + Δ"""
        if tokens[i].value.lower() not in Keywords.DURING:
            return None
        start_i = i
        if i > 0 and tokens[i - 1].value.lower() == "в":
            start_i = i - 1
        j = i + 1
        if j >= len(tokens):
            return None
        num = 1
        if tokens[j].value.isdigit():
            num = int(tokens[j].value)
            j += 1
        elif Keywords.parse_number_word(tokens[j].value, self.morph) is not None:
            num = Keywords.parse_number_word(tokens[j].value, self.morph)
            j += 1
        if j >= len(tokens):
            return None
        uv = tokens[j].value.lower()
        un = tokens[j].normalized
        if un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
            delta = timedelta(minutes=num)
        elif un in Keywords.HOUR or uv in ["час", "часа", "часов", "часу"]:
            delta = timedelta(hours=num)
        elif un in Keywords.DAY or uv in ["день", "дня", "дней"]:
            delta = timedelta(days=num)
        elif un in Keywords.WEEK or uv in ["неделю", "недели", "недель", "неделя"]:
            delta = timedelta(weeks=num)
        else:
            return None
        target = now + delta
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[start_i].start,
            end=tokens[j].end,
            confidence=0.85,
        )
        return (dt, j - i + 1)

    def _try_no_later(self, tokens, i, now):
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in Keywords.NOT_WORD:
            return None
        if tokens[i + 1].value.lower() not in Keywords.DEADLINE_NO_LATER:
            return None
        target, ei = self._find_date(tokens, i + 2, now)
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.9,
        )
        return (dt, ei - i + 1)

    def _try_term(self, tokens, i, now):
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in Keywords.DEADLINE_LATEST:
            return None
        if tokens[i + 1].value.lower() not in Keywords.DEADLINE_TERM:
            return None
        ni = i + 2
        if ni < len(tokens) and tokens[ni].value in ["-", "\u2014", "\u2013"]:
            ni += 1
        if ni >= len(tokens):
            return None
        target, ei = self._find_date(tokens, ni, now)
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.9,
        )
        return (dt, ei - i + 1)

    def _find_date(self, tokens, start, now):
        if start >= len(tokens):
            return (None, start)
        t = tokens[start]
        for wi, days in enumerate(Keywords.days_of_week()):
            if t.normalized in days or t.value.lower() in days:
                da = (wi - now.weekday()) % 7
                if da <= 0:
                    da += 7
                target = (now + timedelta(days=da)).replace(
                    hour=23, minute=59, second=0, microsecond=0
                )
                return (target, start)
        if t.normalized in Keywords.TOMORROW:
            return (
                (now + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0),
                start,
            )
        m = re.match(r"^(\d+)-?(?:го)?$", t.value)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                month = now.month
                year = now.year
                target = datetime(year, month, day, 23, 59, 0)
                if target < now:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                    target = datetime(year, month, day, 23, 59, 0)
                return (target, start)
        return (None, start)

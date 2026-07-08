"""Распознавание длительности: на 2 часа, встреча 30 минут"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class DurationRecognizer(Recognizer):
    """Парсит длительность: 'на 2 часа', 'встреча 30 минут', 'полчаса'"""

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_on_duration(tokens, i, now) or self._try_polchasa(tokens, i, now)
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_on_duration(self, tokens, i, now):
        """на N часов/минут"""
        if tokens[i].value.lower() != "на":
            return None
        if i + 2 >= len(tokens):
            return None
        nt = tokens[i + 1]
        num = (
            int(nt.value)
            if nt.value.isdigit()
            else Keywords.parse_number_word(nt.value, self.morph)
        )
        if num is None or num <= 0:
            return None
        ut = tokens[i + 2]
        uv = ut.value.lower()
        un = ut.normalized
        mins = None
        if un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
            mins = num
        elif un in Keywords.HOUR or uv in ["час", "часа", "часов"]:
            mins = num * 60
        if mins is None:
            return None
        # This is a duration marker - attach it as metadata to the token
        # We create a special token with duration info
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=now + timedelta(minutes=mins),
            has_time=False,
            start=tokens[i].start,
            end=ut.end,
            confidence=0.8,
        )
        dt._is_duration = True
        dt._duration_minutes = mins
        return (dt, 3)

    def _try_polchasa(self, tokens, i, now):
        """полчаса, полтора часа"""
        v = tokens[i].value.lower()
        if v == "полчаса":
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=now + timedelta(minutes=30),
                has_time=False,
                start=tokens[i].start,
                end=tokens[i].end,
                confidence=0.85,
            )
            dt._is_duration = True
            dt._duration_minutes = 30
            return (dt, 1)
        if v == "полтора" and i + 1 < len(tokens):
            ut = tokens[i + 1].value.lower()
            if ut in ["час", "часа", "часов"]:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=now + timedelta(minutes=90),
                    has_time=False,
                    start=tokens[i].start,
                    end=tokens[i + 1].end,
                    confidence=0.85,
                )
                dt._is_duration = True
                dt._duration_minutes = 90
                return (dt, 2)
        return None

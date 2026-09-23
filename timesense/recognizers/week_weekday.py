"""День недели внутри названной недели.

«на следующей неделе в среду», «в среду на следующей неделе»,
«на этой неделе в пятницу», «на прошлой неделе в четверг»,
«на позапрошлой неделе во вторник».

Неделя — календарная (Пн–Вс): «на следующей неделе в среду» = среда
следующей календарной недели. Это отличается от «в следующую среду»
(ближайшая среда + неделя) — ту форму разбирает WeekdayModifierRecognizer.

Выдаёт all-day дату; время («в 11») присоединяет общий merge парсера.
"""

from datetime import timedelta

from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class WeekWeekdayRecognizer(Recognizer):
    _PREPS_WEEK = ("на", "в")
    _PREPS_DAY = ("в", "во")

    def _week_offset(self, tok):
        v, n = tok.value.lower(), tok.normalized
        if v in Keywords.NEXT or n in Keywords.NEXT:
            return 1
        if v in Keywords.PREVIOUS2_MOD or n in Keywords.PREVIOUS2_MOD:
            return -2
        if v in Keywords.PREVIOUS_MOD or n in Keywords.PREVIOUS_MOD:
            return -1
        if v in Keywords.CURRENT or n in Keywords.CURRENT:
            return 0
        return None

    @staticmethod
    def _weekday(tok):
        v, n = tok.value.lower(), tok.normalized
        for wi, days in enumerate(Keywords.days_of_week()):
            if v in days or n in days:
                return wi
        return None

    def _week_phrase(self, tokens, i):
        """[на|в] MOD неделе → (offset, index_after) | None."""
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in self._PREPS_WEEK:
            return None
        off = self._week_offset(tokens[i + 1])
        if off is None:
            return None
        w = tokens[i + 2]
        if w.value.lower() not in Keywords.WEEK and w.normalized not in Keywords.WEEK:
            return None
        return off, i + 3

    def _day_phrase(self, tokens, i):
        """[в|во]? <день> → (weekday, index_after) | None."""
        if i >= len(tokens):
            return None
        j = i
        if tokens[j].value.lower() in self._PREPS_DAY:
            j += 1
        if j >= len(tokens):
            return None
        wd = self._weekday(tokens[j])
        if wd is None:
            return None
        return wd, j + 1

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            found = None
            wp = self._week_phrase(tokens, i)
            if wp is not None:
                dp = self._day_phrase(tokens, wp[1])
                if dp is not None:
                    found = (wp[0], dp[0], i, dp[1] - 1)
            if found is None:
                dp = self._day_phrase(tokens, i)
                if dp is not None:
                    wp = self._week_phrase(tokens, dp[1])
                    if wp is not None:
                        found = (wp[0], dp[0], i, wp[1] - 1)
            if found is None:
                i += 1
                continue
            off, wd, si, ei = found
            monday = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            target = monday + timedelta(days=7 * off + wd)
            results.append(
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=target,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=tokens[si].start,
                    end=tokens[ei].end,
                    confidence=0.97,
                    is_past=target.replace(hour=23, minute=59) < now,
                )
            )
            i = ei + 1
        return results

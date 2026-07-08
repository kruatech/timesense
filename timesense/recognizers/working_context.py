"""в рабочее/нерабочее время, после работы"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class WorkingContextRecognizer(Recognizer):
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
        ws = self.config.working_hours["start"]
        we = self.config.working_hours["end"]
        # в рабочее/нерабочее время
        if i + 2 < len(tokens) and tokens[i].normalized == "в":
            adj = tokens[i + 1].value.lower()
            if tokens[i + 2].value.lower() in Keywords.WORK_TIME:
                if adj in Keywords.WORKING:
                    s = now.replace(hour=ws, minute=0, second=0, microsecond=0)
                    e = now.replace(hour=we, minute=0, second=0, microsecond=0)
                    if self.config.prefer_nearest_future and e < now:
                        s += timedelta(days=1)
                        e += timedelta(days=1)
                    # «рабочее время» в выходной → ближайший будний день
                    while s.weekday() >= 5:
                        s += timedelta(days=1)
                        e += timedelta(days=1)
                    dt = DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=s,
                        date_to=e,
                        has_time=True,
                        start=tokens[i].start,
                        end=tokens[i + 2].end,
                        confidence=0.8,
                    )
                    dt.is_explicit_range = True
                    return (dt, 3)
                if adj in Keywords.NON_WORKING:
                    s = now.replace(hour=we, minute=0, second=0, microsecond=0)
                    e = now.replace(hour=23, minute=59, second=0, microsecond=0)
                    if self.config.prefer_nearest_future and s < now:
                        s += timedelta(days=1)
                        e += timedelta(days=1)
                    dt = DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=s,
                        date_to=e,
                        has_time=True,
                        start=tokens[i].start,
                        end=tokens[i + 2].end,
                        confidence=0.75,
                    )
                    return (dt, 3)
        # после работы
        if i + 1 < len(tokens) and tokens[i].value.lower() in Keywords.AFTER_PREP:
            if tokens[i + 1].value.lower() in Keywords.AFTER_WORK:
                s = now.replace(hour=we, minute=0, second=0, microsecond=0)
                if self.config.prefer_nearest_future and s < now:
                    s += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=s,
                    date_to=s,
                    has_time=True,
                    start=tokens[i].start,
                    end=tokens[i + 1].end,
                    confidence=0.8,
                )
                dt._open_start = True
                return (dt, 2)
        return None

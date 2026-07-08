"""Распознавание времени суток: утром, днём, вечером, ночью.

Старт каждого интервала берётся из config.time_of_day_hours (если слово
там задано), ширина интервала — фиксированная по «корзине». Это позволяет
переопределять части суток через TimeConfig, не меняя ширину окна.
"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType


class TimeOfDayRecognizer(Recognizer):
    # корзина -> (старт по умолчанию, ширина окна в часах)
    _BUCKET = {"morning": (9, 3), "day": (12, 5), "evening": (18, 4), "night": (22, 8)}
    _WORD_BUCKET = {
        "утром": "morning",
        "утра": "morning",
        "утро": "morning",
        "днём": "day",
        "днем": "day",
        "дня": "day",
        "вечером": "evening",
        "вечера": "evening",
        "вечер": "evening",
        "ночью": "night",
        "ночи": "night",
        "ночь": "night",
    }

    def recognize(self, tokens, now):
        results = []
        cfg = getattr(self.config, "time_of_day_hours", None) or {}
        for t in tokens:
            v = t.value.lower()
            bucket = self._WORD_BUCKET.get(v)
            if not bucket:
                continue
            default_start, width = self._BUCKET[bucket]
            start_h = cfg.get(v, default_start)
            try:
                start_h = int(start_h)
            except (TypeError, ValueError):
                start_h = default_start
            s = now.replace(hour=start_h % 24, minute=0, second=0, microsecond=0)
            e = s + timedelta(hours=width)
            if self.config.prefer_nearest_future and s < now:
                s += timedelta(days=1)
                e += timedelta(days=1)
            results.append(
                DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=s,
                    date_to=e,
                    has_time=True,
                    fuzzy=True,
                    start=t.start,
                    end=t.end,
                    confidence=0.75,
                )
            )
        return results

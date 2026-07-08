"""Пользовательские времена из конфига"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType


class CustomTimeRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        for t in tokens:
            ct = self.config.get_custom_time(t.value)
            if ct:
                h, m = ct if isinstance(ct, tuple) else (ct, 0)
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if self.config.prefer_nearest_future and target < now:
                    target += timedelta(days=1)
                results.append(
                    DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=target,
                        date_to=target,
                        has_time=True,
                        start=t.start,
                        end=t.end,
                        confidence=0.9,
                    )
                )
        return results

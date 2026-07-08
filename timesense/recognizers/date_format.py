"""Распознавание дат в форматах: 2026-01-10, 10.01.2026"""

from datetime import datetime
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType


class DateFormatRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        for t in tokens:
            tok = None
            m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$", t.value)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100:
                    y += 2000
                tok = self._mk(d, mo, y, now, t)
            elif re.match(r"^\d{1,2}[./]\d{1,2}$", t.value):
                m = re.match(r"^(\d{1,2})[./](\d{1,2})$", t.value)
                d, mo = int(m.group(1)), int(m.group(2))
                if 1 <= mo <= 12:
                    cand = self._safe(d, mo, now.year)
                    if (
                        cand is not None
                        and self.config.prefer_nearest_future
                        and cand.date() < now.date()
                    ):
                        cand = self._safe(d, mo, now.year + 1)
                    if cand is not None:
                        tok = self._token(cand, now, t)
            else:
                m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", t.value)
                if m:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    tok = self._mk(d, mo, y, now, t)
            if tok is not None:
                results.append(tok)
        return results

    @staticmethod
    def _safe(d, mo, y):
        try:
            return datetime(y, mo, d, 0, 0, 0)
        except ValueError:
            return None

    def _token(self, target, now, t):
        return DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=target,
            date_to=target.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            start=t.start,
            end=t.end,
            confidence=0.99,
            is_past=target.date() < now.date(),
        )

    def _mk(self, d, mo, y, now, t):
        if not (1 <= mo <= 12 and 2000 <= y <= 2100):
            return None
        target = self._safe(d, mo, y)
        return self._token(target, now, t) if target is not None else None

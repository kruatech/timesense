"""после X (OPEN_START): после 18:00, после обеда"""

from datetime import timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class OpenStartRecognizer(Recognizer):
    TOD_MAP = {"обеда": 13, "обед": 13, "завтрака": 10, "ужина": 20, "работы": 18, "школы": 15}

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
        if tokens[i].value.lower() not in Keywords.AFTER_PREP:
            return None
        if i + 1 >= len(tokens):
            return None
        nt = tokens[i + 1]
        nv = nt.value.lower()
        # после HH:MM → open_start (start=HH:MM, «не раньше», не точный reminder)
        m = re.match(r"(\d{1,2})[:.-](\d{2})", nt.value)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                df = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                if self.config.prefer_nearest_future and df < now:
                    df += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=df,
                    date_to=df,
                    has_time=True,
                    start=tokens[i].start,
                    end=nt.end,
                    confidence=0.9,
                )
                dt._open_start = True
                return (dt, 2)
        # после N — голое число, остаётся open_start
        if nt.value.isdigit():
            h = int(nt.value)
            if 0 <= h <= 23:
                if 1 <= h <= 7:
                    h += 12
                df = now.replace(hour=h, minute=0, second=0, microsecond=0)
                if self.config.prefer_nearest_future and df < now:
                    df += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=df,
                    date_to=df,
                    has_time=True,
                    start=tokens[i].start,
                    end=nt.end,
                    confidence=0.85,
                )
                dt._open_start = True
                return (dt, 2)
        # после обеда/работы — размытое время, open_start
        if nv in self.TOD_MAP:
            h = self.TOD_MAP[nv]
            df = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if self.config.prefer_nearest_future and df < now:
                df += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=df,
                date_to=df,
                has_time=True,
                start=tokens[i].start,
                end=nt.end,
                confidence=0.8,
            )
            dt._open_start = True
            return (dt, 2)
        tod = {"утра": 12, "вечера": 22}
        if nv in tod:
            df = now.replace(hour=tod[nv], minute=0, second=0, microsecond=0)
            if self.config.prefer_nearest_future and df < now:
                df += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=df,
                date_to=df,
                has_time=True,
                start=tokens[i].start,
                end=nt.end,
                confidence=0.75,
            )
            dt._open_start = True
            return (dt, 2)
        return None

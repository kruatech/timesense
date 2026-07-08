"""Модели для распознанных дат/времени"""

from datetime import datetime
from enum import Enum


class DateTimeType(Enum):
    FIXED = "fixed"
    PERIOD = "period"
    SPAN_FORWARD = "span_forward"
    SPAN_BACKWARD = "span_backward"


class RecurrenceRule:
    def __init__(
        self,
        frequency,
        interval=1,
        by_day=None,
        by_month=None,
        by_month_day=None,
        until=None,
        count=None,
        by_set_pos=None,
    ):
        self.frequency = frequency
        self.interval = interval
        self.by_day = by_day or []
        self.by_month = by_month or []
        self.by_month_day = by_month_day or []
        self.until = until
        self.count = count
        self.by_set_pos = by_set_pos  # BYSETPOS (напр. -1 = последний из BYDAY-набора)

    def to_rrule(self):
        parts = ["FREQ=" + self.frequency]
        if self.interval > 1:
            parts.append("INTERVAL=" + str(self.interval))
        if self.by_day:
            parts.append("BYDAY=" + ",".join(self.by_day))
        if self.by_month:
            parts.append("BYMONTH=" + ",".join(str(m) for m in self.by_month))
        if self.by_month_day:
            parts.append("BYMONTHDAY=" + ",".join(str(d) for d in self.by_month_day))
        if self.by_set_pos is not None:
            parts.append("BYSETPOS=" + str(self.by_set_pos))
        if self.until:
            parts.append(
                "UNTIL=" + self.until.strftime("%Y%m%dT%H%M%S")
            )  # naive: без Z (UTC не заявляем)
        if self.count:
            parts.append("COUNT=" + str(self.count))
        return ";".join(parts)

    def to_dict(self):
        d = {
            "frequency": self.frequency,
            "interval": self.interval,
            "by_day": self.by_day,
            "until": self.until.isoformat() if self.until else None,
            "count": self.count,
            "rrule": self.to_rrule(),
        }
        if self.by_month:
            d["by_month"] = self.by_month
        if self.by_month_day:
            d["by_month_day"] = self.by_month_day
        return d


class DateTimeToken:
    def __init__(
        self,
        type=None,
        date_from=None,
        date_to=None,
        has_time=False,
        all_day=False,
        fuzzy=False,
        fuzzy_tolerance=0,
        recurrence=None,
        start=0,
        end=0,
        is_deadline=False,
        confidence=1.0,
        is_past=False,
        exclusions=None,
    ):
        self.type = type or DateTimeType.FIXED
        self.date_from = date_from or datetime.now()
        self.date_to = date_to or self.date_from
        self.has_time = has_time
        self.all_day = all_day
        self.fuzzy = fuzzy
        self.fuzzy_tolerance = fuzzy_tolerance
        self.recurrence = recurrence
        self.start = start
        self.end = end
        self.is_deadline = is_deadline
        self.is_explicit_range = False
        self.confidence = confidence
        self.is_past = is_past
        self.exclusions = exclusions or []
        self._open_start = False

    @property
    def duration_minutes(self):
        if self.date_from and self.date_to:
            return int((self.date_to - self.date_from).total_seconds() / 60)
        return None

    def to_dict(self):
        return {
            "type": self.type.value,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "has_time": self.has_time,
            "all_day": self.all_day,
            "fuzzy": self.fuzzy,
            "duration_minutes": self.duration_minutes,
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "confidence": self.confidence,
            "is_past": self.is_past,
            "is_deadline": self.is_deadline,
            "exclusions": [e.to_dict() for e in self.exclusions] if self.exclusions else [],
        }

    def __repr__(self):
        return "DateTimeToken(type=%s, from=%s, to=%s, conf=%.2f)" % (
            self.type.value,
            self.date_from.strftime("%Y-%m-%d %H:%M"),
            self.date_to.strftime("%Y-%m-%d %H:%M"),
            self.confidence,
        )

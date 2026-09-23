"""Типы событий: Reminder, Calendar, Task"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    REMINDER = "reminder"
    CALENDAR = "calendar"
    TASK = "task"


class TaskType(Enum):
    PERIOD = "period"
    DEADLINE = "deadline"
    OPEN_START = "open_start"
    FUZZY = "fuzzy"


class BaseEvent(ABC):
    def __init__(
        self,
        title: str,
        source: str,
        start: Any = 0,
        end: Any = 0,
        confidence: float = 1.0,
        is_past: bool = False,
        location: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        recurrence: Optional[Any] = None,
        exclusions: Optional[List[Any]] = None,
    ) -> None:
        self.title = title
        self.source = source
        self.start = start
        self.end = end
        self.confidence = confidence
        self.is_past = is_past
        self.location = location
        self.duration_minutes = duration_minutes
        self.recurrence = recurrence
        self.exclusions = exclusions or []
        self.detected_language = None

    @property
    @abstractmethod
    def event_type(self) -> EventType:
        pass

    @property
    def when(self) -> Optional[datetime]:
        """Главный момент результата любого типа: время напоминания, дедлайн
        или начало события/периода. Удобно для планировщика бота."""
        for f in ("datetime_at", "deadline", "start_at"):
            v = getattr(self, f, None)
            if v is not None:
                return v
        return None

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass

    def to_ics(self, **kwargs: Any) -> str:
        """Экспорт события в iCalendar (.ics, RFC 5545).
        Открывается в Google Calendar, Apple Calendar, Outlook.
        kwargs: stamp=..., alarm_minutes=N (напоминание за N минут)."""
        from ..ics import to_ics as _to_ics
        return _to_ics(self, **kwargs)

    @abstractmethod
    def human_readable(self) -> str:
        pass

    def summary(self) -> str:
        """Единая строка-разбор для любого типа результата: видно вид события,
        начало, конец, длительность, повтор и название.

            reminder            23.09.2026 10:00                      «встреча»
            calendar            23.09.2026 10:00 → 11:30  (90 мин)    «созвон»
            task/deadline       до 25.09.2026 23:59                   «отчёт»
            task/period         23.09.2026 09:00 → 12:00              «в садик»
            reminder ⟳ FREQ=…   28.09.2026 10:00                      «планёрка»
        """
        # подписи — на языке фразы: русская фраза → русские подписи, английская → английские
        en = self.detected_language == "en"
        L = {
            "except": "except" if en else "кроме",
            "by": "by" if en else "до",
            "all_day": "all day" if en else "весь день",
            "since": "from" if en else "с",
            "min": "min" if en else "мин",
            "fuzzy": "~approx" if en else "~примерно",
            "past": "PAST" if en else "ПРОШЛО",
        }
        kind = self.event_type.value
        tt = getattr(self, "task_type", None)
        if tt is not None:
            kind += "/" + getattr(tt, "value", str(tt))
        if self.recurrence is not None:
            kind += " ⟳ " + self.recurrence.to_rrule()
            exd = getattr(self.recurrence, "exdates", None) or []
            if exd:
                kind += " %s " % L["except"] + ", ".join(x.strftime("%d.%m.%Y") for x in exd)

        def f(dt: Optional[datetime]) -> str:
            if dt is None:
                return "—"
            out = dt.strftime("%d.%m.%Y %H:%M")
            if dt.tzinfo is not None:
                out += dt.strftime(" %z")
            return out

        start, end = getattr(self, "start_at", None), getattr(self, "end_at", None)
        deadline = getattr(self, "deadline", None)
        if deadline is not None:
            when = L["by"] + " " + f(deadline)
        elif start is not None and end is not None and start == end and self.recurrence is None:
            when = f(start)
        elif start is not None and end is not None and start == end:
            # повтор без времени: соглашение данных — start == end в полночь
            if (start.hour, start.minute) == (0, 0):
                when = start.strftime("%d.%m.%Y") + (start.strftime(" %z") if start.tzinfo else "") + \
                    "  " + L["all_day"]
            else:
                when = L["since"] + " " + f(start)
        elif start is not None and end is not None:
            same_day = start.date() == end.date()
            when = f(start) + " → " + (end.strftime("%H:%M") if same_day else f(end))
        else:
            when = f(self.when)
        parts = [kind, when]
        if self.duration_minutes:
            parts.append("(%d %s)" % (self.duration_minutes, L["min"]))
        if getattr(self, "fuzzy", False):
            parts.append(L["fuzzy"])
        if self.is_past:
            parts.append(L["past"])
        if self.location:
            parts.append("@" + self.location)
        parts.append("«%s»" % (self.title or ""))
        return "  ".join(parts)

    def _base_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.event_type.value,
            "title": self.title,
            "source": self.source,
            "confidence": self.confidence,
            "is_past": self.is_past,
        }
        if self.detected_language:
            d["language"] = self.detected_language
        if self.location:
            d["location"] = self.location
        if self.duration_minutes:
            d["duration_minutes"] = self.duration_minutes
        if self.recurrence:
            d["recurrence"] = self.recurrence.to_dict()
        if self.exclusions:
            d["exclusions"] = [str(e) for e in self.exclusions]
        return d


class ReminderResult(BaseEvent):
    def __init__(self, title: str, source: str, datetime_at: datetime, **kw: Any) -> None:
        super().__init__(title, source, **kw)
        self.datetime_at = datetime_at

    @property
    def event_type(self) -> EventType:
        return EventType.REMINDER

    def to_dict(self) -> Dict[str, Any]:
        d = self._base_dict()
        d["datetime"] = self.datetime_at.isoformat()
        return d

    def human_readable(self) -> str:
        return self.datetime_at.strftime("%d.%m.%Y %H:%M")

    def __repr__(self) -> str:
        return "Reminder('%s' @ %s)" % (self.title, self.datetime_at.strftime("%Y-%m-%d %H:%M"))


class CalendarResult(BaseEvent):
    def __init__(self, title: str, source: str, start_at: datetime, end_at: datetime, **kw: Any) -> None:
        super().__init__(title, source, **kw)
        self.start_at = start_at
        self.end_at = end_at
        if not self.duration_minutes:
            self.duration_minutes = int((end_at - start_at).total_seconds() / 60)

    @property
    def event_type(self) -> EventType:
        return EventType.CALENDAR

    def to_dict(self) -> Dict[str, Any]:
        d = self._base_dict()
        d["start"] = self.start_at.isoformat()
        d["end"] = self.end_at.isoformat()
        d["duration_minutes"] = self.duration_minutes
        return d

    def human_readable(self) -> str:
        if self.start_at.date() == self.end_at.date():
            return "%s %s-%s" % (
                self.start_at.strftime("%d.%m.%Y"),
                self.start_at.strftime("%H:%M"),
                self.end_at.strftime("%H:%M"),
            )
        return "%s - %s" % (
            self.start_at.strftime("%d.%m.%Y %H:%M"),
            self.end_at.strftime("%d.%m.%Y %H:%M"),
        )

    def __repr__(self) -> str:
        return "Calendar('%s' %s-%s)" % (
            self.title,
            self.start_at.strftime("%H:%M"),
            self.end_at.strftime("%H:%M"),
        )


class TaskResult(BaseEvent):
    def __init__(
        self,
        title: str,
        source: str,
        task_type: TaskType,
        start_at: Optional[datetime] = None,
        end_at: Optional[datetime] = None,
        deadline: Optional[datetime] = None,
        fuzzy: bool = False,
        **kw: Any,
    ) -> None:
        super().__init__(title, source, **kw)
        self.task_type = task_type
        self.start_at = start_at
        self.end_at = end_at
        self.deadline = deadline
        self.fuzzy = fuzzy

    @property
    def event_type(self) -> EventType:
        return EventType.TASK

    def to_dict(self) -> Dict[str, Any]:
        d = self._base_dict()
        d["task_type"] = self.task_type.value
        d["fuzzy"] = self.fuzzy
        if self.start_at:
            d["start"] = self.start_at.isoformat()
        if self.end_at:
            d["end"] = self.end_at.isoformat()
        if self.deadline:
            d["deadline"] = self.deadline.isoformat()
        return d

    # подписи на языке фразы (detected_language)
    _HR_WORDS = {
        "ru": {"by": "до ", "after": "после ", "soon": "в ближайшее время"},
        "en": {"by": "by ", "after": "after ", "soon": "soon"},
    }

    def human_readable(self) -> str:
        w = self._HR_WORDS.get(self.detected_language or "ru", self._HR_WORDS["ru"])
        if self.task_type == TaskType.DEADLINE and self.deadline:
            return w["by"] + self.deadline.strftime("%d.%m.%Y %H:%M")
        if self.task_type == TaskType.OPEN_START and self.start_at:
            return w["after"] + self.start_at.strftime("%H:%M")
        if self.task_type in (TaskType.PERIOD, TaskType.FUZZY) and self.start_at and self.end_at:
            s, e = self.start_at, self.end_at
            if s.date() != e.date():
                # многодневный период: «26.09.2026 - 27.09.2026»
                return "%s - %s" % (s.strftime("%d.%m.%Y"), e.strftime("%d.%m.%Y"))
            if (s.hour, s.minute) == (0, 0) and (e.hour, e.minute) in ((23, 59), (0, 0)):
                return s.strftime("%d.%m.%Y")  # весь день
            return "%s %s-%s" % (s.strftime("%d.%m.%Y"), s.strftime("%H:%M"), e.strftime("%H:%M"))
        if self.task_type == TaskType.FUZZY:
            return w["soon"]
        return self.source

    def __repr__(self) -> str:
        return "Task('%s' type=%s)" % (self.title, self.task_type.value)

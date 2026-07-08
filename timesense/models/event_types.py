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

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass

    def to_ics(self) -> str:
        """Экспорт события в iCalendar (.ics, RFC 5545).
        Открывается в Google Calendar, Apple Calendar, Outlook."""
        from ..ics import to_ics as _to_ics
        return _to_ics(self)

    @abstractmethod
    def human_readable(self) -> str:
        pass

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

    def human_readable(self) -> str:
        if self.task_type == TaskType.DEADLINE and self.deadline:
            return "до " + self.deadline.strftime("%d.%m.%Y %H:%M")
        if self.task_type == TaskType.OPEN_START and self.start_at:
            return "после " + self.start_at.strftime("%H:%M")
        if self.task_type == TaskType.PERIOD and self.start_at and self.end_at:
            return "%s-%s" % (self.start_at.strftime("%H:%M"), self.end_at.strftime("%H:%M"))
        if self.task_type == TaskType.FUZZY:
            return "в ближайшее время"
        return self.source

    def __repr__(self) -> str:
        return "Task('%s' type=%s)" % (self.title, self.task_type.value)

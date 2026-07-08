"""Конфигурация парсера"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Tuple

if TYPE_CHECKING:
    from .calendar import WorkingCalendar


class TimeConfig:
    def __init__(
        self,
        prefer_nearest_future: bool = True,
        default_hour_for_one: int = 13,
        time_of_day_hours: Optional[Dict[str, int]] = None,
        custom_times: Optional[Dict[str, Tuple[int, int]]] = None,
        relative_offsets: Optional[Dict[str, str]] = None,
        timezone: str = "Europe/Moscow",
        working_hours: Optional[Dict[str, int]] = None,
        merge_distance: int = 50,
        default_language: str = "auto",
        calendar: Optional[WorkingCalendar] = None,
    ) -> None:
        self.prefer_nearest_future = prefer_nearest_future
        self.default_hour_for_one = default_hour_for_one
        self.timezone = timezone
        self.merge_distance = merge_distance
        # Производственный календарь (праздники/перенесённые рабочие дни) —
        # влияет на логику «рабочий день / business day». None → обычные Пн–Пт.
        self.calendar = calendar
        # Язык парсинга: "auto" (определять по тексту), "ru", "en".
        if default_language not in ("auto", "ru", "en"):
            raise ValueError(
                "default_language must be 'auto', 'ru' or 'en', got %r" % (default_language,)
            )
        self.default_language = default_language
        self.time_of_day_hours = time_of_day_hours or {
            "утром": 9,
            "утра": 9,
            "утро": 9,
            "днём": 12,
            "днем": 12,
            "дня": 12,
            "вечером": 18,
            "вечера": 18,
            "вечер": 18,
            "ночью": 22,
            "ночи": 22,
            "ночь": 22,
        }
        self.custom_times = custom_times or {}
        self.relative_offsets = relative_offsets or {}
        self.working_hours = working_hours or {"start": 9, "end": 18}

    def get_custom_time(self, word: str) -> Optional[Tuple[int, int]]:
        return self.custom_times.get(word.lower())

    @classmethod
    def default(cls) -> TimeConfig:
        return cls()

    @classmethod
    def strict(cls) -> TimeConfig:
        return cls(prefer_nearest_future=False, default_hour_for_one=1)

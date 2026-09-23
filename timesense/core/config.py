"""Конфигурация парсера"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

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
        use_morph: Optional[bool] = None,
        max_text_length: Optional[int] = 1000,
        default_tz: Optional[Any] = None,
    ) -> None:
        self.prefer_nearest_future = prefer_nearest_future
        self.default_hour_for_one = default_hour_for_one
        self.timezone = timezone
        self.merge_distance = merge_distance
        # Морфология: None — авто (pymorphy3, если установлен; TIMESENSE_MORPH=0
        # выключает), False — без неё (быстрее и легче), True — попытаться включить.
        self.use_morph = use_morph
        # Защита от тяжёлого ввода: длиннее → parse() возвращает None.
        # None/0 — без ограничения.
        if max_text_length is not None and max_text_length < 0:
            raise ValueError("max_text_length must be >= 0 or None")
        self.max_text_length = max_text_length
        # Пояс пользователя по умолчанию ('Europe/Moscow' или tzinfo): применяется,
        # когда в parse() не передан tz. None — naive-режим (как раньше).
        # Параметр timezone выше исторический и НЕ применяется — используйте default_tz.
        if default_tz is not None:
            from .tz import resolve_tz

            resolve_tz(default_tz)  # ранняя проверка: неизвестный пояс → ValueError
        self.default_tz = default_tz
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

"""Производственный календарь: праздники (нерабочие дни) и перенесённые
рабочие дни (рабочие субботы/воскресенья). Загружается пользователем и
подключается через TimeConfig(calendar=...). Влияет на всю логику
«рабочий день / business day».

Пример:
    from timesense import WorkingCalendar, TimeConfig, TimeSenseParser
    cal = WorkingCalendar(
        holidays=["2026-01-01", "2026-01-02", "2026-02-23", "2026-03-09"],
        working_weekends=["2026-02-28"],   # перенесённая рабочая суббота
        holiday_names={"новый год": "2026-01-01", "new year": "2026-01-01"},
    )
    p = TimeSenseParser(TimeConfig(calendar=cal))
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

DateLike = Union[str, date, datetime]


def _to_date(x: DateLike) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    if isinstance(x, str):
        return datetime.strptime(x.strip(), "%Y-%m-%d").date()
    raise ValueError("Expected date/datetime/'YYYY-MM-DD', got %r" % (x,))


class WorkingCalendar:
    def __init__(
        self,
        holidays: Optional[List[DateLike]] = None,
        working_weekends: Optional[List[DateLike]] = None,
        holiday_names: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.holidays = set(_to_date(x) for x in (holidays or []))
        self.working_weekends = set(_to_date(x) for x in (working_weekends or []))
        self.holiday_names = {}
        for name, dates in (holiday_names or {}).items():
            if not isinstance(dates, (list, tuple, set)):
                dates = [dates]
            self.holiday_names[name.lower()] = sorted(_to_date(d) for d in dates)

    # ── проверки ─────────────────────────────────────────────────────────
    def is_holiday(self, d: DateLike) -> bool:
        return _to_date(d) in self.holidays

    def is_working_day(self, d: DateLike) -> bool:
        dd = _to_date(d)
        if dd in self.working_weekends:
            return True
        if dd in self.holidays:
            return False
        return dd.weekday() < 5

    def is_day_off(self, d: DateLike) -> bool:
        return not self.is_working_day(d)

    # ── навигация ────────────────────────────────────────────────────────
    def next_working_day(self, d: DateLike, inclusive: bool = False) -> date:
        from datetime import timedelta

        cur = _to_date(d)
        if not inclusive:
            cur = cur + timedelta(days=1)
        for _ in range(400):
            if self.is_working_day(cur):
                return cur
            cur += timedelta(days=1)
        return cur

    def prev_working_day(self, d: DateLike, inclusive: bool = False) -> date:
        from datetime import timedelta

        cur = _to_date(d)
        if not inclusive:
            cur = cur - timedelta(days=1)
        for _ in range(400):
            if self.is_working_day(cur):
                return cur
            cur -= timedelta(days=1)
        return cur

    def resolve_holiday(self, name: str, year: Optional[int] = None) -> List[date]:
        """Возвращает список дат для названного праздника (или []).
        Если задан year — фильтрует по году."""
        dates = self.holiday_names.get((name or "").lower().strip(), [])
        if year is not None:
            dates = [d for d in dates if d.year == year]
        return list(dates)

    # ── загрузка ─────────────────────────────────────────────────────────
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkingCalendar:
        return cls(
            holidays=data.get("holidays"),
            working_weekends=data.get("working_weekends"),
            holiday_names=data.get("holiday_names"),
        )

    @classmethod
    def from_json(cls, source: str) -> WorkingCalendar:
        """source — путь к файлу или JSON-строка."""
        import json
        import os

        if isinstance(source, str) and os.path.exists(source):
            with open(source, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(source)
        return cls.from_dict(data)

"""pytest-обёртка над полным набором проверок + тесты новых возможностей."""

from datetime import datetime

from timesense import TimeSenseParser, TimeConfig, WorkingCalendar
from timesense.models.event_types import ReminderResult, TaskResult
from timesense.tests.test_fixes import main

NOW = datetime(2026, 2, 14, 14, 0)


def test_full_suite():
    assert main(show_failed_only=True) is True


def test_parse_multi_splits_events():
    p = TimeSenseParser()
    res = p.parse_multi("завтра встреча и в пятницу созвон", now=NOW)
    assert len(res) == 2
    assert sorted(r.title for r in res) == ["встреча", "созвон"]


def test_parse_multi_comma():
    p = TimeSenseParser()
    res = p.parse_multi("в 10 планёрка, в 15 обед", now=NOW)
    assert len(res) == 2
    assert all(isinstance(r, ReminderResult) for r in res)


def test_parse_multi_single():
    p = TimeSenseParser()
    assert len(p.parse_multi("завтра в 10 встреча", now=NOW)) == 1


def test_config_time_of_day_hours_override():
    nb = datetime(2026, 2, 14, 8, 0)
    rb = TimeSenseParser().parse("вечером встреча", now=nb)
    rc = TimeSenseParser(TimeConfig(time_of_day_hours={"вечером": 20})).parse(
        "вечером встреча", now=nb
    )
    assert rb.start_at.hour == 18
    assert rc.start_at.hour == 20


def test_config_relative_offsets():
    p = TimeSenseParser(TimeConfig(relative_offsets={"потом": "+20", "позже": "+2h"}))
    r1 = p.parse("потом позвонить", now=NOW)
    r2 = p.parse("позже встреча", now=NOW)
    assert (
        isinstance(r1, ReminderResult) and r1.datetime_at.hour == 14 and r1.datetime_at.minute == 20
    )
    assert isinstance(r2, ReminderResult) and r2.datetime_at.hour == 16


def test_config_merge_distance():
    text = "завтра очень длинное описание встречи в 10"
    rn = TimeSenseParser(TimeConfig(merge_distance=50)).parse(text, now=NOW)
    rf = TimeSenseParser(TimeConfig(merge_distance=3)).parse(text, now=NOW)
    assert isinstance(rn, ReminderResult) and rn.datetime_at.day == 15 and rn.datetime_at.hour == 10
    assert not (
        isinstance(rf, ReminderResult) and rf.datetime_at.day == 15 and rf.datetime_at.hour == 10
    )


def test_day_of_month_word():
    r = TimeSenseParser().parse("пятнадцатого обед", now=NOW)
    assert isinstance(r, TaskResult) and r.start_at.day == 15


def test_prefer_nearest_future_false():
    p = TimeSenseParser(TimeConfig(prefer_nearest_future=False))
    r = p.parse("в 10 встреча", now=NOW)  # now=14:00; без флипа должно быть 10:00 сегодня
    assert isinstance(r, ReminderResult) and r.datetime_at.day == 14 and r.datetime_at.hour == 10


def test_parse_multi_one_line_with_dates():
    p = TimeSenseParser()
    res = p.parse_multi("завтра в 10 митинг и послезавтра в 14 обед", now=NOW)
    assert len(res) == 2
    assert res[0].datetime_at.day == 15 and res[0].datetime_at.hour == 10
    assert res[1].datetime_at.day == 16 and res[1].datetime_at.hour == 14


def test_exclusion_two_weekdays():
    r = TimeSenseParser().parse("каждый день кроме понедельника и среды зарядка", now=NOW)
    assert r.recurrence and r.recurrence.frequency == "WEEKLY"
    assert "MO" not in r.recurrence.by_day and "WE" not in r.recurrence.by_day
    assert len(r.recurrence.by_day) == 5


def test_leap_year_valid_and_invalid():
    p = TimeSenseParser()
    assert p.parse("29 февраля 2024 событие", now=NOW) is not None
    assert p.parse("29 февраля 2025 событие", now=NOW) is None
    assert p.parse("31 апреля встреча", now=NOW) is None


def test_english_runner_suite():
    """Гейт: полный английский раннер (наглядный) должен быть весь зелёным."""
    from timesense.tests import test_en_fixes

    assert test_en_fixes.main(fail_only=True) is True


def test_language_detection_ru_en():
    from timesense.core.language import detect_language, resolve_language

    assert detect_language("завтра в 10 встреча") == "ru"
    assert detect_language("tomorrow at 10 meeting") == "en"
    assert detect_language("meeting завтра в 10") == "ru"  # смешанный → победитель ru
    assert detect_language("17.02") == "ru"  # неоднозначно → fallback
    # контракт разрешения: явный → config → auto
    assert resolve_language("tomorrow", "ru", "auto") == "ru"  # явный бьёт auto
    assert resolve_language("tomorrow", None, "en") == "en"  # config
    assert resolve_language("tomorrow at 5pm", None, "auto") == "en"


def test_detected_language_recorded():
    r = TimeSenseParser().parse("завтра в 10 встреча", now=NOW)
    assert r.detected_language == "ru"
    assert r.to_dict().get("language") == "ru"


def test_language_explicit_override():
    p = TimeSenseParser()
    assert p.parse("в 10 встреча", now=NOW, language="ru").detected_language == "ru"
    # русский текст при явном language="en" не парсится английской локалью
    assert p.parse("в 10 встреча", now=NOW, language="en") is None


def test_invalid_language_raises():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        TimeConfig(default_language="de")
    p = TimeSenseParser()
    with _pytest.raises(ValueError):
        p.parse("tomorrow at 10", now=NOW, language="fr")
    with _pytest.raises(ValueError):
        p.parse_multi("tomorrow at 10", now=NOW, language="fr")


def test_parse_multi_preserves_lists():
    p = TimeSenseParser()
    # обычный список дел с «и» внутри — не делится, ничего не теряется
    ru = p.parse_multi("купить хлеб и молоко завтра", now=NOW)
    assert len(ru) == 1 and "хлеб" in ru[0].title and "молоко" in ru[0].title
    en = p.parse_multi("buy milk and bread tomorrow", now=NOW, language="en")
    assert len(en) == 1 and "milk" in en[0].title and "bread" in en[0].title
    # настоящие два события — делятся
    two = p.parse_multi("завтра в 10 встреча и в 12 обед", now=NOW)
    assert len(two) == 2


def test_invalid_date_hard_fail():
    p = TimeSenseParser()
    assert p.parse("31 февраля в 10 встреча", now=NOW) is None
    assert p.parse("29 февраля 2025 в 10 событие", now=NOW) is None
    assert p.parse("Feb 31 at 10 meeting", now=NOW, language="en") is None
    assert p.parse("2/31 at 10 sync", now=NOW, language="en") is None
    # валидные — работают
    assert p.parse("28 февраля в 10 событие", now=NOW) is not None
    assert p.parse("Feb 28 at 10 meeting", now=NOW, language="en") is not None


def test_decimal_relative_offsets():
    p = TimeSenseParser()
    r = p.parse("через 1.5 часа позвонить", now=NOW)
    assert r.datetime_at.hour == 15 and r.datetime_at.minute == 30
    e = p.parse("in 1.5 hours call", now=NOW, language="en")
    assert e.datetime_at.hour == 15 and e.datetime_at.minute == 30


def test_en_timezone_hard_fail():
    p = TimeSenseParser()
    assert p.parse("tomorrow at 10 UTC meeting", now=NOW, language="en") is None
    assert p.parse("tomorrow at 10 GMT+3 meeting", now=NOW, language="en") is None
    assert p.parse("tomorrow at 10 meeting", now=NOW, language="en") is not None


def test_working_calendar_affects_business_days():
    cal = WorkingCalendar(holidays=["2026-02-26", "2026-02-27"], working_weekends=["2026-02-28"])
    p0 = TimeSenseParser()
    p1 = TimeSenseParser(TimeConfig(calendar=cal))
    # без календаря последний рабочий день февраля 2026 = 27 (пт)
    assert p0.parse("последний рабочий день месяца x", now=NOW).start_at.day == 27
    # с календарём 26-27 праздники, 28 — перенесённая рабочая суббота
    assert p1.parse("последний рабочий день месяца x", now=NOW).start_at.day == 28
    # EN тоже
    assert p1.parse("last business day of the month x", now=NOW, language="en").start_at.day == 28
    # «после N числа» пропускает праздники
    assert p1.parse("первый будний день после 25 числа x", now=NOW).start_at.day == 28


def test_working_calendar_api():
    cal = WorkingCalendar.from_dict(
        {
            "holidays": ["2026-01-01", "2026-01-02"],
            "working_weekends": ["2026-01-17"],
            "holiday_names": {"новый год": "2026-01-01"},
        }
    )
    assert cal.is_holiday("2026-01-01") is True
    assert cal.is_working_day("2026-01-01") is False
    assert cal.is_working_day("2026-01-17") is True  # рабочая суббота
    assert cal.resolve_holiday("новый год") == [__import__("datetime").date(2026, 1, 1)]
    assert cal.next_working_day("2026-01-01").isoformat() == "2026-01-05"

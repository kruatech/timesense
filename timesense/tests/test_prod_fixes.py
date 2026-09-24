# -*- coding: utf-8 -*-
"""Регресс-тесты подготовки к проду (этапы 1–2): часовые пояса, лимиты,
морфология, молча неверные результаты. NOW = вт 22.09.2026 14:00."""

from datetime import datetime, timedelta, timezone

import pytest

from timesense import TimeConfig, TimeSenseParser, TaskType, to_ics
from timesense.core.tz import find_tz_marker, resolve_tz

NOW = datetime(2026, 9, 22, 14, 0)  # вторник

try:
    from zoneinfo import ZoneInfo

    ZoneInfo("Europe/Amsterdam")
    HAS_TZDATA = True
except Exception:  # pragma: no cover — нет базы IANA в окружении
    HAS_TZDATA = False

needs_tzdata = pytest.mark.skipif(not HAS_TZDATA, reason="нет базы IANA (pip install tzdata)")


@pytest.fixture(scope="module")
def p():
    return TimeSenseParser()


def _at(r):
    """Главный момент результата (datetime/start/deadline)."""
    for f in ("datetime_at", "deadline", "start_at"):
        v = getattr(r, f, None)
        if v is not None:
            return v
    return None


# ── 1. Часовые пояса ──────────────────────────────────────────────────────
MSK = timezone(timedelta(hours=3), "MSK")


def test_aware_now_does_not_crash(p):
    r = p.parse("завтра в 10 встреча", now=NOW.replace(tzinfo=MSK))
    assert r is not None
    assert r.datetime_at == datetime(2026, 9, 23, 10, 0, tzinfo=MSK)


def test_tz_param_makes_result_aware(p):
    r = p.parse("с 10 до 11 созвон", now=NOW, tz=MSK)
    assert r.start_at.tzinfo is not None and r.end_at.tzinfo is not None
    assert r.start_at.hour == 10 and r.end_at.hour == 11


def test_without_tz_behaviour_unchanged(p):
    r = p.parse("завтра в 10 встреча", now=NOW)
    assert r.datetime_at.tzinfo is None
    # маркер пояса без tz пользователя — как раньше, None
    assert p.parse("в 10 мск созвон", now=NOW) is None
    assert p.parse("at 10 EST call", now=NOW) is None


@pytest.mark.parametrize(
    "text,user_tz,expected_utc",
    [
        # «завтра в 10 по москве» = 07:00 UTC
        ("завтра в 10 по москве созвон", "UTC", datetime(2026, 9, 23, 7, 0)),
        ("завтра в 10 мск созвон", "UTC", datetime(2026, 9, 23, 7, 0)),
        ("завтра в 18 по московскому времени созвон", "UTC", datetime(2026, 9, 23, 15, 0)),
        ("завтра в 10 utc+3 созвон", "UTC", datetime(2026, 9, 23, 7, 0)),
        ("завтра в 10 мск+2 созвон", "UTC", datetime(2026, 9, 23, 5, 0)),
        ("завтра в 10 utc созвон", "UTC", datetime(2026, 9, 23, 10, 0)),
    ],
)
def test_tz_marker_converted(p, text, user_tz, expected_utc):
    r = p.parse(text, now=NOW, tz=user_tz)
    assert r is not None, text
    assert r.datetime_at.astimezone(timezone.utc).replace(tzinfo=None) == expected_utc
    assert r.source == text
    assert "мск" not in r.title and "utc" not in r.title.lower()


@needs_tzdata
def test_tz_marker_en_and_iana(p):
    r = p.parse("tomorrow at 10am EST call", now=NOW, tz="Europe/Moscow")
    # 10:00 New York (EDT, UTC-4) = 17:00 Москва
    assert r.datetime_at.hour == 17 and r.datetime_at.day == 23
    assert r.title == "call"


def test_resolve_tz_errors():
    with pytest.raises(ValueError):
        resolve_tz("Mars/Base")
    with pytest.raises(TypeError):
        resolve_tz(123)
    assert resolve_tz(None) is None


def test_find_tz_marker_keeps_length():
    z, cleaned = find_tz_marker("в 10 по мск созвон")
    assert len(cleaned) == len("в 10 по мск созвон")
    assert "мск" not in cleaned
    assert find_tz_marker("завтра в 10 созвон") is None


def test_parse_multi_with_tz(p):
    res = p.parse_multi("завтра в 10 встреча и в 15 созвон", now=NOW.replace(tzinfo=MSK))
    assert len(res) == 2
    assert all(r.datetime_at.tzinfo is not None for r in res)
    assert res[1].datetime_at.day == 23 and res[1].datetime_at.hour == 15


def test_ics_aware_utc_and_until():
    p = TimeSenseParser()
    r = p.parse("завтра в 10 встреча", now=NOW, tz=MSK)
    ics = to_ics(r, stamp=datetime(2026, 9, 22, 12, 0))
    assert "DTSTART:20260923T070000Z" in ics


@needs_tzdata
def test_ics_recurring_uses_tzid(p):
    r = p.parse("каждую пятницу в 18 отчёт", now=NOW, tz="Europe/Amsterdam")
    ics = to_ics(r, stamp=datetime(2026, 9, 22, 12, 0))
    assert "DTSTART;TZID=Europe/Amsterdam:20260925T180000" in ics


def test_rrule_until_aware_is_utc_z():
    from timesense import RecurrenceRule

    rr = RecurrenceRule("WEEKLY", until=datetime(2026, 10, 31, 23, 59, tzinfo=MSK))
    assert "UNTIL=20261031T205900Z" in rr.to_rrule()
    rr2 = RecurrenceRule("WEEKLY", until=datetime(2026, 10, 31, 23, 59))
    assert "UNTIL=20261031T235900" in rr2.to_rrule() and "Z" not in rr2.to_rrule()


# ── 1. Лимит длины и морфология ───────────────────────────────────────────
def test_max_text_length(p):
    assert p.parse("в 10 " * 300, now=NOW) is None
    assert p.parse_multi("в 10 " * 300, now=NOW) == []
    unlimited = TimeSenseParser(TimeConfig(max_text_length=None))
    assert unlimited.parse("в 10 " * 300, now=NOW) is not None
    with pytest.raises(ValueError):
        TimeConfig(max_text_length=-1)


def test_use_morph_false():
    p0 = TimeSenseParser(TimeConfig(use_morph=False))
    assert p0.tokenizer.morph.available is False
    r = p0.parse("завтра в 10 встреча", now=NOW)
    assert r.datetime_at == datetime(2026, 9, 23, 10, 0)


# ── 2. Неделя + день недели ───────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,expected",
    [
        ("на следующей неделе в среду в 11 созвон", datetime(2026, 9, 30, 11, 0)),
        ("в среду на следующей неделе в 11 созвон", datetime(2026, 9, 30, 11, 0)),
        ("в среду на следующей неделе созвон", datetime(2026, 9, 30)),
        ("на следующей неделе в понедельник", datetime(2026, 9, 28)),
        ("на этой неделе в пятницу кино", datetime(2026, 9, 25)),
        ("на прошлой неделе в четверг", datetime(2026, 9, 17)),
        ("на позапрошлой неделе во вторник", datetime(2026, 9, 8)),
        ("next week on wednesday at 11 call", datetime(2026, 9, 30, 11, 0)),
        ("on wednesday next week call", datetime(2026, 9, 30)),
        ("wednesday of next week at 3pm call", datetime(2026, 9, 30, 15, 0)),
        ("last week on Thursday at 11:25 x", datetime(2026, 9, 17, 11, 25)),
        ("this week on friday", datetime(2026, 9, 25)),
    ],
)
def test_week_weekday(p, text, expected):
    r = p.parse(text, now=NOW)
    assert r is not None, text
    assert _at(r) == expected, text


def test_week_weekday_title_clean(p):
    assert p.parse("на следующей неделе во вторник в 10 врач", now=NOW).title == "врач"


# ── 2. Числовые даты EN ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,expected",
    [
        ("25/09 at 6pm birthday", datetime(2026, 9, 25, 18, 0)),
        ("9/25 at 6pm", datetime(2026, 9, 25, 18, 0)),
        ("31/12/2026 party", datetime(2026, 12, 31)),
    ],
)
def test_en_numeric_dates(p, text, expected):
    assert _at(p.parse(text, now=NOW)) == expected


@pytest.mark.parametrize("text", ["13/13 at 5pm", "31/02 at 5pm"])
def test_en_invalid_numeric_date_none(p, text):
    assert p.parse(text, now=NOW) is None


# ── 2. BYMONTHDAY ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,day",
    [
        ("1 числа каждого месяца оплатить квартиру", 1),
        ("первого числа каждого месяца оплатить квартиру", 1),
        ("15 числа каждого месяца в 10 зарплата", 15),
        ("каждый месяц 15 числа", 15),
    ],
)
def test_monthly_by_month_day(p, text, day):
    r = p.parse(text, now=NOW)
    assert r.recurrence.by_month_day == [day]
    assert "BYMONTHDAY=%d" % day in r.recurrence.to_rrule()
    assert _at(r).day == day
    assert "числ" not in r.title


# ── 2. «11 30» — минуты через пробел ──────────────────────────────────────
@pytest.mark.parametrize(
    "text,start,end",
    [
        ("с 10 до 11 30 совещание", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 11, 30)),
        ("с 10 30 до 11 совещание", datetime(2026, 9, 23, 10, 30), datetime(2026, 9, 23, 11, 0)),
    ],
)
def test_spoken_minutes_range(p, text, start, end):
    r = p.parse(text, now=NOW)
    assert (r.start_at, r.end_at) == (start, end)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("в 11 30 совещание", datetime(2026, 9, 23, 11, 30)),
        ("завтра в 18 45 кино", datetime(2026, 9, 23, 18, 45)),
        ("25 сентября в 18 30 др", datetime(2026, 9, 25, 18, 30)),
    ],
)
def test_spoken_minutes_point(p, text, expected):
    assert p.parse(text, now=NOW).datetime_at == expected


def test_spoken_minutes_not_dates(p):
    r = p.parse("с 1 по 10 октября отпуск", now=NOW)
    assert (r.start_at.day, r.end_at.day) == (1, 10)


# ── 2. Полночь = конец названного дня ─────────────────────────────────────
@pytest.mark.parametrize(
    "text,expected",
    [
        ("сегодня в полночь", datetime(2026, 9, 23, 0, 0)),
        ("завтра в полночь", datetime(2026, 9, 24, 0, 0)),
        ("в полночь", datetime(2026, 9, 23, 0, 0)),
        ("в пятницу в полночь", datetime(2026, 9, 26, 0, 0)),
        ("today at midnight", datetime(2026, 9, 23, 0, 0)),
        ("tomorrow at midnight", datetime(2026, 9, 24, 0, 0)),
        ("tonight at midnight", datetime(2026, 9, 23, 0, 0)),
    ],
)
def test_midnight_end_of_day(p, text, expected):
    r = p.parse(text, now=NOW)
    assert r.datetime_at == expected and r.is_past is False


def test_midnight_no_dangling_at(p):
    assert p.parse("at midnight", now=NOW).title == ""
    assert p.parse("lunch at noon", now=NOW).title == "lunch"


# ── 2. «до ЧЧ» — дедлайн ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,deadline",
    [
        ("до 18 отчёт", datetime(2026, 9, 22, 18, 0)),
        ("до 18:00 сдать отчёт", datetime(2026, 9, 22, 18, 0)),
        ("до 6 вечера отчёт", datetime(2026, 9, 22, 18, 0)),
        ("до 10 утра отчёт", datetime(2026, 9, 23, 10, 0)),
        ("до 18 часов отчёт", datetime(2026, 9, 22, 18, 0)),
        ("завтра до 18 отчёт", datetime(2026, 9, 23, 18, 0)),
        ("сегодня до 20 отчёт", datetime(2026, 9, 22, 20, 0)),
        ("в пятницу до 18:00 отчёт", datetime(2026, 9, 25, 18, 0)),
        ("сегодня до полуночи отчёт", datetime(2026, 9, 23, 0, 0)),
        ("завтра до полуночи отчёт", datetime(2026, 9, 24, 0, 0)),
        ("завтра до обеда отчёт", datetime(2026, 9, 23, 13, 0)),
    ],
)
def test_until_time_deadline(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE, text
    assert r.deadline == deadline, text
    assert r.title in ("отчёт", "сдать отчёт"), text


def test_until_time_does_not_break_others(p):
    assert p.parse("с 10 до 18 работа", now=NOW).end_at == datetime(2026, 9, 23, 18, 0)
    assert p.parse("до 20 марта отчёт", now=NOW).deadline.month == 3
    assert p.parse("до 5 минут", now=NOW) is None
    assert p.parse("к 18 отчёт", now=NOW).datetime_at == datetime(2026, 9, 22, 18, 0)


# ── 2. Разговорные части суток ────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,start",
    [
        ("завтра вечерком", datetime(2026, 9, 23, 18, 0)),
        ("утречком пробежка", datetime(2026, 9, 23, 9, 0)),
        ("с утречка позвонить", datetime(2026, 9, 23, 9, 0)),
        ("поутру созвон", datetime(2026, 9, 23, 9, 0)),
    ],
)
def test_daypart_diminutives(p, text, start):
    r = p.parse(text, now=NOW)
    assert r.start_at == start
    assert "вечерком" not in r.title and "утречк" not in r.title


# ── 2. Альтернативы «или» → None ──────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "либо в понедельник либо во вторник",
        "в понедельник или вторник созвон",
        "в 5 или 6 созвон",
        "завтра или послезавтра",
        "monday or tuesday",
        "at 5 or 6pm call",
    ],
)
def test_alternatives_none(p, text):
    assert p.parse(text, now=NOW) is None


@pytest.mark.parametrize(
    "text", ["чай или кофе завтра в 10", "позвонить Ивану или Пете завтра в 10"]
)
def test_or_in_title_still_parses(p, text):
    r = p.parse(text, now=NOW)
    assert r is not None and r.datetime_at == datetime(2026, 9, 23, 10, 0)


# ── 2. Длительность EN ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,minutes",
    [
        ("tomorrow 11am meeting for 1.5 hours", 90),
        ("tomorrow at 11 meeting for an hour and a half", 90),
        ("tomorrow at 11 meeting for 2 and a half hours", 150),
        ("tomorrow at 11 meeting for half an hour", 30),
        ("tomorrow at 11 meeting for 2h", 120),
        ("tomorrow at 11 meeting for 45 min", 45),
    ],
)
def test_en_duration(p, text, minutes):
    r = p.parse(text, now=NOW)
    assert r.duration_minutes == minutes
    assert r.end_at - r.start_at == timedelta(minutes=minutes)
    assert r.title == "meeting"


# ── 2. Smart-hour: RU и EN одинаковы ──────────────────────────────────────
@pytest.mark.parametrize("hh", range(24))
def test_smart_hour_parity_ru_en(p, hh):
    now = datetime(2026, 9, 22, hh, 0)
    for h in range(24):
        a = p.parse("at %d call" % h, now=now)
        b = p.parse("в %d созвон" % h, now=now)
        assert (a and a.datetime_at) == (b and b.datetime_at), (hh, h)


def test_smart_hour_readme_example(p):
    # README: при now=14:00 «at 10» → 22:00 сегодня
    assert p.parse("at 10 call", now=NOW).datetime_at == datetime(2026, 9, 22, 22, 0)
    assert p.parse("в 10 созвон", now=NOW).datetime_at == datetime(2026, 9, 22, 22, 0)


# ══ Этап 3: покрытие и паритет RU/EN ══════════════════════════════════════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("через 30 секунд проверить", datetime(2026, 9, 22, 14, 0, 30)),
        ("in 30 secs check", datetime(2026, 9, 22, 14, 0, 30)),
        ("через пол часа позвонить", datetime(2026, 9, 22, 14, 30)),
        ("через полчасика", datetime(2026, 9, 22, 14, 30)),
        ("в 1930 кино", datetime(2026, 9, 22, 19, 30)),
        ("at 1930 movie", datetime(2026, 9, 22, 19, 30)),
        ("at 7.30pm dinner", datetime(2026, 9, 22, 19, 30)),
        ("tmrw at 10", datetime(2026, 9, 23, 10, 0)),
        ("2moro at 10", datetime(2026, 9, 23, 10, 0)),
        ("tomorow at 10", datetime(2026, 9, 23, 10, 0)),
    ],
)
def test_shorthand_points(p, text, expected):
    assert _at(p.parse(text, now=NOW)) == expected, text


@pytest.mark.parametrize(
    "text,start,end",
    [
        ("в октябре отпуск", datetime(2026, 10, 1), datetime(2026, 10, 31, 23, 59)),
        ("in october vacation", datetime(2026, 10, 1), datetime(2026, 10, 31, 23, 59)),
        ("в марте отпуск", datetime(2027, 3, 1), datetime(2027, 3, 31, 23, 59)),
        ("in december 2026 trip", datetime(2026, 12, 1), datetime(2026, 12, 31, 23, 59)),
        ("в 2027 году переезд", datetime(2027, 1, 1), datetime(2027, 12, 31, 23, 59)),
        ("in 2027 move", datetime(2027, 1, 1), datetime(2027, 12, 31, 23, 59)),
        ("в следующем месяце", datetime(2026, 10, 1), datetime(2026, 10, 31, 23, 59)),
        ("next month", datetime(2026, 10, 1), datetime(2026, 10, 31, 23, 59)),
        ("в начале следующего месяца", datetime(2026, 10, 1), datetime(2026, 10, 5, 23, 59)),
        ("beginning of next month", datetime(2026, 10, 1), datetime(2026, 10, 5, 23, 59)),
        ("на следующих выходных дача", datetime(2026, 10, 3), datetime(2026, 10, 4, 23, 59)),
        ("next weekend cottage", datetime(2026, 10, 3), datetime(2026, 10, 4, 23, 59)),
        ("в эти выходные дача", datetime(2026, 9, 26), datetime(2026, 9, 27, 23, 59)),
        ("this weekend cottage", datetime(2026, 9, 26), datetime(2026, 9, 27, 23, 59)),
        ("с понедельника по среду командировка", datetime(2026, 9, 28), datetime(2026, 9, 30, 23, 59)),
        ("from monday to wednesday trip", datetime(2026, 9, 28), datetime(2026, 9, 30, 23, 59)),
        ("sep 25 - oct 3 vacation", datetime(2026, 9, 25), datetime(2026, 10, 3, 23, 59)),
        ("this afternoon call", datetime(2026, 9, 22, 12, 0), datetime(2026, 9, 22, 15, 0)),
    ],
)
def test_periods_parity(p, text, start, end):
    r = p.parse(text, now=NOW)
    assert r is not None, text
    assert (r.start_at, r.end_at) == (start, end), text
    assert r.start_at.second == 0 and r.end_at.second == 0
    for junk in ("эти", "следующих", "next", "this", "in"):
        assert junk not in r.title.split(), (text, r.title)


def test_middle_of_month_no_seconds(p):
    r = p.parse("в середине октября поездка", now=NOW)
    assert r.start_at.second == 0 and r.end_at.second == 0


@pytest.mark.parametrize(
    "text,rrule",
    [
        ("every 15th pay salary", "FREQ=MONTHLY;BYMONTHDAY=15"),
        ("every 1st of the month pay rent", "FREQ=MONTHLY;BYMONTHDAY=1"),
        ("раз в две недели", "FREQ=WEEKLY;INTERVAL=2"),
        ("каждую пятницу в 18 до конца октября отчёт", "FREQ=WEEKLY;BYDAY=FR;UNTIL=20261031T235900"),
        ("every friday at 6pm until end of october report", "FREQ=WEEKLY;BYDAY=FR;UNTIL=20261031T235900"),
    ],
)
def test_recurrence_parity(p, text, rrule):
    assert p.parse(text, now=NOW).recurrence.to_rrule() == rrule


@pytest.mark.parametrize(
    "text,deadline",
    [
        ("by eod report", datetime(2026, 9, 22, 23, 59)),
        ("eod report", datetime(2026, 9, 22, 23, 59)),
        ("until 6pm report", datetime(2026, 9, 22, 18, 0)),
        ("before lunch call", datetime(2026, 9, 23, 13, 0)),
        ("перед обедом созвон", datetime(2026, 9, 23, 13, 0)),
    ],
)
def test_deadlines_parity(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE and r.deadline == deadline, text


@pytest.mark.parametrize("text", ["after 5pm call", "after lunch call", "после 17 созвон"])
def test_open_start_parity(p, text):
    assert p.parse(text, now=NOW).task_type == TaskType.OPEN_START


@pytest.mark.parametrize(
    "text,title",
    [
        ("напомни мне завтра в 10 позвонить маме", "позвонить маме"),
        ("напомни через 15 минут выключить плиту", "выключить плиту"),
        ("remind me in 30 seconds", ""),
        ("set a reminder to call mom at 5pm", "call mom"),
        ("at 12am reminder", "reminder"),
    ],
)
def test_remind_me_not_in_title(p, text, title):
    assert p.parse(text, now=NOW).title == title


def test_year_not_taken_as_time(p):
    r = p.parse("в 2027 году переезд", now=NOW)
    assert r.start_at.year == 2027 and not hasattr(r, "datetime_at")


def test_human_readable_localized(p):
    assert p.parse("by friday report", now=NOW).human_readable().startswith("by ")
    assert p.parse("до пятницы отчёт", now=NOW).human_readable().startswith("до ")
    assert p.parse("after 5pm call", now=NOW).human_readable() == "after 17:00"
    assert p.parse("this weekend cottage", now=NOW).human_readable() == "26.09.2026 - 27.09.2026"
    assert p.parse("в эти выходные дача", now=NOW).human_readable() == "26.09.2026 - 27.09.2026"


# ══ Этап 4: названия и даты-«хвосты» ══════════════════════════════════════
@pytest.mark.parametrize(
    "text,title",
    [
        ("завтра в 11 встреча на полтора часа", "встреча"),
        ("завтра в 10 или позже", ""),
        ("с утра пораньше", ""),
        ("поставь будильник на без пятнадцати восемь", "будильник"),
        ("встреча с командой завтра в 10", "встреча с командой"),
        ("через час напомнить про отправку договора", "напомнить про отправку договора"),
        ("turn the lights on at 7pm", "turn the lights on"),
        ("turn on the heater at 6am", "turn on the heater"),
        ("sign in to the portal tomorrow at 9", "sign in to the portal"),
        ("remind me in 15 minutes to turn off the stove", "turn off the stove"),
        ("meeting tomorrow at 10 for 2 hours in the office", "meeting"),
        ("tomorrow at 10 meeting in the park", "meeting"),
        ("meeting on friday with Bob", "meeting with Bob"),
        ("lunch with Anna at noon", "lunch with Anna"),
        ("Sync with ACME tomorrow at 10", "Sync with ACME"),
        ("every month on 15th", ""),
    ],
)
def test_titles_clean(p, text, title):
    assert p.parse(text, now=NOW).title == title, text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("в пн в 10 созвон", datetime(2026, 9, 28, 10, 0)),
        ("в пт созвон", datetime(2026, 9, 25)),
        ("каждый пн в 9 стендап", datetime(2026, 9, 28, 9, 0)),
        ("day before yesterday at 5pm", datetime(2026, 9, 20, 17, 0)),
        ("the day before yesterday morning", datetime(2026, 9, 20, 9, 0)),
        ("a week from monday", datetime(2026, 10, 5)),
        ("on the 5th pay rent", datetime(2026, 10, 5)),
        ("the 30th at 10 call", datetime(2026, 9, 30, 10, 0)),
        ("by the 20th report", datetime(2026, 10, 20, 23, 59)),
    ],
)
def test_tail_dates(p, text, expected):
    assert _at(p.parse(text, now=NOW)) == expected, text


@pytest.mark.parametrize(
    "text,rrule",
    [
        ("every last Friday at 5pm", "FREQ=MONTHLY;BYDAY=-1FR"),
        ("every month on 15th", "FREQ=MONTHLY;BYMONTHDAY=15"),
        ("По пн ср пт", "FREQ=WEEKLY;BYDAY=MO,WE,FR"),
    ],
)
def test_tail_recurrence(p, text, rrule):
    assert p.parse(text, now=NOW).recurrence.to_rrule() == rrule


def test_weekday_abbrev_range(p):
    r = p.parse("со вт по чт", now=NOW)
    assert (r.start_at, r.end_at) == (datetime(2026, 9, 22), datetime(2026, 9, 24, 23, 59))


# ══ Этап 5: конфиг одинаково в RU и EN ════════════════════════════════════
@pytest.mark.parametrize(
    "ru,en,expected",
    [
        ("в 5 созвон", "at 5 call", datetime(2026, 9, 22, 5, 0)),
        ("завтра в 5 созвон", "tomorrow at 5 call", datetime(2026, 9, 23, 5, 0)),
        ("в 1 обед", "at 1 lunch", datetime(2026, 9, 22, 1, 0)),
        ("в пятницу в 5", "friday at 5", datetime(2026, 9, 25, 5, 0)),
        ("до 6 отчёт", "by 6 report", datetime(2026, 9, 22, 6, 0)),
    ],
)
def test_strict_config_parity(ru, en, expected):
    s = TimeSenseParser(TimeConfig.strict())
    assert _at(s.parse(ru, now=NOW)) == expected, ru
    assert _at(s.parse(en, now=NOW)) == expected, en


def test_strict_range_parity():
    s = TimeSenseParser(TimeConfig.strict())
    a, b = s.parse("с 2 до 4 созвон", now=NOW), s.parse("from 2 to 4 call", now=NOW)
    assert (a.start_at, a.end_at) == (b.start_at, b.end_at) == (
        datetime(2026, 9, 22, 2, 0), datetime(2026, 9, 22, 4, 0))


def test_default_tz_config():
    t = TimeSenseParser(TimeConfig(default_tz=MSK))
    r = t.parse("завтра в 10 встреча", now=NOW)
    assert r.datetime_at == datetime(2026, 9, 23, 10, 0, tzinfo=MSK)
    # явный tz в вызове важнее конфига
    r2 = t.parse("завтра в 10 встреча", now=NOW, tz=timezone.utc)
    assert r2.datetime_at.tzinfo is timezone.utc
    with pytest.raises(ValueError):
        TimeConfig(default_tz="Mars/Base")


# ══ Этап 7: живые фразы бота ══════════════════════════════════════════════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("сегодня вечером в 20 созвон", datetime(2026, 9, 22, 20, 0)),
        ("завтра утром в 8:30 врач", datetime(2026, 9, 23, 8, 30)),
        ("вечером в 7 кино", datetime(2026, 9, 22, 19, 0)),
        ("ночью в 2 бэкап", datetime(2026, 9, 23, 2, 0)),
        ("днём в 3 встреча", datetime(2026, 9, 22, 15, 0)),
        ("tonight at 8:30 call", datetime(2026, 9, 22, 20, 30)),
        ("this evening at 7:30 dinner", datetime(2026, 9, 22, 19, 30)),
        ("tomorrow morning at 8:30 doctor", datetime(2026, 9, 23, 8, 30)),
        ("через час пятнадцать созвон", datetime(2026, 9, 22, 15, 15)),
        ("через 2 часа 30 созвон", datetime(2026, 9, 22, 16, 30)),
        ("in an hour fifteen call", datetime(2026, 9, 22, 15, 15)),
        ("через неделю в пятницу в 18 встреча", datetime(2026, 10, 2, 18, 0)),
        ("через 3 недели в понедельник отчёт", datetime(2026, 10, 12)),
        ("last day of the month pay internet", datetime(2026, 9, 30)),
        ("first day of next month rent", datetime(2026, 10, 1)),
        ("в прошлую среду утром в 09:05 созвон", datetime(2026, 9, 16, 9, 5)),
    ],
)
def test_bot_phrases_points(p, text, expected):
    assert _at(p.parse(text, now=NOW)) == expected, text


@pytest.mark.parametrize(
    "text,expected,rrule",
    [
        ("каждое утро в 7 зарядка", datetime(2026, 9, 23, 7, 0), "FREQ=DAILY"),
        ("каждый день в 7 утра зарядка", datetime(2026, 9, 23, 7, 0), "FREQ=DAILY"),
        ("по вечерам в 9 чтение", datetime(2026, 9, 22, 21, 0), "FREQ=DAILY"),
        ("каждую ночь в 2 бэкап", datetime(2026, 9, 23, 2, 0), "FREQ=DAILY"),
        ("по будням в 8 утра стендап", datetime(2026, 9, 23, 8, 0), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("по выходным в 10 йога", datetime(2026, 9, 26, 10, 0), "FREQ=WEEKLY;BYDAY=SA,SU"),
        ("every morning at 7 workout", datetime(2026, 9, 23, 7, 0), "FREQ=DAILY"),
        ("every evening at 9 read", datetime(2026, 9, 22, 21, 0), "FREQ=DAILY"),
        ("every march 5 mom birthday", datetime(2027, 3, 5), "FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=5"),
        ("every year on the 5th of march mom birthday", datetime(2027, 3, 5),
         "FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=5"),
    ],
)
def test_bot_phrases_recurrence(p, text, expected, rrule):
    r = p.parse(text, now=NOW)
    assert _at(r) == expected, text
    assert r.recurrence.to_rrule() == rrule, text


@pytest.mark.parametrize(
    "text,deadline",
    [
        ("в течение дня позвонить", datetime(2026, 9, 22, 23, 59)),
        ("в течение недели ответить", datetime(2026, 9, 27, 23, 59)),
        ("в течение часа ответить", datetime(2026, 9, 22, 15, 0)),
        ("within 2 hours reply to client", datetime(2026, 9, 22, 16, 0)),
        ("within the day call", datetime(2026, 9, 22, 23, 59)),
        ("within an hour call", datetime(2026, 9, 22, 15, 0)),
    ],
)
def test_within_parity(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE and r.deadline == deadline, text


def test_en_range_pm_propagation(p):
    r = p.parse("call tomorrow from 3 to 4:30pm", now=NOW)
    assert (r.start_at, r.end_at) == (datetime(2026, 9, 23, 15, 0), datetime(2026, 9, 23, 16, 30))
    r = p.parse("from 11 to 1pm lunch", now=NOW)
    assert (r.start_at.hour, r.end_at.hour) == (11, 13)


def test_ru_title_keeps_inner_and(p):
    assert p.parse("купить хлеб и молоко завтра", now=NOW).title == "купить хлеб и молоко"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("через 2 дня в 10 врач", datetime(2026, 9, 24, 10, 0)),
        ("через два дня в 16:05 созвониться с дизайнером", datetime(2026, 9, 24, 16, 5)),
        ("днём в 3 встреча", datetime(2026, 9, 22, 15, 0)),
    ],
)
def test_daypart_word_inside_other_expression(p, text, expected):
    # «дня» в «через 2 дня» — не часть суток (регрессия этапа 7)
    assert _at(p.parse(text, now=NOW)) == expected, text


# ══ Этап 8: опечатки и разговорные формы ══════════════════════════════════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("завтро в 10 врач", datetime(2026, 9, 23, 10, 0)),
        ("послезавтро в 10", datetime(2026, 9, 24, 10, 0)),
        ("севодня в 18 созвон", datetime(2026, 9, 22, 18, 0)),
        ("седня в 18 созвон", datetime(2026, 9, 22, 18, 0)),
        ("в понедельнек в 10", datetime(2026, 9, 28, 10, 0)),
        ("в пятницк в 10", datetime(2026, 9, 25, 10, 0)),
        ("питницу созвон", datetime(2026, 9, 25)),
        ("firday at 5pm", datetime(2026, 9, 25, 17, 0)),
        ("satruday at 10", datetime(2026, 9, 26, 10, 0)),
        ("wensday at 10 call", datetime(2026, 9, 23, 10, 0)),
        ("thurday at 10 call", datetime(2026, 9, 24, 10, 0)),
        ("tomorow at 10 call", datetime(2026, 9, 23, 10, 0)),
        ("ocotber 5 trip", datetime(2026, 10, 5)),
        ("через пару часов позвонить", datetime(2026, 9, 22, 16, 0)),
        ("in a couple of hours call", datetime(2026, 9, 22, 16, 0)),
        ("в 10-00 созвон", datetime(2026, 9, 23, 10, 0)),
        ("в 9-05 созвон", datetime(2026, 9, 23, 9, 5)),
        ("в 10ч30 созвон", datetime(2026, 9, 23, 10, 30)),
        ("без 15 десять созвон", datetime(2026, 9, 23, 9, 45)),
        ("без пятнадцати 10 созвон", datetime(2026, 9, 23, 9, 45)),
        ("без 15 19 созвон", datetime(2026, 9, 22, 18, 45)),
        ("at half 10 meeting", datetime(2026, 9, 23, 10, 30)),
        ("через полторы недели отпуск", datetime(2026, 10, 3, 2, 0)),
    ],
)
def test_typos_and_colloquial(p, text, expected):
    assert _at(p.parse(text, now=NOW)) == expected, text


@pytest.mark.parametrize(
    "text,title_word",
    [
        ("завтрак в 9", "завтрак"),          # не «завтра»
        ("до 6 вечера отчёт", "отчёт"),       # «вечера» не «вчера»
        ("the fridge at 5pm", "fridge"),      # не «friday»
        ("в четверть шестого встреча", "встреча"),
    ],
)
def test_typo_fixer_does_not_touch_real_words(p, text, title_word):
    r = p.parse(text, now=NOW)
    assert r is not None and title_word in r.title, text


def test_typo_fixer_units():
    from timesense.core.typo import en_fixer, ru_fixer

    assert ru_fixer().correct("вечера") is None
    assert ru_fixer().correct("завтрак") is None
    assert ru_fixer().correct("завтро") == "завтра"
    assert en_fixer().correct("fridge") is None
    assert en_fixer().correct("firday") == "friday"


def test_range_with_minutes_dash_still_range(p):
    r = p.parse("с 10-11 созвон", now=NOW)
    assert (r.start_at.hour, r.end_at.hour) == (10, 11)


# ══ Этап 9: праздники по названию ═════════════════════════════════════════
@pytest.mark.parametrize(
    "text,expected,title",
    [
        ("на новый год поздравить", datetime(2027, 1, 1), "поздравить"),
        ("в новогоднюю ночь в 23:50 шампанское", datetime(2026, 12, 31, 23, 50), "шампанское"),
        ("на старый новый год", datetime(2027, 1, 14), ""),
        ("в рождество в 12 в церковь", datetime(2027, 1, 7, 12, 0), "в церковь"),
        ("на 8 марта подарок", datetime(2027, 3, 8), "подарок"),
        ("в день победы в 10 парад", datetime(2027, 5, 9, 10, 0), "парад"),
        ("на пасху куличи", datetime(2027, 5, 2), "куличи"),               # православная
        ("christmas party at 7pm", datetime(2026, 12, 25, 19, 0), "party"),
        ("on new year's eve at 11pm party", datetime(2026, 12, 31, 23, 0), "party"),
        ("on thanksgiving dinner at 6pm", datetime(2026, 11, 26, 18, 0), "dinner"),
        ("easter brunch at 11", datetime(2027, 3, 28, 11, 0), "brunch"),     # западная
        ("halloween party", datetime(2026, 10, 31), "party"),
        ("over christmas visit parents", datetime(2026, 12, 25), "visit parents"),
    ],
)
def test_holidays(p, text, expected, title):
    r = p.parse(text, now=NOW)
    assert _at(r) == expected, text
    assert r.title == title, text
    assert r.source == text


@pytest.mark.parametrize(
    "text,deadline",
    [
        ("до нового года сдать проект", datetime(2026, 12, 31, 23, 59)),
        ("by christmas finish the report", datetime(2026, 12, 25, 23, 59)),
    ],
)
def test_holiday_deadlines(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE and r.deadline == deadline


@pytest.mark.parametrize(
    "text,start,end",
    [
        ("на майские поездка", datetime(2027, 5, 1), datetime(2027, 5, 10, 23, 59)),
        ("на новогодние каникулы на дачу", datetime(2027, 1, 1), datetime(2027, 1, 8, 23, 59)),
    ],
)
def test_holiday_periods(p, text, start, end):
    r = p.parse(text, now=NOW)
    assert (r.start_at, r.end_at) == (start, end)


@pytest.mark.parametrize(
    "text,rrule",
    [
        ("каждый новый год поздравить родителей", "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1"),
        ("every christmas call grandma", "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"),
    ],
)
def test_holiday_recurrence(p, text, rrule):
    assert p.parse(text, now=NOW).recurrence.to_rrule() == rrule


def test_calendar_holiday_names_priority():
    from timesense import WorkingCalendar

    cal = WorkingCalendar(holiday_names={"день компании": "2026-10-15", "company day": "2026-10-15"})
    pc = TimeSenseParser(TimeConfig(calendar=cal))
    assert pc.parse("на день компании в 18 фуршет", now=NOW).datetime_at == datetime(2026, 10, 15, 18, 0)
    assert pc.parse("company day at 6pm party", now=NOW).datetime_at == datetime(2026, 10, 15, 18, 0)


def test_holiday_computations():
    from datetime import date

    from timesense.core.holidays import easter_orthodox, easter_western, thanksgiving_us

    assert easter_orthodox(2026) == date(2026, 4, 12) and easter_orthodox(2027) == date(2027, 5, 2)
    assert easter_western(2026) == date(2026, 4, 5) and easter_western(2027) == date(2027, 3, 28)
    assert thanksgiving_us(2026) == date(2026, 11, 26) and thanksgiving_us(2027) == date(2027, 11, 25)


def test_holiday_words_inside_titles_untouched(p):
    # слова, похожие на праздники, но без праздника: дата не выдумывается
    assert p.parse("обсудить новый годовой план", now=NOW) is None


def test_new_year_preposition_forms(p):
    assert p.parse("в новый год", now=NOW).start_at == datetime(2027, 1, 1)
    r = p.parse("в новом году переезд", now=NOW)  # период следующего года
    assert (r.start_at, r.end_at) == (datetime(2027, 1, 1), datetime(2027, 12, 31, 23, 59))
    r3 = p.parse("в рождество в 12 в церковь", now=NOW)
    assert (r3.datetime_at, r3.title) == (datetime(2027, 1, 7, 12, 0), "в церковь")


# ══ Этап 10: analyze() и .when для ботов ══════════════════════════════════
from timesense import ParseAnalysis, ParseStatus  # noqa: E402


@pytest.mark.parametrize(
    "text,status",
    [
        ("завтра в 10 созвон", ParseStatus.OK),
        ("", ParseStatus.EMPTY),
        ("   ", ParseStatus.EMPTY),
        ("купить молоко", ParseStatus.NO_DATETIME),
        ("в понедельник или вторник созвон", ParseStatus.AMBIGUOUS),
        ("monday or tuesday call", ParseStatus.AMBIGUOUS),
        ("вчера и завтра", ParseStatus.AMBIGUOUS),
        ("на прошлой неделе в 14:30 созвон", ParseStatus.AMBIGUOUS),
        ("last week at 14:30 review", ParseStatus.AMBIGUOUS),
        ("31 февраля в 10", ParseStatus.INVALID_DATE),
        ("в 25:00 встреча", ParseStatus.INVALID_DATE),
        ("в 10 мск созвон", ParseStatus.NEEDS_TIMEZONE),
        pytest.param("at 10 EST call", ParseStatus.NEEDS_TIMEZONE, marks=needs_tzdata),
        ("в 10 " * 300, ParseStatus.TOO_LONG),
    ],
)
def test_analyze_status(p, text, status):
    a = p.analyze(text, now=NOW)
    assert isinstance(a, ParseAnalysis)
    assert a.status == status, (text, a)
    assert a.ok == (status == ParseStatus.OK)
    # analyze() согласован с parse()
    assert (a.result is None) == (p.parse(text, now=NOW) is None)
    assert a.to_dict()["status"] == status.value


@pytest.mark.parametrize(
    "text,whens,title",
    [
        ("в понедельник или вторник созвон", [datetime(2026, 9, 28), datetime(2026, 9, 29)], "созвон"),
        ("либо в понедельник либо во вторник", [datetime(2026, 9, 28), datetime(2026, 9, 29)], ""),
        ("в 5 или 6 созвон", [datetime(2026, 9, 22, 17, 0), datetime(2026, 9, 22, 18, 0)], "созвон"),
        ("monday or tuesday call", [datetime(2026, 9, 28), datetime(2026, 9, 29)], "call"),
    ],
)
def test_analyze_alternatives(p, text, whens, title):
    a = p.analyze(text, now=NOW)
    assert [x.when for x in a.alternatives] == whens
    assert all(x.title == title for x in a.alternatives)


def test_analyze_with_tz_resolves(p):
    a = p.analyze("в 10 мск созвон", now=NOW, tz="UTC")
    assert a.ok and a.result.when.tzinfo is not None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("завтра в 10 встреча", datetime(2026, 9, 23, 10, 0)),        # Reminder
        ("до пятницы отчёт", datetime(2026, 9, 25, 23, 59)),          # Task/deadline
        ("с 10 до 11 созвон", datetime(2026, 9, 23, 10, 0)),          # Calendar
        ("в октябре отпуск", datetime(2026, 10, 1)),                  # Task/period
    ],
)
def test_when_property(p, text, expected):
    assert p.parse(text, now=NOW).when == expected


# ══ Этап 11: повторы с несколькими днями, исключениями, UNTIL ═════════════
@pytest.mark.parametrize(
    "text,rrule",
    [
        ("каждый понедельник и среду в 10 созвон", "FREQ=WEEKLY;BYDAY=MO,WE"),
        ("каждый пн, ср и пт в 9 зарядка", "FREQ=WEEKLY;BYDAY=MO,WE,FR"),
        ("every monday and wednesday at 10 call", "FREQ=WEEKLY;BYDAY=MO,WE"),
        ("every monday, wednesday and friday gym", "FREQ=WEEKLY;BYDAY=MO,WE,FR"),
        ("каждый будний день кроме пятницы в 9 стендап", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"),
        ("every weekday except friday at 9 standup", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"),
        ("каждый месяц в последний день оплатить аренду", "FREQ=MONTHLY;BYMONTHDAY=-1"),
        ("every last day of the month pay rent", "FREQ=MONTHLY;BYMONTHDAY=-1"),
        ("каждый год 1 сентября линейка", "FREQ=YEARLY;BYMONTH=9;BYMONTHDAY=1"),
        ("каждый день до конца месяца в 9 стендап", "FREQ=DAILY;UNTIL=20260930T235900"),
        ("каждые 2 недели по понедельникам в 12:00 синк", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("weekdays at 9am", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 15 minutes drink water", "FREQ=MINUTELY;INTERVAL=15"),
    ],
)
def test_recurrence_stage11(p, text, rrule):
    assert p.parse(text, now=NOW).recurrence.to_rrule() == rrule, text


def test_minutely_is_reminder_now_in_both_languages(p):
    for t in ("every 15 minutes drink water", "каждые 15 минут пить воду"):
        r = p.parse(t, now=NOW)
        assert type(r).__name__ == "ReminderResult" and r.when == NOW, t


@pytest.mark.parametrize(
    "text,expected",
    [
        ("к концу дня отправить отчёт", datetime(2026, 9, 22, 23, 59)),
        ("к концу недели отчёт", datetime(2026, 9, 27, 23, 59)),
        ("в следующий рабочий день позвонить", datetime(2026, 9, 23, 9, 0)),
        ("в первых числах октября", datetime(2026, 10, 1)),
        ("in the middle of next week", datetime(2026, 9, 30)),
    ],
)
def test_stage11_points(p, text, expected):
    assert p.parse(text, now=NOW).when == expected, text


def test_analyze_multi(p):
    many = p.analyze_multi("завтра в 10 созвон, в 13 обед, а в 18 спортзал", now=NOW)
    assert [a.status for a in many] == [ParseStatus.OK] * 3
    assert [a.result.when.hour for a in many] == [10, 13, 18]
    one = p.analyze_multi("в понедельник или вторник созвон", now=NOW)
    assert len(one) == 1 and one[0].status == ParseStatus.AMBIGUOUS
    assert len(one[0].alternatives) == 2
    assert p.analyze_multi("купить молоко", now=NOW)[0].status == ParseStatus.NO_DATETIME


# ══ Этап 12: разговорные формы, выходные + время, дедлайн день+время ═════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("в выходные в 10 бег", datetime(2026, 9, 26, 10, 0)),
        ("на выходных в 10 бег", datetime(2026, 9, 26, 10, 0)),
        ("в эти выходные в 7 шашлыки", datetime(2026, 9, 26, 19, 0)),
        ("в двадцать три ноль ноль отбой", datetime(2026, 9, 22, 23, 0)),
        ("в двадцать два тридцать кино", datetime(2026, 9, 22, 22, 30)),
        ("2026-10-01T09:00 планёрка", datetime(2026, 10, 1, 9, 0)),
        ("2026-10-01T09:00 standup", datetime(2026, 10, 1, 9, 0)),
        ("завтра at 10 meeting", datetime(2026, 9, 23, 10, 0)),
        ("by 5pm on friday report", datetime(2026, 9, 25, 17, 0)),
        ("by friday 5pm report", datetime(2026, 9, 25, 17, 0)),
        ("on friday by 5pm report", datetime(2026, 9, 25, 17, 0)),
        ("before lunch on friday submit report", datetime(2026, 9, 25, 13, 0)),
        ("by friday report", datetime(2026, 9, 25, 23, 59)),
        ("by 5pm report", datetime(2026, 9, 22, 17, 0)),
    ],
)
def test_stage12_points(p, text, expected):
    assert p.parse(text, now=NOW).when == expected, text


@pytest.mark.parametrize(
    "text,start,end,title",
    [
        ("созвон минут на 20 в 16", datetime(2026, 9, 22, 16, 0), datetime(2026, 9, 22, 16, 20), "созвон"),
        ("встреча в 15 длительностью 2 часа", datetime(2026, 9, 22, 15, 0), datetime(2026, 9, 22, 17, 0), "встреча"),
        ("meeting at 3pm lasting 2 hours", datetime(2026, 9, 22, 15, 0), datetime(2026, 9, 22, 17, 0), "meeting"),
        ("from morning till evening cleanup", datetime(2026, 9, 23, 9, 0), datetime(2026, 9, 23, 19, 0), "cleanup"),
        ("завтра весь день конференция", datetime(2026, 9, 23), datetime(2026, 9, 23, 23, 59), "конференция"),
        ("tomorrow all day conference", datetime(2026, 9, 23), datetime(2026, 9, 23, 23, 59), "conference"),
        ("всю неделю отпуск", datetime(2026, 9, 21), datetime(2026, 9, 27, 23, 59), "отпуск"),
        ("the whole week vacation", datetime(2026, 9, 21), datetime(2026, 9, 27, 23, 59), "vacation"),
    ],
)
def test_stage12_spans(p, text, start, end, title):
    r = p.parse(text, now=NOW)
    assert (r.start_at, r.end_at, r.title) == (start, end, title), text


@pytest.mark.parametrize("text", ["раз в месяц 5 числа отчёт", "once a month on the 5th report"])
def test_once_a_month_day(p, text):
    assert p.parse(text, now=NOW).recurrence.to_rrule() == "FREQ=MONTHLY;BYMONTHDAY=5"


def test_preprocess_cache_bounded():
    q = TimeSenseParser()
    for i in range(2000):
        q.parse("tomorrow at 10 meeting %d" % i, now=NOW)
        q.parse("завтра в 10 встреча %d" % i, now=NOW)
    assert len(q._en.__dict__.get("_pre_cache", {})) <= q._en._PRE_CACHE_MAX
    assert len(TimeSenseParser._NORM_CACHE) <= TimeSenseParser._NORM_CACHE_MAX


# ══ Этап 13: .ics по RFC 5545 ═════════════════════════════════════════════
import re as _re  # noqa: E402


def _ics_lines(ics):
    assert ics.endswith("\r\n") and "\n" not in ics.replace("\r\n", "")
    for ln in ics.split("\r\n"):
        assert len(ln.encode("utf-8")) <= 75, ln
    return ics.split("\r\n")


@pytest.mark.parametrize(
    "text,tz",
    [
        ("завтра в 10 встреча", None),
        ("каждую пятницу до конца октября отчёт", None),
        pytest.param("каждую пятницу в 18 отчёт", "Europe/Amsterdam", marks=needs_tzdata),
        pytest.param("every monday at 9 standup", "America/New_York", marks=needs_tzdata),
        ("с 10 до 11 созвон", "Europe/Moscow"),
        ("в октябре отпуск", None),
    ],
)
def test_ics_rfc_basics(p, text, tz):
    r = p.parse(text, now=NOW, tz=tz) if tz else p.parse(text, now=NOW)
    lines = _ics_lines(to_ics(r, stamp=datetime(2026, 9, 22, 12, 0)))
    stamp = [ln for ln in lines if ln.startswith("DTSTAMP:")][0]
    assert stamp == "DTSTAMP:20260922T120000Z"  # UTC с Z
    ics = "\r\n".join(lines)
    if "TZID=" in ics:
        assert "BEGIN:VTIMEZONE" in ics and "TZID:%s" % tz in ics
    if "DTSTART;VALUE=DATE" in ics and "UNTIL=" in ics:
        assert _re.search(r"UNTIL=\d{8}(?:\r|;|$)", ics)  # UNTIL — DATE, как DTSTART


def test_ics_aware_stamp_converted_to_utc(p):
    r = p.parse("завтра в 10 встреча", now=NOW)
    ics = to_ics(r, stamp=datetime(2026, 9, 22, 15, 0, tzinfo=MSK))
    assert "DTSTAMP:20260922T120000Z" in ics


def test_ics_alarm(p):
    r = p.parse("завтра в 10 встреча", now=NOW)
    ics = r.to_ics(alarm_minutes=15)
    assert "BEGIN:VALARM" in ics and "TRIGGER:-PT15M" in ics and "ACTION:DISPLAY" in ics
    assert "BEGIN:VALARM" not in to_ics(r)
    with pytest.raises(ValueError):
        to_ics(r, alarm_minutes=-5)


@needs_tzdata
def test_ics_vtimezone_once_per_zone(p):
    from timesense import to_ics_calendar

    rs = [p.parse(t, now=NOW, tz="Europe/Amsterdam")
          for t in ("каждую пятницу в 18 отчёт", "каждый понедельник в 9 стендап")]
    ics = to_ics_calendar(rs)
    assert ics.count("BEGIN:VTIMEZONE") == 1 and ics.count("BEGIN:VEVENT") == 2


@pytest.mark.parametrize(
    "key", ["Europe/Amsterdam", "America/New_York", "Australia/Sydney", "Europe/Moscow"]
)
def test_vtimezone_matches_zoneinfo(key):
    pytest.importorskip("dateutil")
    if not HAS_TZDATA:
        pytest.skip("нет базы IANA")
    from datetime import timezone as _tzu
    from zoneinfo import ZoneInfo
    from dateutil.rrule import rrulestr
    from timesense.ics import _vtimezone

    tz = ZoneInfo(key)
    comps, cur = [], None
    for ln in _vtimezone(tz, 2026):
        if ln in ("BEGIN:STANDARD", "BEGIN:DAYLIGHT"):
            cur = {}
        elif ln in ("END:STANDARD", "END:DAYLIGHT"):
            comps.append(cur)
            cur = None
        elif cur is not None:
            k, v = ln.split(":", 1)
            cur[k] = v

    def off(s):
        return timedelta(hours=int(s[1:3]), minutes=int(s[3:5])) * (1 if s[0] == "+" else -1)

    for y in (2026, 2027):
        got = sorted(
            (occ - off(c["TZOFFSETFROM"]), off(c["TZOFFSETTO"]))
            for c in comps if "RRULE" in c
            for occ in rrulestr(c["RRULE"], dtstart=datetime.strptime(c["DTSTART"], "%Y%m%dT%H%M%S"))
            .between(datetime(y, 1, 1), datetime(y, 12, 31, 23, 59), inc=True)
        )
        exp, t = [], datetime(y, 1, 1, tzinfo=_tzu.utc)
        prev = t.astimezone(tz).utcoffset()
        while t.year == y:
            t2 = t + timedelta(hours=1)
            o = t2.astimezone(tz).utcoffset()
            if o != prev:
                exp.append((t2.replace(tzinfo=None), o))
                prev = o
            t = t2
        assert got == exp, (key, y)


# ══ Этап 14: EN «in N weeks on <day>» (ошибочно заявлено исправленным в этапе 7),
#    части суток в прошлом, «около» ═════════════════════════════════════════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("in 3 weeks on monday report", datetime(2026, 10, 12)),
        ("через 3 недели в понедельник отчёт", datetime(2026, 10, 12)),
        ("in 2 weeks on friday", datetime(2026, 10, 9)),
        ("через 2 недели в пятницу", datetime(2026, 10, 9)),
        ("in a week on friday at 6pm meeting", datetime(2026, 10, 2, 18, 0)),
        ("через неделю в пятницу в 18 встреча", datetime(2026, 10, 2, 18, 0)),
        ("two weeks from friday", datetime(2026, 10, 9)),
        ("friday after next", datetime(2026, 10, 2)),
        ("the week after next", datetime(2026, 10, 5)),
        ("around 5 call", datetime(2026, 9, 22, 17, 0)),
        ("около 5 созвон", datetime(2026, 9, 22, 17, 0)),
        ("5ish call", datetime(2026, 9, 22, 17, 0)),
    ],
)
def test_stage14_points(p, text, expected):
    assert p.parse(text, now=NOW).when == expected, text


@pytest.mark.parametrize(
    "text,start",
    [
        ("this morning", datetime(2026, 9, 22, 9, 0)),
        ("сегодня утром", datetime(2026, 9, 22, 9, 0)),
        ("last night", datetime(2026, 9, 21, 22, 0)),
        ("прошлой ночью", datetime(2026, 9, 21, 22, 0)),
        ("yesterday evening", datetime(2026, 9, 21, 18, 0)),
        ("вчера вечером", datetime(2026, 9, 21, 18, 0)),
    ],
)
def test_past_dayparts_parity(p, text, start):
    r = p.parse(text, now=NOW)
    assert r.start_at == start and r.is_past is True, text


@pytest.mark.parametrize(
    "text,title",
    [
        ("early morning run", "run"), ("рано утром пробежка", "пробежка"),
        ("late evening walk", "walk"), ("поздно вечером прогулка", "прогулка"),
        ("around 5pm call", "call"), ("at 5 sharp call", "call"),
        ("this morning call the bank", "call the bank"),
        ("in 3 weeks on monday report", "report"),
    ],
)
def test_stage14_titles(p, text, title):
    assert p.parse(text, now=NOW).title == title, text


# ══ Предлог со своим словом остаётся в названии ═══════════════════════════
@pytest.mark.parametrize(
    "text,title",
    [
        ("В среду в 12:30 к врачу", "к врачу"),
        ("завтра в 10 к стоматологу", "к стоматологу"),
        ("сегодня в 18 на тренировку", "на тренировку"),
        ("завтра в 9 с командой", "с командой"),
        ("во вторник в 10 за документами", "за документами"),
        ("в 15 по проекту Atlas", "по проекту Atlas"),
        ("on wednesday at 12:30 to the doctor", "to the doctor"),
        ("tomorrow at 10 to the dentist", "to the dentist"),
        ("friday at 6 with the team", "with the team"),
        # висящие предлоги (слово съела дата/время или оно служебное) — снимаются
        ("завтра в 11 встреча на полтора часа", "встреча"),
        ("в следующем месяце 5 числа оплатить", "оплатить"),
        ("до следующего понедельника написать ответ партнёру", "написать ответ партнёру"),
        ("завтра в 10 или позже", ""),
        # ведущий участник снимается, если после него есть суть
        ("завтра в 10 с Иваном встреча", "встреча"),
        ("завтра в 10 у клиента встреча", "встреча"),
        ("set a reminder to call mom at 5pm", "call mom"),
        ("remind me in 15 minutes to turn off the stove", "turn off the stove"),
        ("turn the lights on at 7pm", "turn the lights on"),
    ],
)
def test_preposition_stays_with_its_word(p, text, title):
    assert p.parse(text, now=NOW).title == title, text


# ══ summary() и запуск из командной строки ════════════════════════════════
@pytest.mark.parametrize(
    "text,expected",
    [
        ("завтра в 10 встреча", "reminder  23.09.2026 10:00  «встреча»"),
        ("с 10 до 11:30 созвон в офисе",
         "calendar  23.09.2026 10:00 → 11:30  (90 мин)  @в офисе  «созвон»"),
        ("до пятницы отчёт", "task/deadline  до 25.09.2026 23:59  «отчёт»"),
        ("с 25 сентября по 3 октября отпуск",
         "task/period  25.09.2026 00:00 → 03.10.2026 23:59  «отпуск»"),
        ("в октябре отпуск",
         "task/fuzzy  01.10.2026 00:00 → 31.10.2026 23:59  ~примерно  «отпуск»"),
        ("после 17 позвонить", "task/open_start  22.09.2026 17:00  «позвонить»"),
        ("вчера в 10 был созвон", "reminder  21.09.2026 10:00  ПРОШЛО  «созвон»"),
        ("каждый понедельник и среду в 10 планёрка",
         "reminder ⟳ FREQ=WEEKLY;BYDAY=MO,WE  23.09.2026 10:00  «планёрка»"),
        ("tomorrow at 10 meeting for 2 hours",
         "calendar  23.09.2026 10:00 → 12:00  (120 min)  «meeting»"),  # подписи на языке фразы
    ],
)
def test_summary_line(p, text, expected):
    assert p.parse(text, now=NOW).summary() == expected, text


def test_summary_shows_timezone(p):
    s = p.parse("завтра в 10 встреча", now=NOW, tz=MSK).summary()
    assert s.startswith("reminder  23.09.2026 10:00 +0300")


def test_cli(capsys):
    from timesense.__main__ import main

    assert main(["--now", "2026-09-22 14:00", "в четверг утром в садик"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "task/fuzzy  24.09.2026 09:00 → 12:00  ~примерно  «в садик»"

    assert main(["--now", "2026-09-22 14:00", "--multi", "завтра в 10 встреча, в 13 обед"]) == 0
    assert capsys.readouterr().out.count("reminder") == 2

    # не распознано → код возврата 1 и причина
    assert main(["--now", "2026-09-22 14:00", "купить молоко"]) == 1
    assert "no_datetime" in capsys.readouterr().out

    assert main(["--now", "2026-09-22 14:00", "в понедельник или вторник созвон"]) == 1
    out = capsys.readouterr().out
    assert "ambiguous" in out and out.count("вариант:") == 2

    assert main(["--now", "2026-09-22 14:00", "--json", "завтра в 10 встреча"]) == 0
    import json as _json

    assert _json.loads(capsys.readouterr().out)["datetime"] == "2026-09-23T10:00:00"

    assert main(["--now", "2026-09-22 14:00", "--ics", "завтра в 10 встреча"]) == 0
    assert "BEGIN:VEVENT" in capsys.readouterr().out


# ══ Новый год — момент, а не день: «до/к/перед» = конец 31 декабря ════════
@pytest.mark.parametrize(
    "text,deadline",
    [
        ("до нового года поздравить команду", datetime(2026, 12, 31, 23, 59)),
        ("до нового года в 23:50 поздравить команду", datetime(2026, 12, 31, 23, 50)),
        ("к новому году подготовить отчёт", datetime(2026, 12, 31, 23, 59)),
        ("перед новым годом купить подарки", datetime(2026, 12, 31, 23, 59)),
        ("by new year finish the project", datetime(2026, 12, 31, 23, 59)),
        ("before new year send the report", datetime(2026, 12, 31, 23, 59)),
    ],
)
def test_before_new_year_is_dec_31(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE, text
    assert r.deadline == deadline, text
    assert "нов" not in r.title.lower() and "new" not in r.title.lower()


@pytest.mark.parametrize(
    "text,start",
    [
        # сам праздник — 1 января; «до» тут ни при чём
        ("на новый год поздравить", datetime(2027, 1, 1)),
        ("в новый год отдыхать", datetime(2027, 1, 1)),
        ("в новогоднюю ночь в 23:50 шампанское", datetime(2026, 12, 31, 23, 50)),
    ],
)
def test_new_year_itself_is_jan_1(p, text, start):
    assert p.parse(text, now=NOW).when == start, text


def test_other_holidays_keep_their_own_day(p):
    # у обычных праздников «до» — конец самого дня праздника
    assert p.parse("до рождества купить подарки", now=NOW).deadline == datetime(2027, 1, 7, 23, 59)
    assert p.parse("до 8 марта подарок", now=NOW).deadline == datetime(2027, 3, 8, 23, 59)

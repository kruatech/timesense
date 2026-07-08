"""English locale test suite (pytest). Reference now = Sat 2026-02-14 14:00."""

from datetime import datetime
from timesense import TimeSenseParser, TimeConfig
from timesense.models.event_types import ReminderResult, CalendarResult, TaskResult

NOW = datetime(2026, 2, 14, 14, 0)  # Saturday
p = TimeSenseParser()


def parse(t, **kw):
    return p.parse(t, now=NOW, **kw)


# ── relative days & weekdays ────────────────────────────────────────────
def test_tomorrow_at_time():
    r = parse("tomorrow at 5pm meeting")
    assert isinstance(r, ReminderResult)
    assert r.datetime_at.day == 15 and r.datetime_at.hour == 17
    assert r.title == "meeting"
    assert r.detected_language == "en"


def test_today_tonight():
    assert parse("today at 9am call").datetime_at.day == 14
    r = parse("tonight call")
    assert isinstance(r, TaskResult) and r.start_at.hour == 18


def test_day_after_tomorrow():
    r = parse("day after tomorrow at noon lunch")
    assert r.datetime_at.day == 16 and r.datetime_at.hour == 12


def test_next_this_last_weekday():
    assert parse("next Friday at 10 sync").datetime_at.day == 27  # next = nearest + 7
    assert parse("this Monday at 9 standup").datetime_at.day == 16
    # last Friday = 13.02 (past)
    r = parse("last Friday review")
    assert isinstance(r, TaskResult) and r.start_at.day == 13


def test_weekday_bare():
    # bare "Friday" → nearest upcoming Friday (20.02)
    r = parse("Friday deadline")
    assert isinstance(r, TaskResult) and r.start_at.day == 20


# ── month-name & numeric dates ──────────────────────────────────────────
def test_month_name_forms():
    assert (
        parse("Feb 17 dentist").start_at.month == 2 and parse("Feb 17 dentist").start_at.day == 17
    )
    assert parse("17 Feb dentist").start_at.day == 17
    r = parse("March 3rd party")
    assert r.start_at.month == 3 and r.start_at.day == 3


def test_month_with_year():
    r = parse("Feb 17 2027 conference")
    assert r.start_at.year == 2027 and r.start_at.month == 2 and r.start_at.day == 17


def test_numeric_us_and_iso():
    assert parse("3/17 review").start_at.month == 3 and parse("3/17 review").start_at.day == 17
    r = parse("2026-02-17 at 10 sync")
    assert isinstance(r, ReminderResult) and r.datetime_at.day == 17 and r.datetime_at.hour == 10


# ── times & am/pm ───────────────────────────────────────────────────────
def test_ampm():
    assert parse("at 7am workout").datetime_at.hour == 7
    assert parse("at 7pm dinner").datetime_at.hour == 19
    assert parse("at 12pm lunch").datetime_at.hour == 12
    assert parse("at 12am reminder").datetime_at.hour == 0
    assert parse("noon lunch").datetime_at.hour == 12
    assert parse("midnight backup").datetime_at.hour == 0


def test_2400_time():
    assert parse("at 17:00 sync").datetime_at.hour == 17
    assert parse("9:30am standup").datetime_at.minute == 30


# ── relative "in N units" ───────────────────────────────────────────────
def test_in_units():
    assert parse("in 2 hours call").datetime_at.hour == 16
    assert parse("in 30 minutes coffee").datetime_at.minute == 30
    r = parse("in 3 days review")
    assert r.start_at.day == 17
    r = parse("in 2 weeks demo")
    assert r.start_at.day == 28


# ── ranges → calendar ───────────────────────────────────────────────────
def test_ranges():
    r = parse("from 9 to 5 work shift")
    assert isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 17
    r = parse("9am-11am call")
    assert isinstance(r, CalendarResult) and r.duration_minutes == 120
    r = parse("between 10 and 12 be available")
    assert isinstance(r, CalendarResult) and r.start_at.hour == 10 and r.end_at.hour == 12


def test_range_on_explicit_date():
    r = parse("tomorrow from 9am to 11am workshop")
    assert (
        isinstance(r, CalendarResult)
        and r.start_at.day == 15
        and r.start_at.hour == 9
        and r.end_at.hour == 11
    )


# ── recurrence ──────────────────────────────────────────────────────────
def test_recurrence_basic():
    assert parse("every day at 9am standup").recurrence.to_rrule() == "FREQ=DAILY"
    assert parse("daily standup").recurrence.frequency == "DAILY"
    assert parse("every Monday at 10 sync").recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO"


def test_recurrence_weekday_set():
    assert (
        parse("every weekday at 9 standup").recurrence.to_rrule()
        == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    )
    assert parse("on weekdays standup").recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"


def test_recurrence_interval():
    r = parse("every 2 weeks on Monday review")
    assert (
        r.recurrence.frequency == "WEEKLY"
        and r.recurrence.interval == 2
        and r.recurrence.by_day == ["MO"]
    )
    assert parse("every other week sync").recurrence.interval == 2


def test_recurrence_monthly_day():
    r = parse("every month on the 15th report")
    assert r.recurrence.frequency == "MONTHLY" and r.recurrence.by_month_day == [15]


# ── deadlines ───────────────────────────────────────────────────────────
def test_deadline_weekday_and_time():
    r = parse("by Friday submit report")
    assert isinstance(r, TaskResult) and r.task_type.value == "deadline" and r.deadline.day == 20
    r = parse("by 5pm finish")
    assert r.task_type.value == "deadline" and r.deadline.hour == 17


def test_deadline_end_of_period():
    r = parse("by end of month pay invoice")
    assert r.task_type.value == "deadline" and r.deadline.day == 28 and r.deadline.month == 2
    r = parse("by end of week deadline")
    assert r.task_type.value == "deadline"


# ── duration ────────────────────────────────────────────────────────────
def test_duration_with_time():
    r = parse("meeting tomorrow at 10 for 2 hours")
    assert isinstance(r, CalendarResult) and r.start_at.hour == 10 and r.end_at.hour == 12


# ── dayparts / fuzzy ────────────────────────────────────────────────────
def test_daypart_with_weekday():
    r = parse("this Friday evening call")
    assert (
        isinstance(r, TaskResult)
        and r.task_type.value == "fuzzy"
        and r.start_at.day == 20
        and r.start_at.hour == 18
    )


def test_beginning_end_of_period():
    r = parse("end of the month review")
    assert isinstance(r, TaskResult) and r.task_type.value == "fuzzy"


# ── language routing / detection ────────────────────────────────────────
def test_auto_detect_en():
    r = parse("meeting tomorrow at 3pm")
    assert r is not None and r.detected_language == "en"


def test_explicit_language_forces_en():
    # cyrillic-free but forced en
    r = p.parse("standup every monday at 10", now=NOW, language="en")
    assert r is not None and r.recurrence.by_day == ["MO"]


def test_ru_still_default_for_cyrillic():
    r = p.parse("завтра в 10 встреча", now=NOW)
    assert r is not None and r.detected_language == "ru"
    assert r.datetime_at.hour == 10 and r.datetime_at.day == 15


def test_prefer_nearest_future_false_en():
    pf = TimeSenseParser(TimeConfig(prefer_nearest_future=False, default_language="en"))
    r = pf.parse("at 10 meeting", now=NOW)
    assert isinstance(r, ReminderResult) and r.datetime_at.day == 14 and r.datetime_at.hour == 10


# ── recurrence modifiers: COUNT / UNTIL / EXCEPT ─────────────────────────
def test_recurrence_count():
    r = parse("every Monday 5 times gym")
    assert r.recurrence.count == 5 and r.recurrence.by_day == ["MO"]
    assert "COUNT=5" in r.recurrence.to_rrule()
    assert r.title == "gym"


def test_recurrence_until_period_and_month():
    r = parse("every Friday until end of March sync")
    assert (
        r.recurrence.by_day == ["FR"]
        and r.recurrence.until.month == 3
        and r.recurrence.until.day == 31
    )
    assert r.title == "sync"
    r = parse("every day until March 20 standup")
    assert (
        r.recurrence.frequency == "DAILY" and r.recurrence.until.day == 20 and r.title == "standup"
    )


def test_recurrence_except():
    assert (
        parse("every day except weekends workout").recurrence.to_rrule()
        == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    )
    r = parse("every day except Sunday run")
    assert (
        r.recurrence.frequency == "WEEKLY"
        and "SU" not in r.recurrence.by_day
        and len(r.recurrence.by_day) == 6
    )
    assert r.title == "run"
    assert (
        parse("every day except Saturday and Sunday gym").recurrence.to_rrule()
        == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    )


# ── multi-event parse (EN) ───────────────────────────────────────────────
def test_parse_multi_en_and():
    res = p.parse_multi("meeting tomorrow at 10 and lunch at 12", now=NOW)
    assert len(res) == 2
    assert res[0].title == "meeting" and res[0].datetime_at.hour == 10
    assert res[1].title == "lunch" and res[1].datetime_at.hour == 12


def test_parse_multi_en_commas():
    res = p.parse_multi("call at 9am, review at 2pm, gym at 6pm", now=NOW)
    assert len(res) == 3
    assert [x.title for x in res] == ["call", "review", "gym"]


def test_parse_multi_between_not_split():
    # 'and' внутри 'between X and Y' не должно ломать одно событие
    res = p.parse_multi("between 10 and 12 be available", now=NOW)
    assert len(res) == 1 and isinstance(res[0], CalendarResult)

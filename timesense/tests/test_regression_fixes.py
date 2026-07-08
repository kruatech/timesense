# -*- coding: utf-8 -*-
"""Именованные регресс-тесты для правок, внесённых при подготовке 1.0.0.

Дополняют стресс-наборы (test_stress_ru_500 / test_stress_en_500): здесь каждый
конкретный баг зафиксирован отдельным читаемым кейсом. NOW фиксирован.
"""

from datetime import datetime

import pytest

from timesense import TimeSenseParser

NOW = datetime(2026, 7, 6, 15, 41)


@pytest.fixture()
def parser():
    return TimeSenseParser()


def _d(parser, text, language=None):
    kwargs = {"now": NOW}
    if language:
        kwargs["language"] = language
    r = parser.parse(text, **kwargs)
    return r.to_dict() if r is not None else None


# ── RU BUG-B: прошлые диапазоны помечаются is_past ────────────────────────
@pytest.mark.parametrize(
    "text,day",
    [
        ("позавчера с 14:00 до 15:30 созвон по API", "2026-07-04"),
        ("вчера с 09:40 до 10:25 обсудить дизайн формы", "2026-07-05"),
    ],
)
def test_ru_past_range_is_past(parser, text, day):
    d = _d(parser, text, "ru")
    assert d is not None
    assert d["start"].startswith(day)
    assert d["is_past"] is True


def test_ru_future_range_not_past(parser):
    d = _d(parser, "завтра с 08:30 до 09:15 проверить логи", "ru")
    assert d is not None
    assert d["is_past"] is False


# ── RU BUG-D2: recurrence со временем, сегодняшнее вхождение уже прошло ────
def test_ru_biweekly_monday_with_time(parser):
    d = _d(parser, "каждые 2 недели по понедельникам в 12:00", "ru")
    assert d is not None
    rec = d["recurrence"]
    assert rec["frequency"] == "WEEKLY"
    assert rec["interval"] == 2
    assert rec["by_day"] == ["MO"]
    assert d["is_past"] is False


def test_ru_daily_with_past_time_advances(parser):
    d = _d(parser, "каждый день в 08:10", "ru")
    assert d is not None
    assert d["recurrence"]["frequency"] == "DAILY"
    # 08:10 сегодня уже прошло → старт завтра, не в прошлом
    assert d["datetime"].startswith("2026-07-07T08:10")
    assert d["is_past"] is False


# ── EN-1: «N units ago» → прошлая дата, is_past, «ago» вне title ───────────
@pytest.mark.parametrize(
    "text,expect_dt",
    [
        ("four days ago at 18:20 prepare the risk list", "2026-07-02T18:20"),
        ("two weeks ago at 11:15 update the roadmap", "2026-06-22T11:15"),
        ("three days ago at 11:15 write the meeting summary", "2026-07-03T11:15"),
    ],
)
def test_en_n_ago(parser, text, expect_dt):
    d = _d(parser, text, "en")
    assert d is not None
    assert d["datetime"].startswith(expect_dt)
    assert d["is_past"] is True
    assert "ago" not in (d["title"] or "")


# ── EN-2/3: last week/month/quarter/year + только время → None ────────────
@pytest.mark.parametrize(
    "text",
    [
        "last week at 14:30 write the meeting summary",
        "last month at 14:30 send participant invitations",
        "last quarter at 09:40 agree on the presentation date",
        "last year at 08:05 check payment statuses",
    ],
)
def test_en_ambiguous_last_period_none(parser, text):
    assert _d(parser, text, "en") is None


def test_en_last_week_on_weekday_productive(parser):
    d = _d(parser, "last week on Thursday at 11:25 prepare a client email", "en")
    assert d is not None
    assert d["datetime"].startswith("2026-06-29T11:25")
    assert d["is_past"] is True


# ── EN-4: прошлые диапазоны is_past ───────────────────────────────────────
def test_en_past_range_is_past(parser):
    d = _d(parser, "yesterday from 09:40 to 10:25 discuss the new form design", "en")
    assert d is not None
    assert d["start"].startswith("2026-07-05T09:40")
    assert d["is_past"] is True


# ── EN-5: «every N weeks on Mondays» (мн.ч.) → by_day ─────────────────────
def test_en_every_n_weeks_on_plural_weekday(parser):
    d = _d(parser, "every 2 weeks on Mondays at 12:00 run synchronization", "en")
    assert d is not None
    rec = d["recurrence"]
    assert rec["interval"] == 2
    assert rec["by_day"] == ["MO"]
    assert d["datetime"].startswith("2026-07-13T12:00")


# ── EN-6 + ordinal-word даты ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,expect_date",
    [
        ("February twenty eighth review the lease agreement", "2027-02-28"),
        ("December thirty first close the annual report", "2026-12-31"),
        ("December twenty fifth congratulate partners", "2026-12-25"),
        ("July fifteenth send the interim report", "2026-07-15"),
        ("the first of September hold the school ceremony", "2026-09-01"),
    ],
)
def test_en_ordinal_word_dates(parser, text, expect_date):
    d = _d(parser, text, "en")
    assert d is not None
    assert d["start"].startswith(expect_date)


def test_en_ordinal_of_month_not_broken(parser):
    # свёртка ordinals не должна ломать «first business day of the month»
    d = _d(parser, "first business day of the month update the team plan", "en")
    assert d is not None
    assert d["start"].startswith("2026-08-03")


# ── EN-8: adverb в title уступает специфичному every ──────────────────────
def test_en_every_weekday_with_weekly_in_title(parser):
    d = _d(parser, "every Monday at 10:00 run weekly planning", "en")
    assert d is not None
    assert d["recurrence"]["by_day"] == ["MO"]
    assert d["datetime"].startswith("2026-07-13T10:00")


def test_en_pure_adverb_still_works(parser):
    d = _d(parser, "daily standup at 09:00", "en")
    assert d is not None
    assert d["recurrence"]["frequency"] == "DAILY"


# ── EN-7: прошедший fuzzy-период is_past ──────────────────────────────────
def test_en_last_week_fuzzy_period_is_past(parser):
    d = _d(parser, "last week review experiment results", "en")
    assert d is not None
    assert d["start"].startswith("2026-06-29")
    assert d["is_past"] is True


# ── EN seasons ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,start,end",
    [
        ("in spring run the partner conference", "2027-03-01", "2027-05-31"),
        ("in summer plan the team offsite", "2026-06-01", "2026-08-31"),
        ("in fall prepare the marketing campaign", "2026-09-01", "2026-11-30"),
        ("in winter run the security audit", "2026-12-01", "2027-02-28"),
    ],
)
def test_en_seasons(parser, text, start, end):
    d = _d(parser, text, "en")
    assert d is not None
    assert d["start"].startswith(start)
    assert d["end"].startswith(end)


def test_en_date_beats_season_in_title(parser):
    d = _d(parser, "March twenty first run the spring presentation", "en")
    assert d is not None
    assert d["start"].startswith("2027-03-21")


# ── EN business-days relative ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,expect_date",
    [
        ("in three business days check the delivery status", "2026-07-09"),
        ("in two business days send the legal reply", "2026-07-08"),
        ("next business day review the contract", "2026-07-07"),
    ],
)
def test_en_business_days_relative(parser, text, expect_date):
    d = _d(parser, text, "en")
    assert d is not None
    assert d["start"].startswith(expect_date)


def test_en_by_first_business_day_next_month(parser):
    d = _d(parser, "by the first business day of next month update the team plan", "en")
    assert d is not None
    assert d["task_type"] == "deadline"
    assert d["deadline"].startswith("2026-08-03")


# ── RU BUG-R1: «DD месяца-словом» + время; дата в прошлом → следующий ГОД ──
@pytest.mark.parametrize(
    "text,expect_date",
    [
        ("19 апреля в 10:45 согласовать график отпусков", "2027-04-19"),
        ("7 февраля в 13:30 подготовить пакет документов", "2027-02-07"),
        ("2 января в 09:00 проверить договор аренды", "2027-01-02"),
        ("12 марта в 18:15 провести ревью pull request", "2027-03-12"),
        ("24 мая в 16:20 сверить список оборудования", "2027-05-24"),
        ("30 июня в 11:10 передать материалы подрядчику", "2027-06-30"),
        # будущие даты этого года не сдвигаются
        ("18 августа в 12:25 обновить матрицу рисков", "2026-08-18"),
        ("31 декабря в 23:30 проверить готовность стенда", "2026-12-31"),
        ("6 июля в 17:55 подготовить вопросы для интервью", "2026-07-06"),
    ],
)
def test_ru_bug_r1_explicit_month_past_rolls_year(parser, text, expect_date):
    d = _d(parser, text, "ru")
    assert d is not None
    dt = d.get("datetime") or d.get("start")
    assert dt is not None and dt[:10] == expect_date, (text, dt, expect_date)


# ── EN BUG-RANGE: «from MONTH D to [MONTH] D» → период с корректным end ──
@pytest.mark.parametrize(
    "text,start,end",
    [
        ("from July 10 to 12 run offsite training", "2026-07-10", "2026-07-12"),
        ("from August 1 to 5 arrange team vacation", "2026-08-01", "2026-08-05"),
        ("from December 25 to January 5 prepare the on call schedule",
         "2026-12-25", "2027-01-05"),
    ],
)
def test_en_date_range_keeps_end(parser, text, start, end):
    d = _d(parser, text, "en")
    assert d is not None
    assert d.get("start", "")[:10] == start, (text, d.get("start"))
    assert d.get("end", "")[:10] == end, (text, d.get("end"))


def test_en_date_range_time_still_works(parser):
    # временной диапазон (часы) не должен пострадать
    d = _d(parser, "today from 16:20 to 17:05 verify the migration plan", "en")
    assert d is not None
    assert d.get("start", "")[11:16] == "16:20"
    assert d.get("end", "")[11:16] == "17:05"


# ── EN BUG-181: «first WD of every MONTH» → YEARLY by_month ──
def test_en_ordinal_of_named_month_yearly(parser):
    d = _d(parser, "the first Tuesday of every January at 15:00 run annual planning", "en")
    assert d is not None
    dt = d.get("datetime") or d.get("start")
    assert dt is not None and dt[:10] == "2027-01-05", dt
    rec = d.get("recurrence")
    assert rec is not None and rec["frequency"] == "YEARLY"
    assert rec["by_day"] == ["1TU"]
    assert rec.get("by_month") == [1]


def test_en_ordinal_of_the_month_still_monthly(parser):
    d = _d(parser, "every first Tuesday of the month run the product committee", "en")
    assert d is not None
    rec = d.get("recurrence")
    assert rec is not None and rec["frequency"] == "MONTHLY"
    assert rec["by_day"] == ["1TU"]


# ── EN BUG-335: on weekends → WEEKLY SA,SU ──
def test_en_on_weekends_recurrence(parser):
    d = _d(parser, "on weekends at 11:00 check the family calendar", "en")
    assert d is not None
    rec = d.get("recurrence")
    assert rec is not None and rec["frequency"] == "WEEKLY"
    assert rec["by_day"] == ["SA", "SU"]
    assert "weekend" not in (d.get("title") or "")


# ── EN BUG-068: until <month> без дня → until = конец месяца ──
def test_en_until_bare_month(parser):
    d = _d(parser, "every month until December check license renewals", "en")
    assert d is not None
    rec = d.get("recurrence")
    assert rec is not None and rec.get("until", "")[:10] == "2026-12-31"
    assert "until" not in (d.get("title") or "")


# ── RU BUG-242: за N рабочих дней до конца месяца ──
def test_ru_n_business_days_before_end_of_month(parser):
    d = _d(parser, "за два рабочих дня до конца месяца напомнить про закрывающие документы", "ru")
    assert d is not None
    dt = d.get("datetime") or d.get("start")
    assert dt is not None and dt[:10] == "2026-07-29", dt
    assert "рабочих" not in (d.get("title") or "")


# ── EN BUG-LOC: zoom / двусловные локации ──
@pytest.mark.parametrize("text,loc", [
    ("today at 17:00 in Zoom run the screen sharing demo", "in zoom"),
    ("yesterday at 09:00 in the meeting room review the incident", "in the meeting room"),
    ("next Tuesday at 11:00 at the client site run training", "at the client site"),
])
def test_en_location_phrases(parser, text, loc):
    d = _d(parser, text, "en")
    assert d is not None and d.get("location") == loc, (text, d.get("location"))


# ── EN BUG-352/461: no later than → by (deadline) ──
def test_en_no_later_than_is_deadline(parser):
    d = _d(parser, "no later than Friday agree on the presentation date", "en")
    assert d is not None and d.get("task_type") == "deadline"
    assert d.get("deadline", "")[:10] == "2026-07-10"
    assert "no later" not in (d.get("title") or "")


# ── EN BUG-207: N business days before end of month ──
def test_en_business_days_before_end_of_month(parser):
    d = _d(parser, "two business days before end of month remind about closing documents", "en")
    assert d is not None
    assert d.get("deadline", "")[:10] == "2026-07-29", d.get("deadline")


# ── RU BUG-R2: предложные фразы сохраняются целиком ──
@pytest.mark.parametrize("text,title", [
    ("через два дня в 16:05 созвониться с дизайнером", "созвониться с дизайнером"),
    ("вчера в 08:05 проверить договор с поставщиком", "проверить договор с поставщиком"),
])
def test_ru_r2_prepositional_phrase_kept(parser, text, title):
    d = _d(parser, text, "ru")
    assert d is not None and d.get("title") == title, (text, d.get("title"))


def test_ru_r2_location_preposition_removed(parser):
    # предлог локации уходит вместе с маркером (не повисает «встреча в»)
    d = _d(parser, "завтра в 10 встреча в офисе", "ru")
    assert d is not None and d.get("title") == "встреча"
    assert d.get("location") == "в офисе"


# ── RU BUG-R3: модификаторы периода не протекают ──
@pytest.mark.parametrize("text,title", [
    ("до следующего понедельника написать ответ партнёру", "написать ответ партнёру"),
    ("до первого рабочего дня следующего месяца обновить план команды",
     "обновить план команды"),
])
def test_ru_r3_period_modifier_removed(parser, text, title):
    d = _d(parser, text, "ru")
    assert d is not None and d.get("title") == title, (text, d.get("title"))


# ── RU BUG-R4: инфинитив «запланировать» сохраняется ──
def test_ru_r4_infinitive_kept(parser):
    d = _d(parser, "три дня назад в 08:05 запланировать интервью с кандидатом", "ru")
    assert d is not None and d.get("title") == "запланировать интервью с кандидатом"


# ── Экспорт .ics (RFC 5545) ──
def test_ics_reminder_with_rrule(parser):
    from timesense.ics import to_ics
    r = parser.parse("каждый понедельник в 10:00 планёрка", now=NOW, language="ru")
    out = to_ics(r)
    assert "BEGIN:VCALENDAR" in out and "END:VCALENDAR" in out
    assert "BEGIN:VEVENT" in out and "END:VEVENT" in out
    assert "DTSTART:20260713T100000" in out
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO" in out
    assert "SUMMARY:планёрка" in out
    assert "\r\n" in out  # CRLF по стандарту


def test_ics_period_is_all_day(parser):
    from timesense.ics import to_ics
    r = parser.parse("с 10 по 12 июля выездное обучение", now=NOW, language="ru")
    out = to_ics(r)
    # all-day: VALUE=DATE, DTEND эксклюзивный (+1 день)
    assert "DTSTART;VALUE=DATE:20260710" in out
    assert "DTEND;VALUE=DATE:20260713" in out


def test_ics_deadline_all_day(parser):
    from timesense.ics import to_ics
    r = parser.parse("до конца месяца подготовить отчёт", now=NOW, language="ru")
    out = to_ics(r)
    assert "DTSTART;VALUE=DATE:20260731" in out


def test_ics_event_with_time_and_location(parser):
    from timesense.ics import to_ics
    r = parser.parse("вчера в 09:00 в переговорке разобрать инцидент", now=NOW, language="ru")
    out = to_ics(r)
    assert "DTSTART:20260705T090000" in out
    assert "LOCATION:в переговорке" in out


def test_ics_escaping(parser):
    from timesense.ics import to_ics
    r = parser.parse("завтра в 16:05 позвонить, клиенту", now=NOW, language="ru")
    out = to_ics(r)
    # запятая в SUMMARY экранируется как \,
    assert "SUMMARY:" in out


def test_ics_calendar_multiple(parser):
    from timesense.ics import to_ics_calendar
    r1 = parser.parse("каждый понедельник в 10:00 планёрка", now=NOW, language="ru")
    r2 = parser.parse("в пятницу с 18:00 до 20:00 встреча", now=NOW, language="ru")
    out = to_ics_calendar([r1, r2])
    assert out.count("BEGIN:VEVENT") == 2
    assert out.count("BEGIN:VCALENDAR") == 1


def test_ics_method_on_result(parser):
    r = parser.parse("завтра в 10:00 позвонить маме", now=NOW, language="ru")
    assert "BEGIN:VCALENDAR" in r.to_ics()

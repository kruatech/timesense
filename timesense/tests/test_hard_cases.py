# -*- coding: utf-8 -*-
"""Самые сложные комбинированные фразы (RU и EN) с ожиданиями, вычисленными
независимо от парсера по календарю. NOW = вторник, 22.09.2026 14:00.

Календарь-шпаргалка: 22.09.2026 — вт; 25.09 — пт; 26/27.09 — сб/вс;
30.09 — ср (последний день сентября, рабочий); 01.10 — чт; вторая пятница
октября — 09.10; первый понедельник октября — 05.10.
"""

from datetime import datetime, timedelta, timezone

import pytest

from timesense import ParseStatus, TaskType, TimeSenseParser

NOW = datetime(2026, 9, 22, 14, 0)
MSK = timezone(timedelta(hours=3))


@pytest.fixture(scope="module")
def p():
    return TimeSenseParser()


def _end(r):
    return getattr(r, "end_at", None) or getattr(r, "deadline", None)


# ── повторы: RU и EN с одинаковым ожиданием ───────────────────────────────
REC = [
    ("каждую вторую пятницу месяца в 18:30 ретро в переговорке",
     "every second Friday of the month at 6:30pm retro in the meeting room",
     datetime(2026, 10, 9, 18, 30), "FREQ=MONTHLY;BYDAY=2FR", ("ретро", "retro")),
    ("каждый будний день кроме пятницы в 9:15 до конца октября стендап",
     "every weekday except friday at 9:15 until end of october standup",
     datetime(2026, 9, 23, 9, 15), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH;UNTIL=20261031T235900",
     ("стендап", "standup")),
    ("каждый понедельник и среду в 10 созвон 5 раз",
     "every monday and wednesday at 10 call 5 times",
     datetime(2026, 9, 23, 10, 0), "FREQ=WEEKLY;BYDAY=MO,WE;COUNT=5", ("созвон", "call")),
    ("каждые 2 недели по средам в 11 синк до конца года",
     "every other wednesday at 11 sync until end of year",
     datetime(2026, 9, 23, 11, 0), "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;UNTIL=20261231T235900",
     ("синк", "sync")),
    ("первого числа каждого месяца в 9 оплатить аренду",
     "on the 1st of every month at 9 pay rent",
     datetime(2026, 10, 1, 9, 0), "FREQ=MONTHLY;BYMONTHDAY=1", ("оплатить аренду", "pay rent")),
    ("каждый первый понедельник месяца в 10 планирование",
     "first monday of every month at 10 planning",
     datetime(2026, 10, 5, 10, 0), "FREQ=MONTHLY;BYDAY=1MO", ("планирование", "planning")),
    ("по будням кроме понедельника в 7:30 зарядка",
     "every weekday except monday at 7:30 workout",
     datetime(2026, 9, 23, 7, 30), "FREQ=WEEKLY;BYDAY=TU,WE,TH,FR", ("зарядка", "workout")),
]


@pytest.mark.parametrize("ru,en,when,rrule,titles", REC, ids=[x[1] for x in REC])
def test_hard_recurrence(p, ru, en, when, rrule, titles):
    got, errors = {}, []
    for text, title in ((ru, titles[0]), (en, titles[1])):
        r = p.parse(text, now=NOW)
        got[text] = r and (r.when, r.recurrence and r.recurrence.to_rrule(), r.title)
        if r is None or r.when != when or not r.recurrence or r.recurrence.to_rrule() != rrule \
                or r.title != title:
            errors.append(text)
    assert not errors, got


# ── разовые события: RU и EN ──────────────────────────────────────────────
ONE = [
    ("в следующий вторник с 23:15 до 00:45 проверить ночное окно",
     "next tuesday from 23:15 to 00:45 check the night window",
     # во вторник «в следующий вторник» = через неделю (как и просто «во вторник»)
     datetime(2026, 9, 29, 23, 15), datetime(2026, 9, 30, 0, 45)),
    ("завтро в 10 в офисе совещание на полтора часа",
     "tmrw at 10 meeting at the office for an hour and a half",
     datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 11, 30)),
    ("в последний рабочий день месяца в 17 отчёт",
     "last business day of the month at 5pm report",
     datetime(2026, 9, 30, 17, 0), None),
    ("с пятницы по понедельник поездка", "from friday to monday trip",
     datetime(2026, 9, 25), datetime(2026, 9, 28, 23, 59)),
    ("через 2 часа 30 минут позвонить", "in 2 hours and 30 minutes call",
     datetime(2026, 9, 22, 16, 30), None),
    ("на выходных в субботу в 12 дача", "on the weekend on saturday at 12 cottage",
     datetime(2026, 9, 26, 12, 0), None),
    ("до пятницы 18:00 сдать отчёт", "no later than friday 6pm submit the report",
     datetime(2026, 9, 25, 18, 0), datetime(2026, 9, 25, 18, 0)),
    # Новый год наступает 1 января 00:00 → «до нового года» = конец 31 декабря
    ("до нового года сдать проект", "by new year finish the project",
     datetime(2026, 12, 31, 23, 59), datetime(2026, 12, 31, 23, 59)),
    ("в 23:59 31 декабря подвести итоги", "at 23:59 on december 31 wrap up the year",
     datetime(2026, 12, 31, 23, 59), None),
    ("1 января в 00:00 поздравить", "january 1 at 00:00 congratulate",
     datetime(2027, 1, 1, 0, 0), None),
]


@pytest.mark.parametrize("ru,en,when,end", ONE, ids=[x[1] for x in ONE])
def test_hard_one_off(p, ru, en, when, end):
    got, errors = {}, []
    for text in (ru, en):
        r = p.parse(text, now=NOW)
        got[text] = r and (r.when, _end(r), r.is_past)
        if r is None or r.when != when or (end is not None and _end(r) != end) or r.is_past:
            errors.append(text)
    assert not errors, got


def test_hard_business_days_before_month_end(p):
    # 30.09 — среда; два рабочих дня до конца месяца → понедельник 28.09
    r = p.parse("за 2 рабочих дня до конца месяца отчёт", now=NOW)
    assert r.when.date() == datetime(2026, 9, 28).date()


# ── пояса ─────────────────────────────────────────────────────────────────
def test_hard_timezones(p):
    r = p.parse("завтра в 10 мск созвон с клиентом", now=NOW, tz="Europe/Amsterdam")
    assert r.when.astimezone(timezone.utc) == datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc)
    assert r.title == "созвон с клиентом"
    r = p.parse("tomorrow at 10am EST call with the client", now=NOW, tz=MSK)
    assert r.when == datetime(2026, 9, 23, 17, 0, tzinfo=MSK)  # 10:00 EDT = 14:00 UTC
    assert r.title == "call with the client"
    r = p.parse("завтра в 10 по москве созвон", now=NOW, tz="Asia/Novosibirsk")
    assert r.when.astimezone(timezone.utc) == datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc)


# ── несколько событий ─────────────────────────────────────────────────────
def test_hard_multi(p):
    rs = p.parse_multi("через неделю в пятницу в 18 встреча, в субботу в 12 дача", now=NOW)
    assert [(r.when, r.title) for r in rs] == [
        (datetime(2026, 10, 2, 18, 0), "встреча"), (datetime(2026, 9, 26, 12, 0), "дача")]
    rs = p.parse_multi("tomorrow 10am standup, 1pm lunch with Ann and 6pm gym", now=NOW)
    assert [(r.when, r.title) for r in rs] == [
        (datetime(2026, 9, 23, 10, 0), "standup"), (datetime(2026, 9, 23, 13, 0), "lunch with Ann"),
        (datetime(2026, 9, 23, 18, 0), "gym")]


# ── невалидное и неоднозначное ────────────────────────────────────────────
@pytest.mark.parametrize(
    "text,status",
    [
        ("31 сентября встреча", ParseStatus.INVALID_DATE),
        ("30 февраля созвон", ParseStatus.INVALID_DATE),
        ("september 31 meeting", ParseStatus.INVALID_DATE),
        ("в субботу в 10 или в воскресенье в 11 бег", ParseStatus.AMBIGUOUS),
        ("saturday at 10 or sunday at 11 run", ParseStatus.AMBIGUOUS),
    ],
)
def test_hard_invalid_and_ambiguous(p, text, status):
    assert p.parse(text, now=NOW) is None, text
    assert p.analyze(text, now=NOW).status == status, text


def test_hard_deadline_types(p):
    for text in ("до пятницы 18:00 сдать отчёт", "no later than friday 6pm submit the report",
                 "до нового года сдать проект", "by new year finish the project"):
        assert p.parse(text, now=NOW).task_type == TaskType.DEADLINE, text


# ── части периода: ближайшее будущее (политика «б») ───────────────────────
PART = [
    # без модификатора: окно, которое ещё не закончилось
    ("в начале месяца отчёт", "beginning of the month report",
     datetime(2026, 10, 1), datetime(2026, 10, 5, 23, 59)),
    ("в середине месяца отчёт", "middle of the month report",
     datetime(2026, 10, 13), datetime(2026, 10, 19, 23, 59)),
    ("в конце месяца отчёт", "end of the month report",
     datetime(2026, 9, 26), datetime(2026, 9, 30, 23, 59)),
    ("в середине недели созвон", "middle of the week call",
     datetime(2026, 9, 23), datetime(2026, 9, 25, 23, 59)),
    ("в конце недели созвон", "end of the week call",
     datetime(2026, 9, 26), datetime(2026, 9, 27, 23, 59)),
    ("в начале квартала план", "beginning of the quarter plan",
     datetime(2026, 10, 1), datetime(2026, 10, 10, 23, 59)),
    ("в начале года план", "beginning of the year plan",
     datetime(2027, 1, 1), datetime(2027, 1, 10, 23, 59)),
    # явные модификаторы: как сказано, даже если в прошлом
    ("в начале этого месяца отчёт", "beginning of this month report",
     datetime(2026, 9, 1), datetime(2026, 9, 5, 23, 59)),
    ("в начале прошлого месяца отчёт", "beginning of last month report",
     datetime(2026, 8, 1), datetime(2026, 8, 5, 23, 59)),
    ("в начале следующего месяца отчёт", "beginning of next month report",
     datetime(2026, 10, 1), datetime(2026, 10, 5, 23, 59)),
    # названный месяц — как сказано (в прошлом), не переносится на следующий
    ("в начале сентября отчёт", "early september report",
     datetime(2026, 9, 1), datetime(2026, 9, 5, 23, 59)),
]


@pytest.mark.parametrize("ru,en,start,end", PART, ids=[x[1] for x in PART])
def test_part_of_period_nearest_future(p, ru, en, start, end):
    got, errors = {}, []
    for text in (ru, en):
        r = p.parse(text, now=NOW)
        got[text] = r and (r.start_at, r.end_at, r.is_past)
        if r is None or r.start_at != start or r.end_at != end:
            errors.append(text)
        elif r.is_past != (end < NOW):
            errors.append(text + " (is_past)")
    assert not errors, got


def test_part_of_period_rolls_at_year_end(p):
    late = datetime(2026, 12, 31, 23, 59)
    for text in ("в начале месяца отчёт", "beginning of the month report"):
        r = p.parse(text, now=late)
        assert (r.start_at, r.end_at) == (datetime(2027, 1, 1), datetime(2027, 1, 5, 23, 59)), text


# ── дедлайн с датой И временем, COUNT/UNTIL у любых повторов ──────────────
@pytest.mark.parametrize(
    "text,deadline",
    [
        ("до нового года в 23:50 поздравить команду", datetime(2026, 12, 31, 23, 50)),
        ("до 20 октября в 18:00 отчёт", datetime(2026, 10, 20, 18, 0)),
        ("до конца месяца в 18:00 отчёт", datetime(2026, 9, 30, 18, 0)),
        ("до пятницы в 18:00 отчёт", datetime(2026, 9, 25, 18, 0)),
        ("до 20 октября отчёт", datetime(2026, 10, 20, 23, 59)),
    ],
)
def test_deadline_with_date_and_time(p, text, deadline):
    r = p.parse(text, now=NOW)
    assert r.task_type == TaskType.DEADLINE, text
    assert r.deadline == deadline, text


def test_deadline_pass_does_not_touch_ranges_and_recurrence(p):
    r = p.parse("с 10 до 18 работа", now=NOW)
    assert (r.start_at.hour, r.end_at.hour) == (10, 18)
    r = p.parse("каждую вторую среду месяца в 18:30 ретро до конца года", now=NOW)
    assert r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=2WE;UNTIL=20261231T235900"
    assert r.when == datetime(2026, 10, 14, 18, 30) and r.title == "ретро"
    r = p.parse("до первого рабочего дня следующего месяца обновить план", now=NOW)
    assert r.when == datetime(2026, 10, 1) and r.title == "обновить план"


@pytest.mark.parametrize(
    "text,rrule,when,title",
    [
        ("каждую вторую среду месяца в 18:30 ретро 6 раз", "FREQ=MONTHLY;BYDAY=2WE;COUNT=6",
         datetime(2026, 10, 14, 18, 30), "ретро"),
        ("remind me on the last business day of every month at 5pm to submit the invoice",
         "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", datetime(2026, 9, 30, 17, 0),
         "submit the invoice"),
        ("every month on the last business day at 5pm invoice",
         "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", datetime(2026, 9, 30, 17, 0), "invoice"),
    ],
)
def test_recurrence_modifiers_any_recognizer(p, text, rrule, when, title):
    r = p.parse(text, now=NOW)
    assert (r.recurrence.to_rrule(), r.when, r.title) == (rrule, when, title), text


def test_linking_words_not_in_title(p):
    assert p.parse("потом в 13 обед с Аней", now=NOW).title == "обед с Аней"
    assert p.parse("затем в 15 созвон", now=NOW).title == "созвон"


# ── повторы с интервалом: разговорные формы, RU и EN одинаково ────────────
INTERVAL = [
    ("раз в 2 недели по понедельникам планёрка", "every 2 weeks on monday standup",
     "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", datetime(2026, 9, 28)),
    ("раз в две недели в понедельник в 10 планёрка", "every two weeks on monday at 10 standup",
     "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", datetime(2026, 9, 28, 10, 0)),
    ("каждую вторую неделю по средам в 11 синк", "every second week on wednesday at 11 sync",
     "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE", datetime(2026, 9, 23, 11, 0)),
    ("по средам через неделю в 11 синк", "every other week on wednesday at 11 sync",
     "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE", datetime(2026, 9, 23, 11, 0)),
    ("через неделю по средам в 11 синк", "biweekly on wednesday at 11 sync",
     "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE", datetime(2026, 9, 23, 11, 0)),
    ("каждую третью неделю по пятницам отчёт", "every third week on friday report",
     "FREQ=WEEKLY;INTERVAL=3;BYDAY=FR", datetime(2026, 9, 25)),
]


@pytest.mark.parametrize("ru,en,rrule,when", INTERVAL, ids=[x[1] for x in INTERVAL])
def test_interval_recurrence_parity(p, ru, en, rrule, when):
    got = {}
    for text in (ru, en):
        r = p.parse(text, now=NOW)
        got[text] = r and (r.recurrence and r.recurrence.to_rrule(), r.when)
    assert got[ru] == got[en] == (rrule, when), got


@pytest.mark.parametrize(
    "text,rrule",
    [
        ("раз в 2 недели планёрка", "FREQ=WEEKLY;INTERVAL=2"),
        ("раз в три недели планёрка", "FREQ=WEEKLY;INTERVAL=3"),
        ("каждую вторую неделю планёрка", "FREQ=WEEKLY;INTERVAL=2"),
        ("каждую третью неделю отчёт", "FREQ=WEEKLY;INTERVAL=3"),
        ("каждый второй месяц отчёт", "FREQ=MONTHLY;INTERVAL=2"),
        ("раз в два месяца отчёт", "FREQ=MONTHLY;INTERVAL=2"),
        ("раз в квартал отчёт", "FREQ=MONTHLY;INTERVAL=3"),
        ("ежеквартально отчёт", "FREQ=MONTHLY;INTERVAL=3"),
        ("раз в полгода медосмотр", "FREQ=MONTHLY;INTERVAL=6"),
        ("каждые полгода медосмотр", "FREQ=MONTHLY;INTERVAL=6"),
        ("раз в год техосмотр", "FREQ=YEARLY"),
        ("каждый год техосмотр", "FREQ=YEARLY"),
        ("раз в день витамины", "FREQ=DAILY"),
        ("biweekly sync", "FREQ=WEEKLY;INTERVAL=2"),
        ("fortnightly sync", "FREQ=WEEKLY;INTERVAL=2"),
        ("once every two weeks sync", "FREQ=WEEKLY;INTERVAL=2"),
        ("every third week report", "FREQ=WEEKLY;INTERVAL=3"),
        ("every other month report", "FREQ=MONTHLY;INTERVAL=2"),
        ("every quarter report", "FREQ=MONTHLY;INTERVAL=3"),
        ("quarterly report", "FREQ=MONTHLY;INTERVAL=3"),
        ("every six months checkup", "FREQ=MONTHLY;INTERVAL=6"),
        ("every other day gym", "FREQ=DAILY;INTERVAL=2"),
    ],
)
def test_interval_forms(p, text, rrule):
    r = p.parse(text, now=NOW)
    assert r is not None and r.recurrence.to_rrule() == rrule, (text, r and r.recurrence)
    assert r.title and r.title.split()[0] not in ("once", "раз", "every"), (text, r.title)


def test_interval_does_not_break_one_offs(p):
    # «через неделю в понедельник» без повтора — разовая дата, а не «через раз»
    r = p.parse("через неделю в понедельник", now=NOW)
    assert r.recurrence is None and r.when == datetime(2026, 9, 28)
    # вторая пятница месяца — это не «каждая вторая неделя»
    r = p.parse("every second friday of the month retro", now=NOW)
    assert r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=2FR"
    # «два раза в неделю» — дни не названы, не выдумываем
    assert p.parse("два раза в неделю зал", now=NOW) is None
    assert p.parse("twice a week gym", now=NOW) is None


def test_summary_date_only_series(p):
    assert p.parse("каждый понедельник планёрка", now=NOW).summary() == \
        "task/period ⟳ FREQ=WEEKLY;BYDAY=MO  28.09.2026  весь день  «планёрка»"


# ── «за N (рабочих) дней / неделю до <даты>» — RU и EN одинаково ─────────
BEFORE = [
    ("за два рабочих дня до конца месяца напомнить про документы",
     "two business days before end of month remind about documents", datetime(2026, 9, 28, 9, 0)),
    ("за два дня до конца месяца оплатить аренду", "two days before end of month pay rent",
     datetime(2026, 9, 28, 9, 0)),
    ("за два дня до пятницы отправить отчёт", "two days before friday submit the report",
     datetime(2026, 9, 23, 9, 0)),
    ("за 2 рабочих дня до 20 октября подготовить слайды",
     "2 business days before october 20 prepare slides", datetime(2026, 10, 16, 9, 0)),
    ("за неделю до 20 октября купить билеты", "a week before october 20 buy tickets",
     datetime(2026, 10, 13, 9, 0)),
]


@pytest.mark.parametrize("ru,en,when", BEFORE, ids=[x[1] for x in BEFORE])
def test_days_before_parity(p, ru, en, when):
    got = {t: p.parse(t, now=NOW) for t in (ru, en)}
    sig = {t: r and (type(r).__name__, r.when, r.is_past) for t, r in got.items()}
    assert sig[ru] == sig[en] == ("TaskResult", when, False), sig
    for t, r in got.items():
        assert "дн" not in r.title and "day" not in r.title and "за" not in r.title.split(), (t, r.title)


def test_days_before_respects_working_calendar():
    from timesense import TimeConfig, WorkingCalendar

    # 28.09 объявлен праздником → «за 2 рабочих дня до конца сентября» уходит на 25.09
    cal = WorkingCalendar(holidays=["2026-09-28"])
    q = TimeSenseParser(TimeConfig(calendar=cal))
    for t in ("за два рабочих дня до конца месяца отчёт",
              "two business days before end of month report"):
        assert q.parse(t, now=NOW).when == datetime(2026, 9, 25, 9, 0), t


def test_word_dnya_is_not_daypart(p):
    # «дня» после числа — это «день», а не «днём»
    assert p.parse("через 2 дня в 10 врач", now=NOW).when == datetime(2026, 9, 24, 10, 0)
    assert p.parse("в 3 дня встреча", now=NOW).when == datetime(2026, 9, 22, 15, 0)
    r = p.parse("днём созвон", now=NOW)
    assert r.start_at.hour == 12  # «днём» — по-прежнему часть суток


# ── шаг 1: границы серии («с 1 октября», «с … по …», starting/from … to …) ─
SERIES = [
    ("начиная с 1 октября каждый понедельник планёрка", "starting october 1 every monday standup",
     "FREQ=WEEKLY;BYDAY=MO", datetime(2026, 10, 5)),
    ("каждый понедельник с 1 октября по 1 декабря планёрка",
     "every monday from october 1 to december 1 standup",
     "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261201T235900", datetime(2026, 10, 5)),
    ("по будням с 5 октября в 9 стендап", "every weekday starting october 5 at 9 standup",
     "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", datetime(2026, 10, 5, 9, 0)),
    ("каждый день с 1 по 10 октября в 8 зарядка", "every day from october 1 to october 10 at 8 workout",
     "FREQ=DAILY;UNTIL=20261010T235900", datetime(2026, 10, 1, 8, 0)),
    ("каждый день с 1 по 10 октября зарядка", "every day from october 1 to october 10 workout",
     "FREQ=DAILY;UNTIL=20261010T235900", datetime(2026, 10, 1)),
]


@pytest.mark.parametrize("ru,en,rrule,when", SERIES, ids=[x[1] for x in SERIES])
def test_series_bounds_parity(p, ru, en, rrule, when):
    got = {t: p.parse(t, now=NOW) for t in (ru, en)}
    sig = {t: r and (r.recurrence and r.recurrence.to_rrule(), r.when) for t, r in got.items()}
    assert sig[ru] == sig[en] == (rrule, when), sig
    for t, r in got.items():
        assert r.title.split()[0] not in ("начиная", "starting", "с", "from"), (t, r.title)


@pytest.mark.parametrize(
    "text,start,end",
    [
        ("с 1 октября курс", datetime(2026, 10, 1), datetime(2026, 10, 1, 23, 59)),
        ("с 1 октября по 1 декабря курс", datetime(2026, 10, 1), datetime(2026, 12, 1, 23, 59)),
    ],
)
def test_day_number_before_month_is_not_time(p, text, start, end):
    # раньше «с 1 октября» читалось как «с 1 часа» → завтра 01:00
    r = p.parse(text, now=NOW)
    assert (r.start_at, r.end_at) == (start, end), text


def test_time_ranges_still_work(p):
    assert (p.parse("с 1 до 3 созвон", now=NOW).start_at.hour,
            p.parse("с 1 до 3 созвон", now=NOW).end_at.hour) == (13, 15)
    r = p.parse("каждый будний день кроме пятницы в 9:15 до конца октября стендап", now=NOW)
    assert r.when == datetime(2026, 9, 23, 9, 15)


# ── шаг 2: исключённые даты серии (EXDATE) ────────────────────────────────
EXD = [
    ("каждый день в 8 кроме 31 декабря и 1 января зарядка",
     "every day at 8 except dec 31 and jan 1 workout",
     [datetime(2026, 12, 31, 8, 0), datetime(2027, 1, 1, 8, 0)]),
    ("по будням в 9 за исключением 30 декабря стендап",
     "every weekday at 9 excluding december 30 standup", [datetime(2026, 12, 30, 9, 0)]),
    ("каждый понедельник кроме 28 декабря планёрка", "every monday except december 28 standup",
     [datetime(2026, 12, 28)]),
]


@pytest.mark.parametrize("ru,en,exdates", EXD, ids=[x[1] for x in EXD])
def test_exdates_parity(p, ru, en, exdates):
    got = {t: p.parse(t, now=NOW).recurrence.exdates for t in (ru, en)}
    assert got[ru] == got[en] == exdates, got


@pytest.mark.parametrize("text", [x[0] for x in EXD] + [x[1] for x in EXD]
                         + ["каждый день кроме 31 декабря зарядка"])
def test_exdates_are_real_occurrences_and_in_ics(p, text):
    pytest.importorskip("dateutil")
    from dateutil.rrule import rrulestr

    r = p.parse(text, now=NOW)
    start = r.when
    occ = set(rrulestr("RRULE:" + r.recurrence.to_rrule(), dtstart=start)
              .between(start, datetime(2027, 6, 1), inc=True))
    assert r.recurrence.exdates and all(x in occ for x in r.recurrence.exdates), text
    ics = to_ics_text = r.to_ics()
    assert ics.count("EXDATE") == len(r.recurrence.exdates), to_ics_text
    assert r.to_dict()["recurrence"]["exdates"] == [x.isoformat() for x in r.recurrence.exdates]


def test_exdates_with_timezone_use_tzid(p):
    r = p.parse("каждый день в 8 кроме 31 декабря зарядка", now=NOW, tz="Europe/Amsterdam")
    ics = r.to_ics()
    assert "EXDATE;TZID=Europe/Amsterdam:20261231T080000" in ics


def test_exclusion_without_series_is_not_an_event(p):
    # «кроме 31 декабря» без серии — исключать не из чего; это НЕ событие 31 декабря
    assert p.parse("кроме 31 декабря", now=NOW) is None
    assert p.parse("except december 31", now=NOW) is None


def test_weekday_exclusions_unchanged(p):
    assert p.parse("каждый будний день кроме пятницы в 9 стендап", now=NOW).recurrence.to_rrule() \
        == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"
    r = p.parse("каждый день кроме выходных зарядка", now=NOW)
    assert r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    assert "exdates" not in r.to_dict()["recurrence"]  # формат без исключений не меняется


# ── шаг 3 ─────────────────────────────────────────────────────────────────
WEEK_OF_MONTH = [
    ("во вторую неделю октября отпуск", "second week of october vacation",
     datetime(2026, 10, 8), datetime(2026, 10, 14, 23, 59)),
    ("на второй неделе октября отпуск", "the second week of october vacation",
     datetime(2026, 10, 8), datetime(2026, 10, 14, 23, 59)),
    ("в последнюю неделю октября отпуск", "last week of october vacation",
     datetime(2026, 10, 25), datetime(2026, 10, 31, 23, 59)),
    ("в третью неделю февраля 2027 поездка", "the third week of february 2027 trip",
     datetime(2027, 2, 15), datetime(2027, 2, 21, 23, 59)),
]

WINDOWS = [
    ("после 10 но до 12 созвон", "after 10 but before 12 call",
     datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
    ("не раньше 10 и не позже 12 созвон", "no earlier than 10am and no later than 12pm call",
     datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
    ("с утра до полудня уборка", "from morning to noon cleanup",
     datetime(2026, 9, 23, 9, 0), datetime(2026, 9, 23, 12, 0)),
    ("с утра до обеда уборка", "from morning till lunch cleanup",
     datetime(2026, 9, 23, 9, 0), datetime(2026, 9, 23, 13, 0)),
    ("с обеда до вечера работа", "from lunch to evening work",
     datetime(2026, 9, 23, 13, 0), datetime(2026, 9, 23, 19, 0)),
]


@pytest.mark.parametrize("ru,en,start,end", WEEK_OF_MONTH + WINDOWS,
                         ids=[x[1] for x in WEEK_OF_MONTH + WINDOWS])
def test_step3_spans_parity(p, ru, en, start, end):
    got = {t: p.parse(t, now=NOW) for t in (ru, en)}
    sig = {t: r and (r.start_at, r.end_at) for t, r in got.items()}
    assert sig[ru] == sig[en] == (start, end), sig


@pytest.mark.parametrize(
    "ru,en,rrule,when",
    [
        ("каждые 30 минут с 9 до 18 разминка", "every 30 minutes from 9 to 6 stretch",
         "FREQ=MINUTELY;INTERVAL=30;BYHOUR=9,10,11,12,13,14,15,16,17", datetime(2026, 9, 22, 14, 0)),
        ("каждый час с 9 до 18 вода", "every hour from 9 to 6 water",
         "FREQ=HOURLY;BYHOUR=9,10,11,12,13,14,15,16,17", datetime(2026, 9, 22, 14, 0)),
        ("каждый час пить воду", "every hour drink water", "FREQ=HOURLY", datetime(2026, 9, 22, 14, 0)),
        ("ежечасно проверка", "hourly check", "FREQ=HOURLY", datetime(2026, 9, 22, 14, 0)),
        ("каждые выходные дача", "every weekend cottage", "FREQ=WEEKLY;BYDAY=SA,SU", datetime(2026, 9, 26)),
    ],
)
def test_step3_recurrence_parity(p, ru, en, rrule, when):
    got = {t: p.parse(t, now=NOW) for t in (ru, en)}
    sig = {t: r and (type(r).__name__, r.recurrence and r.recurrence.to_rrule(), r.when) for t, r in got.items()}
    assert sig[ru] == sig[en] and sig[ru][1:] == (rrule, when), sig


def test_hour_window_first_slot_after_window_is_tomorrow(p):
    late = datetime(2026, 9, 22, 19, 0)
    assert p.parse("каждые 30 минут с 9 до 18 разминка", now=late).when == datetime(2026, 9, 23, 9, 0)


@pytest.mark.parametrize("ru,en", [("не раньше 10 позвонить", "no earlier than 10am call")])
def test_not_earlier_is_open_start(p, ru, en):
    for t in (ru, en):
        r = p.parse(t, now=NOW)
        assert r.task_type == TaskType.OPEN_START and r.start_at == datetime(2026, 9, 23, 10, 0), t


@pytest.mark.parametrize("ru,en", [("с этого момента до пятницы фокус", "from now until friday focus")])
def test_from_now_until_is_deadline(p, ru, en):
    for t in (ru, en):
        r = p.parse(t, now=NOW)
        assert r.task_type == TaskType.DEADLINE and r.deadline == datetime(2026, 9, 25, 23, 59), t


@pytest.mark.parametrize("text", ["в пн, ср и пт в 10 созвон", "в понедельник, среду и пятницу в 10 созвон",
                                  "on monday, wednesday and friday at 10 call"])
def test_enumerated_days_are_multiple_events(p, text):
    assert p.parse(text, now=NOW) is None  # одно событие выбрать нельзя, не потеряв другие
    a = p.analyze(text, now=NOW)
    assert a.status == ParseStatus.MULTIPLE
    whens = [datetime(2026, 9, 28, 10, 0), datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 25, 10, 0)]
    assert [x.when for x in a.alternatives] == whens
    assert [x.when for x in p.parse_multi(text, now=NOW)] == whens


def test_enumeration_does_not_touch_recurrence_and_exclusions(p):
    assert p.parse("по пн, ср и пт в 10 созвон", now=NOW).recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,WE,FR"
    assert p.parse("every day except monday and tuesday workout", now=NOW).recurrence.to_rrule() \
        == "FREQ=WEEKLY;BYDAY=WE,TH,FR,SA,SU"


# ── шаг 4: паритет, формы, названия ───────────────────────────────────────
@pytest.mark.parametrize(
    "ru,en,deadline",
    [
        ("до вторника включительно отчёт", "through tuesday report", datetime(2026, 9, 29, 23, 59)),
        ("до вторника включительно отчёт", "until tuesday inclusive report", datetime(2026, 9, 29, 23, 59)),
        ("в ближайшие 2 часа ответить", "in the next 2 hours reply", datetime(2026, 9, 22, 16, 0)),
        ("в течение ближайших 2 часов ответить", "within the next 2 hours reply", datetime(2026, 9, 22, 16, 0)),
    ],
)
def test_step4_deadlines_parity(p, ru, en, deadline):
    for t in (ru, en):
        r = p.parse(t, now=NOW)
        assert r.task_type == TaskType.DEADLINE and r.deadline == deadline, t
        assert r.title in ("отчёт", "report", "ответить", "reply"), (t, r.title)


def test_through_does_not_break_ranges_and_until(p):
    r = p.parse("monday through friday trip", now=NOW)
    assert (r.start_at, r.end_at) == (datetime(2026, 9, 28), datetime(2026, 10, 2, 23, 59))
    assert p.parse("every friday until end of march sync", now=NOW).recurrence.to_rrule() \
        == "FREQ=WEEKLY;BYDAY=FR;UNTIL=20270331T235900"


@pytest.mark.parametrize(
    "ru,en,rrule,when",
    [
        ("по чётным числам полив", "on even days water plants",
         "FREQ=MONTHLY;BYMONTHDAY=" + ",".join(str(x) for x in range(2, 31, 2)), datetime(2026, 9, 22)),
        ("по нечётным числам в 9 полив", "on odd days at 9 water plants",
         "FREQ=MONTHLY;BYMONTHDAY=" + ",".join(str(x) for x in range(1, 32, 2)), datetime(2026, 9, 23, 9, 0)),
    ],
)
def test_even_odd_days_parity(p, ru, en, rrule, when):
    for t in (ru, en):
        r = p.parse(t, now=NOW)
        assert (r.recurrence.to_rrule(), r.when) == (rrule, when), t


@pytest.mark.parametrize(
    "text,title",
    [
        ("в районе 5 созвон", "созвон"),
        ("начиная с завтра бегать", "бегать"),
        ("starting tomorrow run", "run"),
        ("ближе к концу недели отчёт", "отчёт"),
        ("towards the end of the week report", "report"),
        ("towards evening call mom", "call mom"),
        ("до 20 октября включительно отчёт", "отчёт"),
    ],
)
def test_step4_titles(p, text, title):
    assert p.parse(text, now=NOW).title == title, text


def test_around_five_parity(p):
    assert p.parse("в районе 5 созвон", now=NOW).when == p.parse("around 5 call", now=NOW).when \
        == datetime(2026, 9, 22, 17, 0)


@pytest.mark.parametrize("text", ["ближе к вечеру позвонить", "towards evening call mom",
                                  "closer to the evening call"])
def test_towards_evening_parity(p, text):
    r = p.parse(text, now=NOW)
    assert (r.start_at, r.end_at) == (datetime(2026, 9, 22, 17, 0), datetime(2026, 9, 22, 21, 0)), text


def test_towards_evening_with_hour_is_pm(p):
    assert p.parse("towards evening at 7 call", now=NOW).when.hour == 19

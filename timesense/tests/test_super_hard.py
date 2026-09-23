# -*- coding: utf-8 -*-
"""32 сверхсложные фразы (RU и EN): повтор + исключения + границы серии + пояс,
опечатки + длительность + место, праздники со временем, несколько событий, частые повторы
с окном часов и днями недели, переход через полночь, «за неделю до …». Ожидаемые ответы
посчитаны независимо от парсера по календарю. NOW = вт 22.09.2026 14:00.
RRULE сравнивается как множество частей (порядок частей RFC 5545 не фиксирует)."""

from datetime import datetime, timezone

import pytest

from timesense import ParseStatus, TimeSenseParser

N = datetime(2026, 9, 22, 14, 0)
p = TimeSenseParser()
U = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731
CASES = []


def chk(no, text, got_fn, expected, tz=None, mode="parse"):
    CASES.append((no, text, got_fn, expected, tz, mode))


def rr(r):
    if not r or not r.recurrence:
        return None
    return frozenset(r.recurrence.to_rrule().split(";"))


def W(r):
    return r.when


def T(r):
    return r.title


# 1–2: повтор + исключение дня + пояс + границы серии
chk(1,"каждый будний день кроме пятницы в 9:15 мск с 1 октября до конца года стендап",
    lambda r:(rr(r), W(r).astimezone(timezone.utc), T(r)),
    ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH;UNTIL=20261231T205900Z", U(2026,10,1,6,15), "стендап"), tz="Europe/Amsterdam")
chk(2,"every weekday except friday at 9:15 msk starting october 1 until end of year standup",
    lambda r:(rr(r), W(r).astimezone(timezone.utc), T(r)),
    ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH;UNTIL=20261231T205900Z", U(2026,10,1,6,15), "standup"), tz="Europe/Amsterdam")
# 3: вторая пятница + COUNT + место
chk(3,"каждую вторую пятницу месяца в 18:30 ретро в переговорке 6 раз",
    lambda r:(rr(r), W(r), T(r), r.location), ("FREQ=MONTHLY;BYDAY=2FR;COUNT=6", datetime(2026,10,9,18,30), "ретро", "в переговорке"))
# 4–5: последний рабочий день каждого месяца + время
chk(4,"в последний рабочий день каждого месяца в 17 закрыть отчёт",
    lambda r:(rr(r), W(r), T(r)), ("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", datetime(2026,9,30,17,0), "закрыть отчёт"))
chk(5,"last business day of every month at 5pm close the report",
    lambda r:(rr(r), W(r), T(r)), ("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", datetime(2026,9,30,17,0), "close the report"))
# 6–7: раз в две недели + исключение даты + UNTIL
chk(6,"по средам через неделю в 11 синк с дизайнером кроме 30 декабря до конца года",
    lambda r:(rr(r), W(r), [x for x in r.recurrence.exdates], T(r)),
    ("FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;UNTIL=20261231T235900", datetime(2026,9,23,11,0), [datetime(2026,12,30,11,0)], "синк с дизайнером"))
chk(7,"every other wednesday at 11 sync with the designer except december 30 until end of year",
    lambda r:(rr(r), W(r), [x for x in r.recurrence.exdates], T(r)),
    ("FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;UNTIL=20261231T235900", datetime(2026,9,23,11,0), [datetime(2026,12,30,11,0)], "sync with the designer"))
# 8: за N рабочих дней до конца месяца + время
chk(8,"за 2 рабочих дня до конца месяца в 10 напомнить про документы",
    lambda r:(W(r), T(r)), (datetime(2026,9,28,10,0), "напомнить про документы"))
# 9–10: опечатка + разговорное время + место + длительность
chk(9,"завтро в 10 30 в офисе совещание на полтора часа",
    lambda r:(r.start_at, r.end_at, r.location, T(r)), (datetime(2026,9,23,10,30), datetime(2026,9,23,12,0), "в офисе", "совещание"))
chk(10,"tmrw at 10:30 meeting at the office for an hour and a half",
    lambda r:(r.start_at, r.end_at, r.location, T(r)), (datetime(2026,9,23,10,30), datetime(2026,9,23,12,0), "at the office", "meeting"))
# 11–12: праздник + время
chk(11,"до нового года в 23:50 поздравить команду",
    lambda r:(r.deadline, T(r)), (datetime(2026,12,31,23,50), "поздравить команду"))
chk(12,"christmas party at 7pm at the office",
    lambda r:(W(r), r.location, T(r)), (datetime(2026,12,25,19,0), "at the office", "party"))
# 13–14: несколько событий
chk(13,"в пн, ср и пт в 10 созвон с командой",
    lambda a:(a.status, [(x.when, x.title) for x in a.alternatives]),
    (ParseStatus.MULTIPLE, [(datetime(2026,9,28,10),"созвон с командой"),(datetime(2026,9,23,10),"созвон с командой"),(datetime(2026,9,25,10),"созвон с командой")]), mode='analyze')
chk(14,"tomorrow 10am standup, 1pm lunch with Ann and 6pm gym",
    lambda rs:[(x.when, x.title) for x in rs],
    [(datetime(2026,9,23,10),"standup"),(datetime(2026,9,23,13),"lunch with Ann"),(datetime(2026,9,23,18),"gym")], mode='multi')
chk(15,"сегодня вечером в 8, завтра утром в 9 и в пятницу в 18 тренировка",
    lambda rs:[x.when for x in rs], [datetime(2026,9,22,20), datetime(2026,9,23,9), datetime(2026,9,25,18)], mode='multi')
# 16–17: частый повтор + окно часов + дни недели
chk(16,"каждые 30 минут с 9 до 18 по будням пить воду",
    lambda r:(rr(r), W(r)), ("FREQ=MINUTELY;INTERVAL=30;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,10,11,12,13,14,15,16,17", datetime(2026,9,22,14,0)))
chk(17,"every 30 minutes from 9 to 6 on weekdays drink water",
    lambda r:(rr(r), W(r)), ("FREQ=MINUTELY;INTERVAL=30;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9,10,11,12,13,14,15,16,17", datetime(2026,9,22,14,0)))
# 18–19: недели + пояс
chk(18,"через 3 недели в понедельник в 10 мск созвон",
    lambda r: W(r).astimezone(timezone.utc), U(2026,10,12,7,0), tz="Europe/Amsterdam")
chk(19,"in 3 weeks on monday at 10am EST call",
    lambda r: W(r).astimezone(timezone.utc), U(2026,10,12,14,0), tz="Europe/Moscow")
# 20–21: словесное время + «следующая пятница»
chk(20,"в половине седьмого вечера в следующую пятницу ужин",
    lambda r:(W(r), T(r)), (datetime(2026,10,2,18,30), "ужин"))
chk(21,"half past six pm next friday dinner",
    lambda r:(W(r), T(r)), (datetime(2026,10,2,18,30), "dinner"))
# 22–23: через полночь
chk(22,"в пятницу с 23:30 до 01:15 релиз",
    lambda r:(r.start_at, r.end_at, T(r)), (datetime(2026,9,25,23,30), datetime(2026,9,26,1,15), "релиз"))
chk(23,"friday from 11:30pm to 1:15am release",
    lambda r:(r.start_at, r.end_at, T(r)), (datetime(2026,9,25,23,30), datetime(2026,9,26,1,15), "release"))
# 24–25: ежегодно в последнюю пятницу октября
chk(24,"каждый год в последнюю пятницу октября корпоратив",
    lambda r:(rr(r), W(r)), ("FREQ=YEARLY;BYMONTH=10;BYDAY=-1FR", datetime(2026,10,30)))
chk(25,"every year on the last friday of october company party",
    lambda r:(rr(r), W(r)), ("FREQ=YEARLY;BYMONTH=10;BYDAY=-1FR", datetime(2026,10,30)))
# 26–27: дедлайн с поясом
chk(26,"до пятницы 18:00 по москве сдать отчёт",
    lambda r:(r.deadline.astimezone(timezone.utc), T(r)), (U(2026,9,25,15,0), "сдать отчёт"), tz="Europe/Amsterdam")
chk(27,"by friday 6pm london time submit the report",
    lambda r:(r.deadline.astimezone(timezone.utc), T(r)), (U(2026,9,25,17,0), "submit the report"), tz="Europe/Moscow")
# 28–29: за неделю до даты
chk(28,"за неделю до 5 марта купить подарок маме",
    lambda r:(W(r), T(r)), (datetime(2027,2,26,9,0), "купить подарок маме"))
chk(29,"a week before march 5 buy a gift for mom",
    lambda r:(W(r), T(r)), (datetime(2027,2,26,9,0), "buy a gift for mom"))
# 30–31: опечатка + дедлайн / открытое начало
chk(30,"завтро до обеда позвонить в банк",
    lambda r:(r.task_type.value, r.deadline, T(r)), ("deadline", datetime(2026,9,23,13,0), "позвонить в банк"))
chk(31,"firday after lunch call the bank",
    lambda r:(r.task_type.value, r.start_at, T(r)), ("open_start", datetime(2026,9,25,13,0), "call the bank"))
# 32: исключение + границы серии + окно
chk(32,"каждый день с 1 по 10 октября в 8 кроме 5 октября зарядка",
    lambda r:(rr(r), W(r), r.recurrence.exdates, T(r)),
    ("FREQ=DAILY;UNTIL=20261010T235900", datetime(2026,10,1,8,0), [datetime(2026,10,5,8,0)], "зарядка"))


def _norm(x):
    if isinstance(x, str) and x.startswith("FREQ="):
        return frozenset(x.split(";"))
    if isinstance(x, tuple):
        return tuple(_norm(v) for v in x)
    return x


@pytest.mark.parametrize("no,text,got_fn,expected,tz,mode", CASES, ids=[f"{c[0]:02d}" for c in CASES])
def test_super_hard(no, text, got_fn, expected, tz, mode):
    if mode == "multi":
        r = p.parse_multi(text, now=N, tz=tz)
    elif mode == "analyze":
        r = p.analyze(text, now=N, tz=tz)
    else:
        r = p.parse(text, now=N, tz=tz)
    assert _norm(got_fn(r)) == _norm(expected), text


@pytest.mark.parametrize(
    "text,rrule,when",
    [
        ("каждые 30 минут по выходным пить воду", "FREQ=MINUTELY;INTERVAL=30;BYDAY=SA,SU", datetime(2026, 9, 26)),
        ("каждые 30 минут по будням пить воду", "FREQ=MINUTELY;INTERVAL=30;BYDAY=MO,TU,WE,TH,FR", N),
        ("каждый час по субботам проверка", "FREQ=HOURLY;BYDAY=SA", datetime(2026, 9, 26)),
        ("каждую пятницу по 31 октября отчёт", "FREQ=WEEKLY;BYDAY=FR;UNTIL=20261031T235900", datetime(2026, 9, 25)),
    ],
)
def test_frequent_with_weekdays_and_until(text, rrule, when):
    r = p.parse(text, now=N)
    assert (r.recurrence.to_rrule(), r.when) == (rrule, when), text


# ── исторические даты и диапазон, разорванный датой ───────────────────────
@pytest.mark.parametrize(
    "text,start,end",
    [
        ("Полёт Гагарина длился с 9 утра 12 апреля 1961 года до 11 утра",
         datetime(1961, 4, 12, 9, 0), datetime(1961, 4, 12, 11, 0)),
        ("from 9am on april 12 1961 to 11am flight", datetime(1961, 4, 12, 9, 0), datetime(1961, 4, 12, 11, 0)),
        ("с 22 31 декабря до 2 ночи вечеринка", datetime(2026, 12, 31, 22, 0), datetime(2027, 1, 1, 2, 0)),
        ("from 10pm on december 31 to 2am party", datetime(2026, 12, 31, 22, 0), datetime(2027, 1, 1, 2, 0)),
        ("с 10 завтра до 12 созвон", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
        ("from 10 tomorrow to 12 call", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
        ("с 10 в пятницу до 12 созвон", datetime(2026, 9, 25, 10, 0), datetime(2026, 9, 25, 12, 0)),
        ("from 10am on friday to noon call", datetime(2026, 9, 25, 10, 0), datetime(2026, 9, 25, 12, 0)),
        ("с 10 до полудня созвон", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
        ("from 10am to noon call", datetime(2026, 9, 23, 10, 0), datetime(2026, 9, 23, 12, 0)),
        ("с полудня до 15 обед", datetime(2026, 9, 23, 12, 0), datetime(2026, 9, 23, 15, 0)),
        ("from noon to 3pm lunch", datetime(2026, 9, 23, 12, 0), datetime(2026, 9, 23, 15, 0)),
        ("с 22 до полуночи вечеринка", datetime(2026, 9, 22, 22, 0), datetime(2026, 9, 23, 0, 0)),
        ("from 10pm to midnight party", datetime(2026, 9, 22, 22, 0), datetime(2026, 9, 23, 0, 0)),
    ],
)
def test_split_and_bounded_ranges(text, start, end):
    r = p.parse(text, now=N)
    assert type(r).__name__ == "CalendarResult", (text, r)
    assert (r.start_at, r.end_at) == (start, end), text
    assert r.is_past == (end < N), text


@pytest.mark.parametrize(
    "text,day",
    [
        ("12 апреля 1961 года полёт", datetime(1961, 4, 12)),
        ("12.04.1961 полёт", datetime(1961, 4, 12)),
        ("1961-04-12 полёт", datetime(1961, 4, 12)),
        ("12 апреля 1999 года полёт", datetime(1999, 4, 12)),
        ("april 12 1961 flight", datetime(1961, 4, 12)),
    ],
)
def test_historic_years_are_kept(text, day):
    # раньше годы до 2020 (RU) молча отбрасывались и дата уезжала в будущее
    r = p.parse(text, now=N)
    assert r.when == day and r.is_past is True, text


def test_amount_after_month_is_not_a_year():
    r = p.parse("10 октября 2000 рублей перевести", now=N)
    assert r.when == datetime(2026, 10, 10)


def test_plain_deadlines_with_noon_midnight_unchanged():
    assert p.parse("до полудня отчёт", now=N).deadline == datetime(2026, 9, 23, 12, 0)
    assert p.parse("сегодня до полуночи отчёт", now=N).deadline == datetime(2026, 9, 23, 0, 0)

# -*- coding: utf-8 -*-
"""Прошлое и история (RU и EN): «вчера», «назад», «в прошлом …», прошлые сезоны,
исторические даты и диапазоны через годы. Ожидания посчитаны независимо от парсера.
NOW = вт 22.09.2026 14:00: прошлый понедельник — 21.09, прошлая пятница — 18.09,
среда прошлой недели — 16.09."""

from datetime import datetime

import pytest

from timesense import TimeSenseParser

N = datetime(2026, 9, 22, 14, 0)
D = datetime
p = TimeSenseParser()

cases=[
 ("вчера в 18 был созвон","yesterday at 6pm had a call",(D(2026,9,21,18),None,True)),
 ("позавчера вечером кино","the day before yesterday in the evening movie",(D(2026,9,20,18),D(2026,9,20,22),True)),
 ("в прошлый понедельник в 10 собеседование","last monday at 10 interview",(D(2026,9,21,10),None,True)),
 ("на прошлой неделе в среду в 11 созвон","last week on wednesday at 11 call",(D(2026,9,16,11),None,True)),
 ("два дня назад в 15 встреча","two days ago at 3pm meeting",(D(2026,9,20,15),None,True)),
 ("в прошлую пятницу с 10 до 12 созвон","last friday from 10 to 12 call",(D(2026,9,18,10),D(2026,9,18,12),True)),
 ("в прошлом месяце отпуск","last month vacation",(D(2026,8,1),D(2026,8,31,23,59),True)),
 ("в прошлом году переезд","last year moved",(D(2025,1,1),D(2025,12,31,23,59),True)),
 ("в начале прошлого месяца отчёт","at the beginning of last month report",(D(2026,8,1),D(2026,8,5,23,59),True)),
 ("9 мая 1945 года победа","may 9 1945 victory",(D(1945,5,9),D(1945,5,9,23,59),True)),
 ("с 22 июня 1941 по 9 мая 1945 война","from june 22 1941 to may 9 1945 war",(D(1941,6,22),D(1945,5,9,23,59),True)),
 ("в 1945 году победа","in 1945 victory",(D(1945,1,1),D(1945,12,31,23,59),True)),
 ("в марте 2020 локдаун","in march 2020 lockdown",(D(2020,3,1),D(2020,3,31,23,59),True)),
 ("полёт Гагарина 12 апреля 1961 года в 9:07","gagarin flight on april 12 1961 at 9:07",(D(1961,4,12,9,7),None,True)),
 ("прошлой зимой каток","last winter skating",(D(2025,12,1),D(2026,2,28,23,59),True)),
]
ago=[("неделю назад отправил отчёт","a week ago sent the report",D(2026,9,15)),
     ("месяц назад купил","a month ago bought",D(2026,8,22)),
     ("3 года назад переехал","3 years ago moved",D(2023,9,22))]


def _sig(r):
    end = getattr(r, "end_at", None) if type(r).__name__ != "ReminderResult" else None
    return (r.when, end, r.is_past)


@pytest.mark.parametrize("ru,en,exp", cases, ids=[c[1] for c in cases])
def test_past_parity(ru, en, exp):
    got = {t: p.parse(t, now=N) for t in (ru, en)}
    sig = {t: r and _sig(r) for t, r in got.items()}
    assert sig[ru] == sig[en] == exp, sig


@pytest.mark.parametrize("ru,en,day", ago, ids=[a[1] for a in ago])
def test_ago_parity(ru, en, day):
    for t in (ru, en):
        r = p.parse(t, now=N)
        assert (r.when.date(), r.is_past) == (day.date(), True), t


def test_year_is_not_compact_time():
    # «в 1945 году» раньше давало сегодня 19:45; «в 1930» (без «году») — по-прежнему время
    assert p.parse("в 1945 году победа", now=N).start_at == D(1945, 1, 1)
    assert p.parse("в 1930 встреча", now=N).when == D(2026, 9, 22, 19, 30)
    assert p.parse("в 2027 году переезд", now=N).start_at == D(2027, 1, 1)


@pytest.mark.parametrize(
    "now,text,start",
    [
        (D(2027, 1, 15, 12), "прошлой зимой каток", D(2025, 12, 1)),
        (D(2027, 1, 15, 12), "этой зимой каток", D(2026, 12, 1)),
        (D(2027, 1, 15, 12), "следующей зимой каток", D(2027, 12, 1)),
        (D(2027, 1, 15, 12), "last winter skating", D(2025, 12, 1)),
        (N, "прошлым летом отпуск", D(2026, 6, 1)),
        (N, "last summer vacation", D(2026, 6, 1)),
    ],
)
def test_season_modifiers(now, text, start):
    assert p.parse(text, now=now).start_at == start, text


def test_same_year_ranges_unchanged():
    r = p.parse("с 25 сентября по 3 октября отпуск", now=N)
    assert (r.start_at, r.end_at) == (D(2026, 9, 25), D(2026, 10, 3, 23, 59))
    r = p.parse("from september 25 to october 3 vacation", now=N)
    assert (r.start_at, r.end_at) == (D(2026, 9, 25), D(2026, 10, 3, 23, 59))

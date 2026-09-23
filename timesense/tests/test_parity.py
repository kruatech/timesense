# -*- coding: utf-8 -*-
"""Паритет RU/EN: одна и та же фраза на двух языках даёт одинаковый результат
(тип, задача, момент, конец/дедлайн, RRULE, is_past). Любое расхождение —
ошибка одной из локалей. NOW = вт 22.09.2026 14:00.

Сознательные различия (сюда не входят): «рождество» (7 января) ≠ «christmas»
(25 декабря), «пасха» — православная, «easter» — западная."""

from datetime import datetime

import pytest

from timesense import TimeSenseParser

NOW = datetime(2026, 9, 22, 14, 0)

PAIRS = [
 # время
 ("в 10 созвон","at 10 call"),("в 15:30 созвон","at 15:30 call"),("в 7 утра созвон","at 7am call"),
 ("в 7 вечера созвон","at 7pm call"),("в полдень созвон","at noon call"),("в полночь созвон","at midnight call"),
 ("в половине пятого созвон","at half past four call"),("без четверти пять созвон","at quarter to five call"),
 ("в десять тридцать созвон","at ten thirty call"),
 # относительное
 ("через 15 минут созвон","in 15 minutes call"),("через 2 часа созвон","in 2 hours call"),
 ("через полчаса созвон","in half an hour call"),("через полтора часа созвон","in an hour and a half call"),
 ("через 3 дня созвон","in 3 days call"),("через неделю созвон","in a week call"),("через месяц созвон","in a month call"),
 ("через 30 секунд созвон","in 30 seconds call"),("через пару часов созвон","in a couple of hours call"),
 # дни
 ("сегодня в 18 созвон","today at 6pm call"),("завтра в 10 созвон","tomorrow at 10 call"),
 ("послезавтра в 10 созвон","day after tomorrow at 10 call"),("вчера в 10 созвон","yesterday at 10 call"),
 ("позавчера в 10 созвон","day before yesterday at 10 call"),
 ("в пятницу в 10 созвон","on friday at 10 call"),("в следующую пятницу в 10 созвон","next friday at 10 call"),
 ("в эту пятницу в 10 созвон","this friday at 10 call"),("в прошлую пятницу в 10 созвон","last friday at 10 call"),
 ("на следующей неделе в среду в 11 созвон","next week on wednesday at 11 call"),
 ("25 сентября в 10 созвон","september 25 at 10 call"),("25 декабря созвон","december 25 call"),
 ("1 января 2027 созвон","january 1 2027 call"),("через неделю в пятницу созвон","in a week on friday call"),
 # части суток
 ("сегодня вечером созвон","this evening call"),("завтра утром созвон","tomorrow morning call"),
 ("завтра утром в 8:30 созвон","tomorrow morning at 8:30 call"),("сегодня вечером в 8 созвон","tonight at 8 call"),
 ("вчера вечером созвон","yesterday evening call"),
 # диапазоны
 ("с 10 до 11 созвон","from 10 to 11 call"),("с 9 до 5 работа","from 9 to 5 work"),
 ("с 22 до 2 дежурство","from 10pm to 2am on call"),("завтра с 10 до 11:30 созвон","tomorrow from 10 to 11:30 call"),
 ("с понедельника по среду командировка","from monday to wednesday trip"),
 ("с 1 по 10 октября отпуск","from october 1 to october 10 vacation"),
 # длительность
 ("завтра в 10 созвон на 2 часа","tomorrow at 10 call for 2 hours"),
 ("завтра в 10 созвон на полтора часа","tomorrow at 10 call for an hour and a half"),
 # повторы
 ("каждый день в 9 стендап","every day at 9 standup"),("каждый понедельник в 10 созвон","every monday at 10 call"),
 ("каждый понедельник и среду в 10 созвон","every monday and wednesday at 10 call"),
 ("по будням в 9 стендап","every weekday at 9 standup"),("по выходным в 10 йога","on weekends at 10 yoga"),
 ("каждые 2 недели в понедельник созвон","every 2 weeks on monday call"),("каждые 15 минут вода","every 15 minutes water"),
 ("каждый месяц 15 числа зарплата","every month on the 15th salary"),("каждое утро в 7 зарядка","every morning at 7 workout"),
 ("каждый будний день кроме пятницы в 9 стендап","every weekday except friday at 9 standup"),
 ("каждый день до конца месяца в 9 стендап","every day until end of month at 9 standup"),
 ("каждую пятницу 5 раз йога","every friday 5 times yoga"),("каждый второй вторник месяца клуб","every second tuesday of the month club"),
 ("в последнюю пятницу месяца ретро","last friday of the month retro"),
 ("ежегодно 5 марта день рождения","every year on march 5 birthday"),("каждый новый год звонок","every new year call"),
 # дедлайны
 ("до пятницы отчёт","by friday report"),("до 18 отчёт","by 6pm report"),("до конца дня отчёт","by end of day report"),
 ("до конца недели отчёт","by end of week report"),("до конца месяца отчёт","by end of month report"),
 ("до 20 октября отчёт","by october 20 report"),("в течение 2 часов ответ","within 2 hours reply"),
 ("завтра до 18 отчёт","by 6pm tomorrow report"),("в пятницу до 18 отчёт","by 6pm on friday report"),
 ("не позднее пятницы отчёт","no later than friday report"),("до нового года отчёт","by new year report"),
 # открытое начало
 ("после 17 созвон","after 5pm call"),("после обеда созвон","after lunch call"),
 # периоды
 ("в октябре отпуск","in october vacation"),("в следующем месяце отпуск","next month vacation"),
 ("на следующей неделе отпуск","next week vacation"),("в эти выходные дача","this weekend cottage"),
 ("на следующих выходных дача","next weekend cottage"),("в начале следующего месяца отчёт","beginning of next month report"),
 ("в конце месяца отчёт","end of the month report"),("в середине октября поездка","mid october trip"),
 ("в 2027 году переезд","in 2027 move"),("зимой поездка","in winter trip"),
 # рабочие дни, праздники
 ("через 2 рабочих дня ответ","in 2 business days reply"),
 # «рождество» (RU, 7 января) и «christmas» (EN, 25 декабря) — разные праздники, пары нет
 ("в четыре часа созвон","at 4 o'clock call"),
 # пояса
 ("завтра в 10 мск созвон","tomorrow at 10 msk call"),
]



@pytest.fixture(scope="module")
def p():
    return TimeSenseParser()


def _sig(r):
    if r is None:
        return None
    d = r.to_dict()
    rec = d.get("recurrence") or {}
    return (d["type"], d.get("task_type"), r.when, d.get("end") or d.get("deadline"),
            rec.get("rrule"), r.is_past)


@pytest.mark.parametrize("ru,en", PAIRS, ids=[en for _, en in PAIRS])
def test_ru_en_parity(p, ru, en):
    kw = {"tz": "Europe/Moscow"} if "мск" in ru else {}
    a, b = _sig(p.parse(ru, now=NOW, **kw)), _sig(p.parse(en, now=NOW, **kw))
    assert a is not None, ru
    assert a == b, (ru, en, a, b)

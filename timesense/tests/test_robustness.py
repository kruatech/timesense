# -*- coding: utf-8 -*-
"""Устойчивость и производительность: парсер не падает на мусоре и не
деградирует по скорости. Пороги скорости щедрые (в 10–20 раз выше замеров на
слабом VPS), чтобы тест ловил только реальную деградацию, а не шум CI.
Отключить perf-проверку: TIMESENSE_SKIP_PERF=1."""

import os
import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from timesense import TimeConfig, TimeSenseParser

NOW = datetime(2026, 9, 22, 14, 0)
ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюяabcdefghijklmnopqrstuvwxyz0123456789 .:,-/!?ё\n\t😀+"

PHRASES = [
    "завтра в 10 встреча", "через 2 часа позвонить", "каждый понедельник в 9 планёрка",
    "с 10 до 11:30 совещание", "до пятницы сдать отчёт", "на следующей неделе в среду в 11",
    "в 10 мск созвон", "в октябре отпуск", "напомни через 15 минут выключить плиту",
    "tomorrow at 10 meeting", "in 2 hours call", "every monday at 9 standup",
    "from 10 to 11:30 sync", "by friday submit report", "next week on wednesday at 11",
    "at 10 EST call", "in october vacation", "remind me in 15 minutes to turn off the stove",
]


@pytest.fixture(scope="module")
def p():
    return TimeSenseParser()


def test_fuzz_never_raises(p):
    rnd = random.Random(20260922)
    for _ in range(3000):
        s = "".join(rnd.choice(ALPHABET) for _ in range(rnd.randint(0, 80)))
        p.parse(s, now=NOW)
        p.parse_multi(s, now=NOW)
        p.parse(s, now=NOW, tz=timezone(timedelta(hours=3)))


def test_mutated_phrases_never_raise(p):
    rnd = random.Random(7)
    for base in PHRASES:
        for _ in range(60):
            chars = list(base)
            for _ in range(rnd.randint(1, 4)):
                op = rnd.random()
                pos = rnd.randrange(len(chars) + 1)
                if op < 0.4 and chars:
                    chars.pop(min(pos, len(chars) - 1))
                elif op < 0.8:
                    chars.insert(pos, rnd.choice(ALPHABET))
                elif chars:
                    chars[min(pos, len(chars) - 1)] = rnd.choice(ALPHABET)
            s = "".join(chars)
            p.parse(s, now=NOW)
            p.parse(s, now=NOW, language="en")
            p.parse(s, now=NOW, language="ru")


@pytest.mark.parametrize("value", [None, "", "   ", "\n\t", "😀" * 50, "9" * 500])
def test_edge_inputs(p, value):
    p.parse(value, now=NOW)
    assert p.parse_multi(value, now=NOW) in ([],) or isinstance(p.parse_multi(value, now=NOW), list)


def test_long_input_bounded(p):
    t = time.perf_counter()
    assert p.parse("в 10 " * 10000, now=NOW) is None  # отсечено лимитом
    assert time.perf_counter() - t < 0.05


def test_deterministic(p):
    for s in PHRASES:
        a, b = p.parse(s, now=NOW), p.parse(s, now=NOW)
        assert (a and a.to_dict()) == (b and b.to_dict())


@pytest.mark.skipif(os.environ.get("TIMESENSE_SKIP_PERF") == "1", reason="perf отключён")
def test_latency_budget():
    fast = TimeSenseParser(TimeConfig(use_morph=False))
    for s in PHRASES:
        fast.parse(s, now=NOW)  # прогрев
    n = 0
    t = time.perf_counter()
    for _ in range(20):
        for s in PHRASES:
            fast.parse(s, now=NOW)
            n += 1
    per_phrase_ms = (time.perf_counter() - t) / n * 1000
    # замер: ~0.1–0.25 мс на фразу; порог 5 мс ловит только грубую деградацию
    assert per_phrase_ms < 5.0, per_phrase_ms


def test_thread_safety():
    """Один парсер из многих потоков (типично для бота) даёт те же ответы."""
    from concurrent.futures import ThreadPoolExecutor

    shared = TimeSenseParser()
    expected = {s: (shared.parse(s, now=NOW) and shared.parse(s, now=NOW).to_dict()) for s in PHRASES}

    def work(i):
        s = PHRASES[i % len(PHRASES)]
        r = shared.parse(s, now=NOW)
        return s, (r and r.to_dict())

    with ThreadPoolExecutor(max_workers=8) as ex:
        for s, d in ex.map(work, range(800)):
            assert d == expected[s], s

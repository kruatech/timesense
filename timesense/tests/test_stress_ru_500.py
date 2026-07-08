#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimeSense semantic stress test, RU.

500 валидных рабочих фраз. Это не набор "один шаблон + разные title":
кейсы перемешаны по типам и проверяют не только отсутствие падений, но и
простую семантику past/future.

Standalone:
    python3 tests/test_stress_ru_500.py
    python3 tests/test_stress_ru_500.py --verbose
    python3 tests/test_stress_ru_500.py --audit
    python3 tests/test_stress_ru_500.py --json > test_stress_ru_500.json.json

Pytest:
    python3 -m pytest -q tests/test_stress_ru_500.py -vv
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


NOW = datetime(2026, 7, 6, 15, 41)
LANGUAGE = "ru"


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    tags: tuple[str, ...]
    temporal: str = "any"  # past | future | any


def normalize_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    data = {k: v for k, v in data.items() if k != "source"}
    return {"_class": type(result).__name__, **data}


def _primary_dt(data: dict[str, Any] | None) -> datetime | None:
    if not data:
        return None
    for key in ("datetime", "start", "deadline"):
        value = data.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
    return None


def _parse(parser: Any, text: str) -> Any:
    kwargs = {"now": NOW}

    return parser.parse(text, **kwargs)


def _is_recurrence_date_only(data: dict[str, Any]) -> bool:
    """Date-only recurrence: серия без времени суток (якорь на полуночи,
    start==end, есть recurrence). Для неё нельзя требовать start>=NOW —
    сегодняшний день ещё актуален, хотя start=00:00 уже «в прошлом»."""
    if not data.get("recurrence"):
        return False
    if data.get("datetime"):
        return False
    start = data.get("start")
    end = data.get("end")
    return bool(start and end and start == end and start.endswith("T00:00:00"))


def _validate(case: Case, result: Any) -> list[str]:
    errors: list[str] = []
    data = normalize_result(result)

    # Ожидаем None: неоднозначные (прошлый период + только время) и нереализованные фичи.
    if case.temporal == "none":
        if data is not None:
            errors.append(f"expected None (ambiguous/feature-gap), got {data!r}")
        return errors

    if data is None:
        return [f"None result for valid case: {case.text!r}"]

    dt = _primary_dt(data)
    is_past = data.get("is_past")

    if case.temporal == "past":
        if dt is None:
            errors.append("expected a primary datetime/start/deadline for past case")
        elif not dt < NOW:
            errors.append(f"expected past datetime, got {dt.isoformat()}")
        if is_past is not True:
            errors.append(f"expected is_past=True, got {is_past!r}")

    elif case.temporal == "future":
        if _is_recurrence_date_only(data):
            # date-only серия: проверяем только флаг, не start (сегодня ещё актуален)
            if is_past is True:
                errors.append("expected non-past recurrence, got is_past=True")
        else:
            if dt is None:
                errors.append("expected a primary datetime/start/deadline for future case")
            elif not dt >= NOW:
                errors.append(f"expected future/current datetime, got {dt.isoformat()}")
            if is_past is True:
                errors.append("expected non-past result, got is_past=True")

    return errors


def run_cases(verbose: bool = False) -> dict[str, Any]:
    from timesense import TimeSenseParser

    parser = TimeSenseParser()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    crashes: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()

    for case in make_cases():
        try:
            result = _parse(parser, case.text)
            data = normalize_result(result)
            result_type = "None" if result is None else type(result).__name__
            type_counts[result_type] += 1
            for tag in case.tags:
                tag_counts[tag] += 1

            errors = _validate(case, result)
            if errors:
                failures.append(
                    {
                        "id": case.id,
                        "text": case.text,
                        "tags": list(case.tags),
                        "temporal": case.temporal,
                        "errors": errors,
                        "result": data,
                    }
                )

            row = {
                "id": case.id,
                "text": case.text,
                "tags": list(case.tags),
                "temporal": case.temporal,
                "result": data,
                "errors": errors,
            }
            rows.append(row)

            if verbose:
                from timesense.tests._pretty import card
                print(card(row, LANGUAGE))
                print()

        except Exception as exc:  # noqa: BLE001
            crashes.append(
                {
                    "id": case.id,
                    "text": case.text,
                    "tags": list(case.tags),
                    "temporal": case.temporal,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            type_counts["CRASH"] += 1

    return {
        "now": NOW.isoformat(),
        "language": LANGUAGE,
        "case_count": len(make_cases()),
        "type_counts": dict(type_counts),
        "tag_counts": dict(tag_counts),
        "failures": failures,
        "crashes": crashes,
        "rows": rows,
        "multi": run_multi(),
    }


def run_multi() -> list[dict[str, Any]]:
    from timesense import TimeSenseParser

    parser = TimeSenseParser()
    out: list[dict[str, Any]] = []

    for text, expected_min in MULTI_CASES:
        try:
            kwargs = {"now": NOW}

            results = parser.parse_multi(text, **kwargs)
            out.append(
                {
                    "text": text,
                    "expected_min": expected_min,
                    "count": len(results),
                    "results": [normalize_result(r) for r in results],
                }
            )
        except Exception as exc:  # noqa: BLE001
            out.append(
                {
                    "text": text,
                    "expected_min": expected_min,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return out


def print_summary(snapshot: dict[str, Any]) -> None:
    from timesense.tests._pretty import header, summary, card
    print(header(snapshot, snapshot["language"], mode_all=False))
    # показываем только проблемные карточки (краши/ошибки) в обычном режиме
    if snapshot["failures"]:
        print()
        for row in snapshot["failures"][:80]:
            print(card(row, snapshot["language"]))
            print()
    print(summary(snapshot, snapshot["language"]))
    if False:  # старый детальный вывод отключён (оставлен ниже как справка)
        print(f"NOW={snapshot['now']}")
        print(f"language={snapshot['language']}")
        print(f"cases={snapshot['case_count']}")
        print(f"type counts: {snapshot['type_counts']}")
        print(f"crashes: {len(snapshot['crashes'])}")
        print(f"semantic failures: {len(snapshot['failures'])}")

    if snapshot["crashes"]:
        print("\nCRASHES, first 50:")
        for row in snapshot["crashes"][:50]:
            print(f"  {row['id']} {row['text']!r}: {row['error_type']}: {row['error']}")

    if snapshot["failures"]:
        print("\nSEMANTIC FAILURES, first 80:")
        for row in snapshot["failures"][:80]:
            print(f"  {row['id']} {row['text']!r} temporal={row['temporal']} tags={tuple(row['tags'])}")
            for err in row["errors"]:
                print(f"    - {err}")

    from timesense.tests._pretty import multi_block
    print()
    print(multi_block(snapshot["multi"], snapshot["language"]))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--audit", action="store_true", help="do not exit 1 on semantic failures")
    ap.add_argument("--save-snapshot", type=Path)
    args = ap.parse_args(argv)

    snapshot = run_cases(verbose=args.verbose)

    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    else:
        print_summary(snapshot)

    if args.save_snapshot:
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"\nsaved snapshot: {args.save_snapshot}")

    bad_multi = [
        item for item in snapshot["multi"]
        if ("error_type" in item) or (item.get("count", 0) < item.get("expected_min", 0))
    ]

    if snapshot["crashes"] or bad_multi:
        return 1
    if snapshot["failures"] and not args.audit:
        return 1
    return 0


def make_cases() -> list[Case]:
    raw: list[Case] = []

    def add(text: str, tags: tuple[str, ...], temporal: str = "any") -> None:
        raw.append(Case(id="tmp", text=" ".join(text.split()), tags=tags, temporal=temporal))

    titles = [
        "проверить договор с поставщиком",
        "подготовить письмо для клиента",
        "обновить инструкцию по релизу",
        "разобрать замечания ревьюера",
        "согласовать макет лендинга",
        "проверить оплату инвойса",
        "создать резервную копию базы",
        "обсудить план миграции",
        "отправить финальную смету",
        "провести демонстрацию прототипа",
        "собрать список вопросов",
        "проверить отчёт по метрикам",
        "подготовить материалы для юристов",
        "обновить карточки задач",
        "запланировать интервью с кандидатом",
        "проверить доступы подрядчика",
        "написать краткое резюме встречи",
        "разобрать входящие заявки",
        "проверить экспорт аналитики",
        "подготовить публикацию changelog",
        "созвониться с дизайнером",
        "проверить состояние бэкапов",
        "сверить документы для бухгалтерии",
        "отправить приглашения участникам",
        "проверить ошибки мониторинга",
        "подготовить список рисков",
        "разобрать фидбек пользователей",
        "обновить план тестирования",
        "согласовать дату презентации",
        "проверить права доступа",
        "провести ревью pull request",
        "подготовить релизные заметки",
        "настроить окружение для демо",
        "собрать данные по конверсии",
        "проверить статусы платежей",
        "написать ответ партнёру",
        "пересчитать бюджет кампании",
        "обновить дорожную карту",
        "сверить список участников",
        "проверить интеграцию календаря",
        "заказать пропуска для гостей",
        "проверить готовность стенда",
        "собрать обратную связь от отдела продаж",
        "подготовить список блокеров",
        "обновить матрицу рисков",
        "проверить договор аренды",
        "согласовать график отпусков",
        "сверить список оборудования",
        "передать материалы подрядчику",
        "подготовить вопросы для интервью",
    ]

    # Past: varied forms, no invalid nonsense.
    past_markers = [
        "вчера", "позавчера", "три дня назад", "четыре дня назад", "пять дней назад",
        "две недели назад", "в прошлый понедельник", "в прошлую среду", "в прошлую пятницу",
    ]
    past_times = ["в 08:05", "в 09:40", "в 11:15", "в 14:30", "в 18:20"]
    for i, marker in enumerate(past_markers):
        for j, tm in enumerate(past_times):
            add(f"{marker} {tm} {titles[(i * 7 + j) % len(titles)]}", ("past", "date_time"), "past")

    # Ambiguous: прошлый ПЕРИОД + только время (день/число не заданы) → None.
    # Момент внутри недели/месяца/квартала/года не определяется.
    ambiguous_none_cases = [
        "на прошлой неделе в 14:30 написать краткое резюме встречи",
        "на прошлой неделе в 09:40 запланировать интервью с кандидатом",
        "на прошлой неделе в 11:15 проверить доступы подрядчика",
        "на прошлой неделе в 08:05 обновить карточки задач",
        "на прошлой неделе в 18:20 разобрать входящие заявки",
        "в прошлом месяце в 14:30 отправить приглашения участникам",
        "в прошлом месяце в 11:15 сверить документы для бухгалтерии",
        "в прошлом месяце в 08:05 созвониться с дизайнером",
        "в прошлом месяце в 18:20 проверить ошибки мониторинга",
        "в прошлом месяце в 09:40 проверить состояние бэкапов",
        "в прошлом квартале в 09:40 согласовать дату презентации",
        "в прошлом квартале в 08:05 обновить план тестирования",
        "в прошлом квартале в 14:30 провести ревью pull request",
        "в прошлом квартале в 18:20 подготовить релизные заметки",
        "в прошлом квартале в 11:15 проверить права доступа",
        "в прошлом году в 11:15 пересчитать бюджет кампании",
        "в прошлом году в 08:05 проверить статусы платежей",
        "в прошлом году в 14:30 обновить дорожную карту",
        "в прошлом году в 09:40 написать ответ партнёру",
        "в прошлом году в 18:20 сверить список участников",
    ]
    for text in ambiguous_none_cases:
        add(text, ("ambiguous_past_period", "expected_none"), "none")

    # Today/future.
    future_markers = [
        "сегодня", "завтра", "послезавтра", "через день", "через два дня",
        "через три дня", "через неделю", "через две недели", "через месяц",
        "в ближайшую пятницу", "в следующий понедельник", "в следующую среду",
    ]
    future_times = ["в 16:05", "в 17:10", "в 18:25", "в 19:30"]
    for i, marker in enumerate(future_markers):
        for j, tm in enumerate(future_times):
            add(f"{marker} {tm} {titles[(100 + i * 5 + j) % len(titles)]}", ("future", "date_time"), "future")

    # Absolute dates.
    absolute_cases = [
        "первого сентября провести школьную линейку",
        "пятого января сверить праздничный график",
        "десятого февраля подготовить пакет документов",
        "двадцать первого марта провести весеннюю презентацию",
        "тридцать первого декабря закрыть годовой отчёт",
        "двадцать восьмого февраля проверить договор аренды",
        "пятнадцатого июля отправить промежуточный отчёт",
        "двадцать пятого декабря поздравить партнёров",
        "первого марта обновить план найма",
        "двадцатого октября проверить подготовку конференции",
        "2 января в 09:00 проверить договор аренды",
        "7 февраля в 13:30 подготовить пакет документов",
        "12 марта в 18:15 провести ревью pull request",
        "19 апреля в 10:45 согласовать график отпусков",
        "24 мая в 16:20 сверить список оборудования",
        "30 июня в 11:10 передать материалы подрядчику",
        "6 июля в 17:55 подготовить вопросы для интервью",
        "18 августа в 12:25 обновить матрицу рисков",
        "29 сентября в 15:35 собрать обратную связь от отдела продаж",
        "31 декабря в 23:30 проверить готовность стенда",
    ]
    for text in absolute_cases:
        add(text, ("absolute_date",), "any")

    # Ranges.
    range_cases = [
        "сегодня с 16:20 до 17:05 сверить план миграции",
        "завтра с 08:30 до 09:15 провести утреннюю проверку логов",
        "послезавтра с 10:30 до 11:45 провести интервью с кандидатом",
        "вчера с 09:40 до 10:25 обсудить дизайн новой формы",
        "позавчера с 14:00 до 15:30 провести рабочую сессию по API",
        "в пятницу с 18:00 до 20:00 провести встречу с партнёром",
        "в прошлую пятницу с 12:10 до 13:00 разобрать список вопросов",
        "в следующий вторник с 23:15 до 00:45 проверить ночное окно работ",
        "с 1 по 5 августа оформить отпуск команды",
        "с 10 по 12 июля провести выездное обучение",
        "с 25 декабря по 5 января подготовить график дежурств",
        "с понедельника по пятницу с 10 до 12 провести серию семинаров",
        "со вторника по четверг с 14 до 16 организовать обучение операторов",
        "с утра до вечера провести инвентаризацию склада",
        "с вечера пятницы до утра понедельника организовать дежурство поддержки",
        "с начала недели до пятницы проверить все заявки",
    ]
    for text in range_cases:
        temporal = "past" if text.startswith(("вчера", "позавчера", "в прошлую")) else "any"
        add(text, ("range",), temporal)

    # Deadlines.
    deadline_cases = [
        "до 18:30 сегодня сдать подписанный договор",
        "до завтра подготовить презентацию для совета",
        "до завтра 10:00 обновить документацию для клиента",
        "до пятницы проверить расчёт бюджета",
        "до пятницы 18:00 закрыть критичные замечания",
        "до следующего понедельника написать ответ партнёру",
        "до конца дня проверить список доступов",
        "до конца недели отправить финальную версию макета",
        "до конца месяца подготовить пакет для бухгалтерии",
        "до конца квартала согласовать график платежей",
        "до конца года обновить дорожную карту",
        "к пятнице подготовить список рисков",
        "к понедельнику 12:00 проверить статусы платежей",
        "к концу дня сверить список участников",
        "к первому сентября подготовить форму для школы",
        "не позже пятницы согласовать дату презентации",
        "не позже конца месяца закрыть финансовые документы",
        "до последнего рабочего дня месяца подготовить финансовый отчёт",
        "до первого рабочего дня следующего месяца обновить план команды",
        "до 31 декабря 23:59 закрыть годовой отчёт",
    ]
    for text in deadline_cases:
        add(text, ("deadline",), "future")

    # Recurrence.
    recurrence_cases = [
        "каждый день в 08:10 принимать лекарство",
        "каждый день в 19:20 записывать итоги дня",
        "каждый будний день в 09:00 проверять очередь заявок",
        "каждый будний день до конца месяца в 09:30 проводить короткий статус",
        "по будням в 18:00 отправлять дневной отчёт",
        "по выходным в 11:00 проверять семейный календарь",
        "каждый понедельник в 10:00 проводить планирование недели",
        "каждую среду в 15:30 проводить ревью задач",
        "каждую пятницу в 16:00 собирать ретроспективу",
        "каждые 2 недели по понедельникам в 12:00 проводить синхронизацию",
        "каждый месяц 15 числа проверять оплату аренды",
        "каждый месяц 30 числа оплачивать сервисы",
        "каждый последний рабочий день месяца готовить отчёт по финансам",
        "каждый первый вторник месяца проводить продуктовый комитет",
        "первый вторник каждого января в 15:00 проводить годовое планирование",
        "каждый день до пятницы в 18:00 отправлять короткий статус",
        "каждый понедельник до конца квартала проводить архитектурный разбор",
        "каждую пятницу до конца года обновлять roadmap",
        "каждый месяц до декабря проверять продление лицензий",
        "каждый будний день кроме пятницы в 09:15 проверять инциденты",
    ]
    for text in recurrence_cases:
        add(text, ("recurrence",), "future")

    # Working days, fuzzy, locations, durations.
    special = [
        ("последний рабочий день месяца подготовить финансовый отчёт", ("working_days",), "future"),
        ("первый рабочий день месяца обновить план команды", ("working_days",), "any"),
        ("через два рабочих дня отправить юридический ответ", ("working_days",), "future"),
        ("через три рабочих дня проверить статус поставки", ("working_days",), "future"),
        ("за два рабочих дня до конца месяца напомнить про закрывающие документы", ("working_days",), "future"),
        ("каждый первый рабочий день месяца сверять бюджет отдела", ("working_days", "recurrence"), "future"),
        ("каждый последний рабочий день месяца закрывать финансовые задачи", ("working_days", "recurrence"), "future"),
        ("в ближайший рабочий день проверить договор", ("working_days", "feature_gap", "expected_none"), "none"),
        ("весной провести конференцию для партнёров", ("fuzzy", "period"), "any"),
        ("летом запланировать командный выезд", ("fuzzy", "period"), "any"),
        ("осенью подготовить крупный релиз", ("fuzzy", "period"), "future"),
        ("зимой провести аудит безопасности", ("fuzzy", "period"), "any"),
        ("в начале месяца обновить план продаж", ("fuzzy", "period"), "any"),
        ("в середине месяца сверить метрики продукта", ("fuzzy", "period"), "any"),
        ("в конце месяца оплатить счета подрядчиков", ("fuzzy", "period"), "future"),
        ("на следующей неделе провести встречу с командой поддержки", ("fuzzy", "period"), "future"),
        ("на прошлой неделе разобрать результаты эксперимента", ("fuzzy", "period"), "past"),
        ("завтра в 10:30 в офисе обсудить договор аренды", ("location", "date_time"), "future"),
        ("в пятницу в 18:00 в кафе провести встречу с партнёром", ("location", "date_time"), "future"),
        ("сегодня в 17:00 в Zoom провести демонстрацию экрана", ("location", "date_time"), "future"),
        ("вчера в 09:00 в переговорке разобрать инцидент", ("location", "date_time"), "past"),
        ("послезавтра в 07:30 в аэропорту встретить делегацию", ("location", "date_time"), "future"),
        ("в следующий вторник в 11:00 у клиента провести обучение", ("location", "date_time"), "future"),
        ("завтра в 10:00 провести встречу на 30 минут", ("duration", "date_time"), "future"),
        ("в пятницу в 14:00 провести демо на 45 минут", ("duration", "date_time"), "future"),
        ("вчера в 10:00 провести созвон на 30 минут", ("duration", "past"), "past"),
        ("позавчера в 12:00 провести интервью на 45 минут", ("duration", "past"), "past"),
        ("через 15 минут проверить статус деплоя", ("duration", "relative"), "future"),
        ("через полчаса позвонить администратору здания", ("duration", "relative"), "future"),
        ("через час напомнить про отправку договора", ("duration", "relative"), "future"),
        ("через два с половиной часа проверить результат миграции", ("duration", "relative"), "future"),
    ]
    for text, tags, temporal in special:
        add(text, tags, temporal)

    # Add varied natural fillers until 500, shuffled later. These are not adjacent duplicates.
    extra_markers = [
        ("завтра утром", "future"),
        ("завтра вечером", "future"),
        ("послезавтра утром", "future"),
        ("в следующий четверг", "future"),
        ("в ближайшую субботу", "future"),
        ("вчера вечером", "past"),
        ("позавчера утром", "past"),
        ("три дня назад вечером", "past"),
        ("в прошлую среду утром", "past"),
        ("на прошлой неделе в четверг", "past"),
    ]
    extra_tasks = [
        "проверить список открытых договоров",
        "подготовить краткое письмо клиенту",
        "обновить страницу релизных заметок",
        "разобрать комментарии службы поддержки",
        "согласовать правки в макете",
        "проверить поступление оплаты",
        "создать копию production базы",
        "обсудить перенос дедлайна",
        "отправить обновлённую смету",
        "провести внутреннюю демонстрацию",
    ]
    contexts = [
        "по проекту Atlas",
        "для клиента Север",
        "по внутреннему релизу",
        "для команды поддержки",
        "по финансовому блоку",
        "для юридического отдела",
        "по интеграции календаря",
        "для демо-стенда",
        "по миграции данных",
        "для партнёрской встречи",
    ]
    suffixes = ["в 09:05", "в 11:25", "в 14:40", "в 16:55", "до 18:00"]
    idx = 0
    while len(raw) < 500:
        marker, temporal = extra_markers[idx % len(extra_markers)]
        task = extra_tasks[(idx // len(extra_markers)) % len(extra_tasks)]
        suffix = suffixes[(idx // (len(extra_markers) * len(extra_tasks))) % len(suffixes)]
        context = contexts[(idx // (len(extra_markers) * len(extra_tasks) * len(suffixes))) % len(contexts)]
        add(f"{marker} {suffix} {task} {context}", ("mixed",), temporal)
        idx += 1

    rnd = random.Random(20260706)
    rnd.shuffle(raw)

    seen_texts: set[str] = set()
    out: list[Case] = []
    for case in raw:
        if case.text in seen_texts:
            raise AssertionError(f"duplicate after generation: {case.text!r}")
        seen_texts.add(case.text)
        out.append(Case(id=f"ru_{len(out) + 1:03d}", text=case.text, tags=case.tags, temporal=case.temporal))

    if len(out) != 500:
        raise AssertionError(f"RU cases count mismatch: {len(out)}")
    return out


MULTI_CASES = [
    ("завтра в 10 планирование релиза, в 15 разбор заявок и послезавтра в 12 встреча с юристами", 3),
    ("вчера в 10 разбор инцидента, позавчера в 12 интервью и неделю назад в 9 сверка отчёта", 3),
    ("сегодня до 18 закрыть договор, завтра в 9 показать демо, в пятницу в 16 собрать ретро", 3),
    ("в понедельник в 10 планирование и каждый день до пятницы в 18 отправлять статус", 2),
    ("до конца месяца закрыть финансовые документы, каждый понедельник проверять риски", 2),
    ("с 10 до 12 провести воркшоп, с 23 до 1 проверить ночной релиз, через полчаса позвонить дежурному", 3),
]


def _case_id(case: Case) -> str:
    safe = case.text.replace("[", "(").replace("]", ")")
    return f"{case.id}:{case.temporal}:{safe[:80]}"


@pytest.mark.parametrize("case", make_cases(), ids=_case_id)
def test_case_semantics(case: Case) -> None:
    from timesense import TimeSenseParser

    result = _parse(TimeSenseParser(), case.text)
    errors = _validate(case, result)
    assert not errors, f"{case.text!r}: {errors}; result={normalize_result(result)}"


def test_parse_multi_cases() -> None:
    bad = [
        item for item in run_multi()
        if ("error_type" in item) or (item.get("count", 0) < item.get("expected_min", 0))
    ]
    assert not bad, bad[:10]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

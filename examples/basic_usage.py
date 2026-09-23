"""Базовые примеры использования timesense."""
from datetime import datetime
from timesense import TimeSenseParser, TaskType

# Фиксированное "сейчас" для воспроизводимости вывода
NOW = datetime(2026, 2, 14, 14, 0)
parser = TimeSenseParser()


def show(text):
    r = parser.parse(text, now=NOW)
    if r is None:
        print(f"{text!r:40} -> (дата/время не найдены)")
        return
    print(f"{text!r:40} -> {type(r).__name__}: {r.human_readable()} | title={r.title!r}")


def example_basic():
    print("=== Базовые примеры ===")
    for t in [
        "завтра в 10 встреча",
        "сегодня вечером созвон",
        "через 2 часа позвонить",
        "в 15:30 планёрка",
        "встреча 15:00",
    ]:
        show(t)
    print()


def example_dates():
    print("=== Даты ===")
    for t in [
        "10 января день рождения",
        "первого сентября линейка",
        "в пятницу обед",
        "на следующей неделе встреча",
        "в конце месяца отчёт",
    ]:
        show(t)
    print()


def example_ranges_and_recurrence():
    print("=== Диапазоны и повторения ===")
    for t in [
        "с 10 до 11 созвон в офисе",
        "с понедельника по среду командировка",
        "каждый понедельник планёрка",
        "по будням зарядка",
    ]:
        show(t)
    print()


def example_to_dict():
    print("=== JSON (to_dict) ===")
    import json
    r = parser.parse("каждый понедельник планёрка", now=NOW)
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    print()


def example_task_types():
    print("=== Типы задач ===")
    r = parser.parse("до пятницы сдать отчёт", now=NOW)
    print("task_type:", r.task_type, "| это дедлайн:", r.task_type == TaskType.DEADLINE)
    print()


def example_english():
    print("=== English ===")
    for t in [
        "remind me tomorrow at 9am to call mom",
        "every weekday at 9 standup",
        "from 10 to 11:30 sync in the meeting room",
        "by eod send the report",
        "next week on Wednesday at 3pm dentist",
        "this weekend cottage",
        "in October vacation",
        "after lunch call the bank",
    ]:
        show(t)
    print()


if __name__ == "__main__":
    example_basic()
    example_dates()
    example_ranges_and_recurrence()
    example_to_dict()
    example_task_types()
    example_english()

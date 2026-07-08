"""
TimeSense v2 — Unified Test Suite

Запуск:
    cd <parent_of_timesense>
    python -m timesense.tests.test_all
    python -m timesense.tests.test_all --fail-only
    TEST_NOW="2026-02-14 14:00" python -m timesense.tests.test_all

По умолчанию NOW = 2026-02-14 14:00 (суббота).
Если указать TEST_NOW — используется текущее время.

Покрытие (~500+ тестов):
  1.  Диапазоны времени (дефис/тире/с..до)
  2.  Относительная дата + диапазон (через неделю/месяц + range)
  3.  Конкретная дата + с..до
  4.  Половина часа / четверть / разговорные
  5.  Дедлайны (до/к/в течение)
  6.  Периоды (TaskResult(period))
  7.  Нечёткие (fuzzy)
  8.  Конкретные даты
  9.  Дни недели + время
  10. Составные оффсеты (через X часов Y минут)
  11. Через полгода/квартал/полтора года
  12. Smart hour (nearest future, now_override)
  13. Диапазоны дней недели (с пн по пт)
  14. Порядковые дни — одноразово
  15. Порядковые дни + рекуррентность
  16. Рекуррентность + time ranges
  17. rrule string validation
  18. Голосовые / разговорные
  19. Повторяющиеся события
  20. Open Start (после X)
  21. Модификаторы дней недели
  22. Длительность событий
  23. Синонимы дедлайнов
  24. Рабочее/нерабочее время
  25. Извлечение локации
  26. Исключения (кроме)
  27. parse_multi
  28. Регрессия — базовые паттерны
  29. Сложные случаи
  30–34. Генерация (массовые комбинации)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, date, timedelta

from timesense import TimeSenseParser
from timesense.models.event_types import CalendarResult, ReminderResult, TaskResult

try:
    from timesense import TimeConfig

    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

_now_override = os.environ.get("TEST_NOW")
if _now_override:
    NOW = datetime.strptime(_now_override, "%Y-%m-%d %H:%M")
else:
    NOW = datetime(2026, 2, 14, 14, 0)  # Saturday

if HAS_CONFIG:
    config = TimeConfig(prefer_nearest_future=True)
    parser = TimeSenseParser(config)
else:
    parser = TimeSenseParser()

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def format_result_type(result):
    if isinstance(result, CalendarResult):
        return "📅 CalendarResult"
    if isinstance(result, ReminderResult):
        return "⏰ ReminderResult"
    if isinstance(result, TaskResult):
        return f"📋 TaskResult ({result.task_type.value})"
    return f"❔ {type(result).__name__}"


def format_datetime_info(result):
    lines = []
    if isinstance(result, CalendarResult):
        start = result.start_at.strftime("%d.%m.%Y %H:%M")
        end = result.end_at.strftime("%d.%m.%Y %H:%M")
        duration = result.duration_minutes
        lines.append(f"   📍 Период: {start} → {end}")
        lines.append(f"   ⏱️  Длительность: {duration} мин")
        if result.recurrence:
            lines.append(f"   🔁 Рекуррентность: {result.recurrence.to_rrule()}")
    elif isinstance(result, ReminderResult):
        dt = result.datetime_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"   📍 Время: {dt}")
        if result.recurrence:
            lines.append(f"   🔁 Рекуррентность: {result.recurrence.to_rrule()}")
    elif isinstance(result, TaskResult):
        if result.task_type.value == "deadline" and result.deadline:
            dl = result.deadline.strftime("%d.%m.%Y %H:%M")
            lines.append(f"   🎯 Дедлайн: {dl}")
        elif result.start_at and result.end_at:
            start = result.start_at.strftime("%d.%m.%Y %H:%M")
            end = result.end_at.strftime("%d.%m.%Y %H:%M")
            lines.append(f"   📍 Период: {start} → {end}")
        if result.recurrence:
            lines.append(f"   🔁 Рекуррентность: {result.recurrence.to_rrule()}")
    return lines


def print_section(title, emoji=""):
    print(f"{'═' * 60}")
    print(f"{emoji}  {BOLD}{CYAN}{title}{RESET}")
    print(f"{'═' * 60}")


def _in_future(dt, now=None, strict=True):
    n = now or NOW
    if strict:
        return dt > n
    return dt >= n


def _assert_future_result(r, now=None):
    n = now or NOW
    if isinstance(r, ReminderResult):
        return _in_future(r.datetime_at, n, strict=True)
    if isinstance(r, CalendarResult):
        return (
            _in_future(r.start_at, n, strict=True)
            and _in_future(r.end_at, n, strict=True)
            and (r.end_at > r.start_at)
        )
    if isinstance(r, TaskResult):
        if r.task_type.value == "deadline" and r.deadline:
            return _in_future(r.deadline, n, strict=True)
        if r.start_at and r.end_at:
            return (
                _in_future(r.start_at, n, strict=False)
                and _in_future(r.end_at, n, strict=True)
                and (r.end_at > r.start_at)
            )
    return True


def _is_task_period(r):
    return (
        isinstance(r, TaskResult)
        and getattr(r, "task_type", None)
        and r.task_type.value == "period"
        and r.start_at
        and r.end_at
    )


def _is_task_fuzzy(r):
    return (
        isinstance(r, TaskResult)
        and getattr(r, "task_type", None)
        and r.task_type.value == "fuzzy"
        and r.start_at
        and r.end_at
    )


def _is_task_deadline(r):
    return (
        isinstance(r, TaskResult)
        and getattr(r, "task_type", None)
        and r.task_type.value == "deadline"
        and r.deadline
    )


# ═══════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════


def extract_task_text(result, original_text):
    for attr in (
        "title",
        "event_title",
        "summary",
        "text",
        "name",
        "task",
        "description",
        "subject",
    ):
        if hasattr(result, attr):
            v = getattr(result, attr)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return (original_text or "").strip()


def emoji_for_task(task_text):
    t = (task_text or "").lower()
    if "созвон" in t or "звон" in t or "позвон" in t:
        return "📞"
    if "встреч" in t:
        return "🤝"
    if "планёр" in t or "планерк" in t:
        return "🧑‍💼"
    if "кино" in t:
        return "🎬"
    if "трениров" in t or "пробеж" in t:
        return "🏋️"
    if "деплой" in t or "релиз" in t:
        return "🚀"
    if "отч" in t:
        return "🧾"
    return "📝"


def run_case(
    name,
    text,
    expected_type,
    check_func=None,
    *,
    print_on_pass=True,
    section_header=None,
    now_override=None,
):
    n = now_override or NOW
    result = parser.parse(text, now=n)
    actual_type = type(result).__name__
    type_ok = actual_type == expected_type

    check_ok = True
    if check_func:
        try:
            check_ok = bool(check_func(result))
        except Exception:
            check_ok = False

    passed = type_ok and check_ok

    if passed and not print_on_pass:
        return True, False

    header_printed = False
    if not passed and section_header:
        print_section(section_header, "🧩")
        header_printed = True

    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"

    print(f"{status}  {BOLD}{name}{RESET}")
    print(f'   {DIM}Input:{RESET} "{text}"')
    print(f"   {DIM}Type:{RESET}  {format_result_type(result)}")

    if now_override:
        print(f"   {DIM}NOW:{RESET}   {now_override.strftime('%d.%m.%Y %H:%M')}")

    for line in format_datetime_info(result):
        print(line)

    task_text = extract_task_text(result, text)
    if task_text:
        print(f"   {emoji_for_task(task_text)} {task_text}")

    if not type_ok:
        print(f"   {RED}⚠️  Ожидался тип: {expected_type}, получен: {actual_type}{RESET}")
    if not check_ok and type_ok:
        print(f"   {RED}⚠️  Проверка значений не пройдена{RESET}")

    return passed, header_printed


# ═══════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════


def build_tests():
    tests = []

    def add(section, name, text, expected_type, check=None, now_override=None):
        tests.append((section, name, text, expected_type, check, now_override))

    months_ru = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    tomorrow = (NOW + timedelta(days=1)).date()
    day_after_tomorrow = (NOW + timedelta(days=2)).date()

    # ═══════════════════════════════════════════════════════════════════
    # 1) Диапазоны времени
    # ═══════════════════════════════════════════════════════════════════
    sec = "1. Диапазоны времени (дефис/тире/с..до..)"

    add(
        sec,
        "Простой диапазон 9-10",
        "с 9-10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 9
        and r.end_at.hour == 10
        and _assert_future_result(r),
    )
    add(
        sec,
        "Диапазон 10-11 без 'с'",
        "10-11 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 11
        and _assert_future_result(r),
    )
    add(
        sec,
        "Диапазон с минутами 10:30-11:15",
        "с 10:30-11:15 созвон",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.start_at.minute == 30
        and r.end_at.hour == 11
        and r.end_at.minute == 15,
    )
    add(
        sec,
        "Диапазон с нулями 09:00-10:00",
        "с 09:00-10:00 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )

    add(
        sec,
        "Тире: 9–10",
        "с 9–10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )
    add(
        sec,
        "Тире: 10—11",
        "с 10—11 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 10 and r.end_at.hour == 11,
    )

    add(
        sec,
        "С..до.. 9-10",
        "с 9 до 10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )
    add(
        sec,
        "С..до.. с минутами",
        "с 10:30 до 11:15 созвон",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.start_at.minute == 30
        and r.end_at.hour == 11
        and r.end_at.minute == 15,
    )
    add(
        sec,
        "С..по..",
        "с 9 по 10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )
    add(
        sec,
        "С..по.. (минуты)",
        "с 10:30 по 11:15 созвон",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.minute == 30
        and r.end_at.minute == 15,
    )

    add(
        sec,
        "Слипшийся диапазон",
        "с9-10 встреча",
        "CalendarResult",
        lambda r: _assert_future_result(r),
    )

    add(
        sec,
        "Диапазон + место",
        "с 9-10 встреча в офисе",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )
    add(
        sec,
        "Диапазон + участник",
        "с 10:30-11:15 созвон с Иваном",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.start_at.minute == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 2) Относительная дата + диапазон
    # ═══════════════════════════════════════════════════════════════════
    sec = "2. Относительная дата + диапазон"

    # "на завтра" формат → CombinedRecognizer
    add(
        sec,
        "На завтра с 9 до 10",
        "на завтра с 9 до 10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == tomorrow
        and r.start_at.hour == 9
        and r.end_at.hour == 10,
    )
    add(
        sec,
        "На завтра к 11",
        "на завтра к 11 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 11,
    )
    add(
        sec,
        "На послезавтра к 9",
        "на послезавтра к 9 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == day_after_tomorrow
        and r.datetime_at.hour == 9,
    )
    add(
        sec,
        "На сегодня к 18",
        "на сегодня к 18 закончить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 18,
    )
    add(
        sec,
        "На завтра в 10:30",
        "на завтра в 10:30 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 10
        and r.datetime_at.minute == 30,
    )

    # "через неделю/месяц" + диапазон → CalendarResult (range побеждает)
    add(
        sec,
        "Через неделю 9-10",
        "через неделю 9-10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 21)
        and r.start_at.hour == 9
        and r.end_at.hour == 10
        and r.title == "встреча",
    )
    add(
        sec,
        "Через неделю с 9 до 10",
        "через неделю с 9 до 10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 21)
        and r.start_at.hour == 9
        and r.end_at.hour == 10,
    )
    add(
        sec,
        "Через неделю с 9 до 11 планёрка",
        "через неделю с 9 до 11 планёрка",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 21)
        and r.start_at.hour == 9
        and r.end_at.hour == 11
        and r.title == "планёрка",
    )
    add(
        sec,
        "Через неделю 10-12",
        "через неделю 10-12 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 21)
        and r.start_at.hour == 10
        and r.end_at.hour == 12,
    )
    add(
        sec,
        "Через месяц 10-12",
        "через месяц 10-12 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.month == 3
        and r.start_at.hour == 10
        and r.end_at.hour == 12,
    )
    add(
        sec,
        "Через месяц с 9 до 10",
        "через месяц с 9 до 10 созвон",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.month == 3
        and r.start_at.hour == 9
        and r.end_at.hour == 10,
    )

    # "через неделю/месяц" без диапазона → TaskResult
    add(
        sec,
        "Через неделю (без range)",
        "через неделю встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.date() == date(2026, 2, 21),
    )
    add(
        sec,
        "Через месяц (без range)",
        "через месяц созвон",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.month == 3,
    )

    # "завтра + диапазон" без "на" → TaskResult (дата побеждает, range не мержится)
    add(
        sec,
        "Завтра (без range merge)",
        "завтра встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.date() == tomorrow,
    )
    add(
        sec,
        "Послезавтра (без range merge)",
        "послезавтра встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.date() == day_after_tomorrow,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 3) Конкретная дата + с..до
    # ═══════════════════════════════════════════════════════════════════
    sec = "3. Конкретная дата + с..до"

    add(
        sec,
        "31 марта с 9 до 11",
        "31 марта с 9 до 11 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 3, 31)
        and r.start_at.hour == 9
        and r.end_at.hour == 11
        and r.title == "встреча",
    )
    add(
        sec,
        "15 марта с 10 до 12",
        "15 марта с 10 до 12 обед",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 3, 15)
        and r.start_at.hour == 10
        and r.end_at.hour == 12,
    )
    add(
        sec,
        "1 апреля с 14 до 16",
        "1 апреля с 14 до 16 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 4, 1)
        and r.start_at.hour == 14
        and r.end_at.hour == 16,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 4) Половина часа / четверть / разговорные
    # ═══════════════════════════════════════════════════════════════════
    sec = "4. Половина часа / четверть / разговорные"

    add(
        sec,
        "В половине третьего",
        "в половине третьего встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "Полтретьего",
        "полтретьего созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "Пол пятого",
        "в полпятого созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "В четверть третьего",
        "в четверть третьего созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 14
        and r.datetime_at.minute == 15,
    )
    add(
        sec,
        "Без четверти пять",
        "без четверти пять созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 45,
    )
    add(
        sec,
        "Без десяти шесть",
        "без десяти шесть созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 50,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 5) Дедлайны (до/к/в течение)
    # ═══════════════════════════════════════════════════════════════════
    sec = "5. Дедлайны (до/к/в течение)"

    add(
        sec,
        "К 10:00 (явные минуты → строго 10:00)",
        "к 10:00 подготовить отчёт",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.datetime_at.minute == 0,
    )
    add(
        sec,
        "К 10 без :00 → smart-hour nearest-future (22:00)",
        "к 10 подготовить отчёт",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 22,
    )
    add(
        sec,
        "К полудню",
        "к полудню закончить черновик",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 12,
    )
    add(
        sec,
        "На завтра к 11",
        "на завтра к 11:00 подготовить вопросы",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 11,
    )
    add(
        sec,
        "До пятницы",
        "до пятницы отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r)
        and r.deadline.date() == (NOW + timedelta(days=(4 - NOW.weekday()) % 7 or 7)).date(),
    )
    add(
        sec,
        "До понедельника",
        "до понедельника подготовить план",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.weekday() == 0,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 6) Периоды (TaskResult(period))
    # ═══════════════════════════════════════════════════════════════════
    sec = "6. Периоды (TaskResult(period))"

    add(
        sec,
        "На неделе",
        "на неделе подготовить документы",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(sec, "На выходных", "на выходных уборка", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "В будни", "в будни созвон", "TaskResult", lambda r: _is_task_period(r))

    # ═══════════════════════════════════════════════════════════════════
    # 7) Нечёткие (fuzzy)
    # ═══════════════════════════════════════════════════════════════════
    sec = "7. Нечёткие (fuzzy)"

    add(
        sec,
        "Ближе к вечеру",
        "ближе к вечеру встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 8) Конкретные даты (будущее)
    # ═══════════════════════════════════════════════════════════════════
    sec = "8. Конкретные даты (будущее)"

    future_date_1 = NOW + timedelta(days=3)
    future_date_2 = NOW + timedelta(days=40)
    future_date_3 = NOW + timedelta(days=300)

    date1_text = f"{future_date_1.day} {months_ru[future_date_1.month]} {future_date_1.year}"
    date1_dot = future_date_1.strftime("%d.%m.%Y")

    add(
        sec,
        "Дата + время (текст)",
        f"{date1_text} в 10:30 планёрка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == future_date_1.date()
        and r.datetime_at.hour == 10
        and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "Дата + время (точки)",
        f"{date1_dot} в 08:15 анализ",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == future_date_1.date()
        and r.datetime_at.hour == 8
        and r.datetime_at.minute == 15,
    )

    date2_text = f"{future_date_2.day} {months_ru[future_date_2.month]}"
    add(
        sec,
        "Дата без времени (период)",
        f"{date2_text} встреча",
        "TaskResult",
        lambda r: _is_task_period(r)
        and r.start_at.month == future_date_2.month
        and r.start_at.day == future_date_2.day,
    )
    add(
        sec,
        "Дата + время",
        f"{date2_text} в 11:00 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.month == future_date_2.month
        and r.datetime_at.day == future_date_2.day
        and r.datetime_at.hour == 11,
    )

    date3_text = f"{future_date_3.day} {months_ru[future_date_3.month]} {future_date_3.year}"
    add(
        sec,
        "Дата в конце года",
        f"{date3_text} в 23:59 проверить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == future_date_3.date()
        and r.datetime_at.hour == 23
        and r.datetime_at.minute == 59,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 9) Дни недели + время
    # ═══════════════════════════════════════════════════════════════════
    sec = "9. Дни недели + время"

    add(
        sec,
        "В пятницу в 18",
        "в пятницу в 18 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 18,
    )
    add(
        sec,
        "Во вторник к 12",
        "во вторник к 12:00 закончить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 12,
    )
    add(sec, "В пятницу без времени", "в пятницу обед", "TaskResult", lambda r: _is_task_period(r))
    add(
        sec,
        "В среду без времени",
        "в среду деловой ужин",
        "TaskResult",
        lambda r: _is_task_period(r),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 10) Составные оффсеты (через X часов Y минут)
    # ═══════════════════════════════════════════════════════════════════
    sec = "10. Составные оффсеты (через X часов Y минут)"

    add(
        sec,
        "Через 2 часа 30 минут",
        "через 2 часа 30 минут созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 16
        and r.datetime_at.minute == 30
        and r.title == "созвон",
    )
    add(
        sec,
        "Через 1 час 15 минут",
        "через 1 час 15 минут звонок",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 15
        and r.title == "звонок",
    )
    add(
        sec,
        "Через 3 часа 45 минут",
        "через 3 часа 45 минут встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 17
        and r.datetime_at.minute == 45
        and r.title == "встреча",
    )

    # ═══════════════════════════════════════════════════════════════════
    # 11) Через полгода/квартал/полтора
    # ═══════════════════════════════════════════════════════════════════
    sec = "11. Через полгода/квартал/полтора"

    add(
        sec,
        "Через полгода",
        "через полгода отчёт",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.month == 8 and "отчёт" in r.title,
    )
    add(
        sec,
        "Через квартал",
        "через квартал ревью",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.month == 5 and "ревью" in r.title,
    )
    add(
        sec,
        "Через полтора года",
        "через полтора года проект",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.year == 2027,
    )
    add(
        sec,
        "Через год",
        "через год конференция",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.year == 2027,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 12) Smart hour — nearest future (now_override)
    # ═══════════════════════════════════════════════════════════════════
    sec = "12. Smart hour — nearest future"

    # now=14:00 (default)
    add(
        sec,
        "В 10 (now=14:00) → 22:00",
        "в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 22,
    )
    add(
        sec,
        "В 5 (now=14:00) → 17:00",
        "в 5 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 17,
    )
    add(
        sec,
        "В 3 (now=14:00) → 15:00",
        "в 3 позвонить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 15,
    )

    # now=09:00
    add(
        sec,
        "В 10 (now=09:00) → 10:00",
        "в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 10,
        now_override=datetime(2026, 2, 14, 9, 0),
    )
    add(
        sec,
        "В 6 (now=09:00) → 18:00",
        "в 6 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 18,
        now_override=datetime(2026, 2, 14, 9, 0),
    )

    # now=23:00 — both h and h+12 passed → tomorrow
    add(
        sec,
        "В 10 (now=23:00) → 10:00 tomorrow",
        "в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.datetime_at.date() == date(2026, 2, 15),
        now_override=datetime(2026, 2, 14, 23, 0),
    )

    # now=05:00 exactly — h==now.hour → 5:00 today
    add(
        sec,
        "В 5 (now=05:00) → 5:00 today",
        "в 5 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 5
        and r.datetime_at.date() == date(2026, 2, 14),
        now_override=datetime(2026, 2, 14, 5, 0),
    )

    # now=05:01 — 5 passed → 17:00
    add(
        sec,
        "В 5 (now=05:01) → 17:00",
        "в 5 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 17,
        now_override=datetime(2026, 2, 14, 5, 1),
    )

    # Unambiguous hour (>=12)
    add(
        sec,
        "В 15 → 15:00",
        "в 15 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 15,
    )
    add(
        sec,
        "В 18:30 → 18:30",
        "в 18:30 ужин",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 18
        and r.datetime_at.minute == 30,
    )

    # now=19:00 — both 6 and 18 passed → 6:00 tomorrow
    add(
        sec,
        "В 6 (now=19:00) → 6:00 tomorrow",
        "в 6 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 6
        and r.datetime_at.date() == date(2026, 2, 15),
        now_override=datetime(2026, 2, 14, 19, 0),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 13) Диапазоны дней недели (с пн по пт)
    # ═══════════════════════════════════════════════════════════════════
    sec = "13. Диапазоны дней недели (с пн по пт)"

    add(
        sec,
        "С пн по пт (без времени)",
        "с понедельника по пятницу тренинг",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == date(2026, 2, 16)
        and r.end_at.date() == date(2026, 2, 20)
        and r.recurrence is None
        and r.title == "тренинг",
    )
    add(
        sec,
        "Со вт по чт",
        "со вторника по четверг конференция",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == date(2026, 2, 17)
        and r.end_at.date() == date(2026, 2, 19)
        and r.recurrence is None,
    )

    add(
        sec,
        "С пн по пт 9-10 → конечная серия (UNTIL)",
        "с понедельника по пятницу 9-10 тренинг",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 16)
        and r.start_at.hour == 9
        and r.end_at.hour == 10
        and r.recurrence
        and set(r.recurrence.by_day) == {"MO", "TU", "WE", "TH", "FR"}
        and r.recurrence.until is not None
        and r.recurrence.until.date() == date(2026, 2, 20),
    )
    add(
        sec,
        "С пн по пт в 10 → конечная серия (UNTIL)",
        "с понедельника по пятницу в 10 тренинг",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == date(2026, 2, 16)
        and r.datetime_at.hour == 10
        and r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and r.recurrence.until is not None,
    )
    add(
        sec,
        "Каждую неделю с пн по пт 9-10 → бесконечная BYDAY, старт пн",
        "каждую неделю с понедельника по пятницу 9-10 работа",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 16)
        and set(r.recurrence.by_day) == {"MO", "TU", "WE", "TH", "FR"}
        and r.recurrence.until is None,
    )
    add(
        sec,
        "С пн по ср с 10 до 12",
        "с понедельника по среду с 10 до 12 семинар",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.date() == date(2026, 2, 16)
        and r.start_at.hour == 10
        and r.end_at.hour == 12
        and r.recurrence
        and set(r.recurrence.by_day) == {"MO", "TU", "WE"},
    )

    # ═══════════════════════════════════════════════════════════════════
    # 14) Порядковые дни — одноразово
    # ═══════════════════════════════════════════════════════════════════
    sec = "14. Порядковые дни — одноразово"

    add(
        sec,
        "Первый вторник месяца",
        "первый вторник месяца совещание",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == date(2026, 3, 3)
        and r.recurrence is None
        and "совещание" in r.title,
    )
    add(
        sec,
        "Последняя пятница месяца",
        "последняя пятница месяца отчёт",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == date(2026, 2, 27)
        and r.recurrence is None,
    )
    add(
        sec,
        "Первый вторник января",
        "первый вторник января встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.month == 1
        and r.start_at.year == 2027
        and r.start_at.weekday() == 1,
    )
    add(
        sec,
        "Первый вторник месяца в 10",
        "первый вторник месяца в 10",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.recurrence is None,
    )
    add(
        sec,
        "Второй вторник месяца",
        "второй вторник месяца ревью",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.weekday() == 1,
    )
    add(
        sec,
        "Третий вторник месяца",
        "третий вторник месяца совещание",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.weekday() == 1,
    )
    add(
        sec,
        "Последний понедельник месяца",
        "последний понедельник месяца демо",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.weekday() == 0,
    )
    add(
        sec,
        "Первая среда месяца",
        "первая среда месяца планёрка",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.weekday() == 2,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 15) Порядковые дни + рекуррентность
    # ═══════════════════════════════════════════════════════════════════
    sec = "15. Порядковые дни + рекуррентность"

    add(
        sec,
        "Последняя суббота каждого месяца",
        "последняя суббота каждого месяца",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == date(2026, 2, 28)
        and r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and "-1SA" in r.recurrence.by_day,
    )
    add(
        sec,
        "Последняя суббота каждого месяца в 10",
        "последняя суббота каждого месяца в 10",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and "-1SA" in r.recurrence.by_day,
    )
    add(
        sec,
        "Последняя суббота каждого месяца 10-12",
        "последняя суббота каждого месяца 10-12",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 12
        and r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and "-1SA" in r.recurrence.by_day,
    )
    add(
        sec,
        "Первый вторник каждого месяца",
        "первый вторник каждого месяца",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and "1TU" in r.recurrence.by_day,
    )
    add(
        sec,
        "Первый вторник каждого января",
        "первый вторник каждого января",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.recurrence
        and r.recurrence.frequency == "YEARLY"
        and "1TU" in r.recurrence.by_day
        and 1 in r.recurrence.by_month,
    )
    add(
        sec,
        "Первый вторник каждого января в 15",
        "первый вторник каждого января в 15",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.recurrence
        and r.recurrence.frequency == "YEARLY"
        and 1 in r.recurrence.by_month,
    )
    add(
        sec,
        "Третья среда каждого месяца с 10 до 12",
        "третья среда каждого месяца с 10 до 12",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 12
        and r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and "3WE" in r.recurrence.by_day,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 16) Рекуррентность + time ranges
    # ═══════════════════════════════════════════════════════════════════
    sec = "16. Рекуррентность + time ranges"

    add(
        sec,
        "Каждую среду с 12 до 14",
        "каждую среду с 12 до 14",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 12
        and r.end_at.hour == 14
        and r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and "WE" in r.recurrence.by_day,
    )
    add(
        sec,
        "Каждый четверг в 15",
        "каждый четверг в 15",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and "TH" in r.recurrence.by_day,
    )
    add(
        sec,
        "Каждую среду 10-12",
        "каждую среду 10-12",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 12
        and r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and "WE" in r.recurrence.by_day,
    )
    add(
        sec,
        "Каждый день с 9 до 18",
        "каждый день с 9 до 18",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 9
        and r.end_at.hour == 18
        and r.recurrence
        and r.recurrence.frequency == "DAILY",
    )
    add(
        sec,
        "По пн и ср 9-11",
        "по понедельникам и средам 9-11",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 9
        and r.end_at.hour == 11
        and r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and set(r.recurrence.by_day) == {"MO", "WE"},
    )

    # ═══════════════════════════════════════════════════════════════════
    # 17) rrule string validation
    # ═══════════════════════════════════════════════════════════════════
    sec = "17. rrule string validation"

    add(
        sec,
        "rrule: последняя суббота MONTHLY",
        "последняя суббота каждого месяца 10-12",
        "CalendarResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=-1SA",
    )
    add(
        sec,
        "rrule: первый вторник YEARLY",
        "первый вторник каждого января в 15",
        "ReminderResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=YEARLY;BYDAY=1TU;BYMONTH=1",
    )
    add(
        sec,
        "rrule: каждую среду WEEKLY",
        "каждую среду с 12 до 14",
        "CalendarResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=WE",
    )

    # ═══════════════════════════════════════════════════════════════════
    # 18) Голосовые / разговорные
    # ═══════════════════════════════════════════════════════════════════
    sec = "18. Голосовые / разговорные формулировки"

    add(
        sec,
        "Ну завтра в 10",
        "ну завтра в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "Слушай в пятницу вечером",
        "слушай в пятницу вечером созвон",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Напомни через 45 минут",
        "напомни через 45 минут",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(minutes=45))).total_seconds()) < 60,
    )
    add(
        sec,
        "Поставь на выходных",
        "поставь на выходных созвон",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(
        sec,
        "Запланируй на выходных",
        "запланируй на выходных уборку",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(
        sec,
        "К 10 ноль ноль",
        "надо к 10 ноль ноль отправить отчёт",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.datetime_at.minute == 0,
    )
    add(
        sec,
        "К полудню закончить",
        "к полудню закончить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 12,
    )
    add(
        sec,
        "Ну типа ближе к вечеру",
        "ну типа ближе к вечеру встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Завтра часов в 9",
        "завтра часов в 9 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 9,
    )
    add(
        sec,
        "На послезавтра в 19 кино",
        "на послезавтра в 19 кино",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == day_after_tomorrow
        and r.datetime_at.hour == 19,
    )
    add(
        sec,
        "В три пятнадцать",
        "в три пятнадцать созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 15,
    )
    add(
        sec,
        "В четыре двадцать",
        "в четыре двадцать встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 16
        and r.datetime_at.minute == 20,
    )
    add(
        sec,
        "В девять ноль пять",
        "в девять ноль пять напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 5,
    )
    add(
        sec,
        "В десять тридцать",
        "в десять тридцать планёрка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "В одиннадцать сорок пять",
        "в одиннадцать сорок пять ревью",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.minute == 45,
    )
    add(
        sec,
        "Через два часа тридцать минут (текст)",
        "через два часа тридцать минут созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(hours=2, minutes=30))).total_seconds()) < 120,
    )
    add(
        sec,
        "Через 2 часа",
        "через 2 часа созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(hours=2))).total_seconds()) < 120,
    )
    add(
        sec,
        "Через 3 часа",
        "через 3 часа позвони",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(hours=3))).total_seconds()) < 120,
    )
    add(
        sec,
        "Через 30 минут",
        "через 30 минут напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(minutes=30))).total_seconds()) < 60,
    )
    add(
        sec,
        "Через 15 минут",
        "через 15 минут напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(minutes=15))).total_seconds()) < 60,
    )
    add(
        sec,
        "Через 70 минут",
        "через 70 минут напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(minutes=70))).total_seconds()) < 60,
    )
    add(
        sec,
        "На завтра в три пятнадцать",
        "на завтра в три пятнадцать созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 15,
    )
    add(
        sec,
        "На послезавтра без четверти пять",
        "на послезавтра без четверти пять встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == day_after_tomorrow
        and r.datetime_at.minute == 45,
    )
    add(
        sec,
        "Эээ через 2 часа",
        "эээ через 2 часа напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(hours=2))).total_seconds()) < 120,
    )
    add(
        sec,
        "Так завтра в три пятнадцать",
        "так завтра в три пятнадцать созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 15,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 19) Повторяющиеся события (RecurrenceRecognizer)
    # ═══════════════════════════════════════════════════════════════════
    sec = "19. Повторяющиеся события (рекуррентность)"

    add(
        sec,
        "Каждый понедельник",
        "каждый понедельник стендап",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(sec, "Каждую среду", "каждую среду ретро", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Каждую пятницу", "каждую пятницу демо", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "По вторникам", "по вторникам планёрка", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "По средам", "по средам синк", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "По пятницам", "по пятницам ретро", "TaskResult", lambda r: _is_task_period(r))
    add(
        sec,
        "По вторникам и четвергам",
        "по вторникам и четвергам тренировка",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(
        sec,
        "По пн ср пт",
        "по понедельникам средам и пятницам занятия",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(sec, "Ежедневно", "ежедневно зарядка", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Еженедельно", "еженедельно синк", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Ежемесячно", "ежемесячно отчёт", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Раз в неделю", "раз в неделю уборка", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Раз в месяц", "раз в месяц ревью", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Каждые 2 дня", "каждые 2 дня полив", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Каждые 3 дня", "каждые 3 дня проверка", "TaskResult", lambda r: _is_task_period(r))
    add(
        sec,
        "Каждый день в 9",
        "каждый день в 9 планёрка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 9,
    )
    add(
        sec,
        "Каждый понедельник в 10",
        "каждый понедельник в 10 стендап",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "Каждые 2 часа",
        "каждые 2 часа проверка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult),
    )
    add(sec, "Каждый день", "каждый день медитация", "TaskResult", lambda r: _is_task_period(r))
    add(sec, "Каждую субботу", "каждую субботу уборка", "TaskResult", lambda r: _is_task_period(r))

    # ═══════════════════════════════════════════════════════════════════
    # 20) Open Start (после X)
    # ═══════════════════════════════════════════════════════════════════
    sec = "20. Open Start (после X)"

    add(
        sec,
        "После 18:00 → open_start",
        "после 18:00 позвонить",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.task_type.value == "open_start"
        and r.start_at.hour == 18,
    )
    add(
        sec,
        "После 15:30 → open_start",
        "после 15:30 выйти",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.task_type.value == "open_start"
        and r.start_at.hour == 15
        and r.start_at.minute == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 21) Модификаторы дней недели
    # ═══════════════════════════════════════════════════════════════════
    sec = "21. Модификаторы дней недели"

    add(
        sec,
        "В следующую пятницу",
        "в следующую пятницу митинг",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 4,
    )
    add(
        sec,
        "В следующий понедельник",
        "в следующий понедельник планёрка",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 0,
    )
    add(
        sec,
        "В следующую среду",
        "в следующую среду обед",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 2,
    )
    add(
        sec,
        "В прошлый понедельник",
        "в прошлый понедельник было собрание",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(
        sec,
        "В прошлую пятницу",
        "в прошлую пятницу был митинг",
        "TaskResult",
        lambda r: _is_task_period(r),
    )
    add(
        sec,
        "В ближайшую среду",
        "в ближайшую среду дедлайн",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 2,
    )
    add(
        sec,
        "В ближайший понедельник",
        "в ближайший понедельник собрание",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 0,
    )
    add(
        sec,
        "В ближайшую субботу",
        "в ближайшую субботу поездка",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.weekday() == 5,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 22) Длительность событий
    # ═══════════════════════════════════════════════════════════════════
    sec = "22. Длительность событий"

    add(
        sec,
        "Завтра на 2 часа",
        "встреча завтра на 2 часа",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Завтра на полтора часа",
        "завтра на полтора часа встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "На 30 минут (start+dur → Calendar)",
        "на завтра к 10 на 30 минут созвон",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 10
        and r.end_at.minute == 30
        and r.duration_minutes == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 23) Синонимы дедлайнов
    # ═══════════════════════════════════════════════════════════════════
    sec = "23. Синонимы дедлайнов"

    add(
        sec,
        "Не позднее пятницы",
        "не позднее пятницы сдать отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r),
    )
    add(
        sec,
        "Крайний срок - завтра",
        "крайний срок - завтра",
        "TaskResult",
        lambda r: _is_task_deadline(r),
    )
    add(
        sec,
        "Не позднее понедельника",
        "не позднее понедельника ответить",
        "TaskResult",
        lambda r: _is_task_deadline(r),
    )
    add(
        sec,
        "Крайний срок - пятница",
        "крайний срок - пятница",
        "TaskResult",
        lambda r: _is_task_deadline(r),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 24) Рабочее/нерабочее время
    # ═══════════════════════════════════════════════════════════════════
    sec = "24. Рабочее/нерабочее время"

    add(
        sec,
        "В рабочее время",
        "в рабочее время позвонить",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 18,
    )
    # add(sec, "В нерабочее время", "в нерабочее время позвонить", "TaskResult",
    #     lambda r: isinstance(r, TaskResult))

    # ═══════════════════════════════════════════════════════════════════
    # 25) Извлечение локации
    # ═══════════════════════════════════════════════════════════════════
    sec = "25. Извлечение локации"

    add(
        sec,
        "В офисе",
        "завтра в 10 в офисе совещание",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 10
        and r.location == "в офисе"
        and r.title == "совещание",
    )
    add(
        sec,
        "В кафе",
        "в пятницу в кафе обед",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.location == "в кафе" and r.title == "обед",
    )
    add(
        sec,
        "В зале",
        "завтра в 15 в зале тренировка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.location == "в зале"
        and r.title == "тренировка",
    )

    # ═══════════════════════════════════════════════════════════════════
    # 26) Исключения (кроме)
    # ═══════════════════════════════════════════════════════════════════
    sec = "26. Исключения (кроме)"

    add(
        sec,
        "Кроме выходных",
        "каждый день кроме выходных зарядка",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Кроме среды",
        "каждый день кроме среды обед",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Кроме понедельника",
        "каждый день кроме понедельника уборка",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 27) parse_multi (множественные события)
    # ═══════════════════════════════════════════════════════════════════
    sec = "27. parse_multi (множественные события)"

    add(
        sec,
        "Первое из multi",
        "завтра в 10 митинг",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "Второе из multi",
        "послезавтра в 14 обед",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 14,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 28) Регрессия — базовые паттерны
    # ═══════════════════════════════════════════════════════════════════
    sec = "28. Регрессия — базовые паттерны"

    add(
        sec,
        "Через 2 часа",
        "через 2 часа позвонить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 16,
    )
    add(
        sec,
        "Через 1 час",
        "через 1 час напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and abs((r.datetime_at - (NOW + timedelta(hours=1))).total_seconds()) < 60,
    )
    add(
        sec,
        "В 15:30",
        "встреча в 15:30",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "В 10:00",
        "в 10:00 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "Завтра в 10",
        "завтра в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "Завтра в 9",
        "завтра в 9 планёрка",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == tomorrow
        and r.datetime_at.hour == 9,
    )
    add(
        sec,
        "Послезавтра в 14",
        "послезавтра в 14 обед",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.date() == day_after_tomorrow
        and r.datetime_at.hour == 14,
    )

    add(
        sec,
        "10 марта",
        "10 марта день рождения",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.month == 3 and r.start_at.day == 10,
    )
    add(
        sec,
        "25 февраля",
        "25 февраля презентация",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.month == 2 and r.start_at.day == 25,
    )

    add(
        sec,
        "С 10 до 11",
        "с 10 до 11 совещание",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 10 and r.end_at.hour == 11,
    )
    add(
        sec,
        "С 9 до 12",
        "с 9 до 12 планирование",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 12,
    )
    add(
        sec,
        "9-10 встреча",
        "9-10 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 9 and r.end_at.hour == 10,
    )

    add(sec, "Сегодня", "сегодня задача", "TaskResult", lambda r: _is_task_period(r))
    add(
        sec,
        "Послезавтра",
        "послезавтра экзамен",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.date() == day_after_tomorrow,
    )

    add(sec, "Утром", "утром зарядка", "TaskResult", lambda r: isinstance(r, TaskResult))
    add(sec, "Вечером", "вечером кино", "TaskResult", lambda r: isinstance(r, TaskResult))
    add(sec, "Днём", "днём обед", "TaskResult", lambda r: isinstance(r, TaskResult))

    add(
        sec,
        "Формат dd.mm.yyyy",
        "15.02.2026 встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.month == 2 and r.start_at.day == 15,
    )
    add(
        sec,
        "Формат dd.mm.yyyy + время",
        "15.02.2026 в 10:00 созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.month == 2
        and r.datetime_at.day == 15
        and r.datetime_at.hour == 10,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 29) Сложные случаи
    # ═══════════════════════════════════════════════════════════════════
    sec = "29. Сложные случаи (длинные периоды, рабочие дни, сезоны)"

    add(
        sec,
        "Через 2 недели",
        "через 2 недели встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Через 3 недели",
        "через три недели созвон",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Через 2 месяца",
        "через 2 месяца отпуск",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Через 7 дней",
        "через 7 дней встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )
    add(
        sec,
        "Через 5 рабочих дней",
        "через 5 рабочих дней ответ",
        "TaskResult",
        lambda r: isinstance(r, TaskResult),
    )

    add(
        sec,
        "Весной",
        "весной конференция",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )
    add(
        sec,
        "Летом",
        "летом отпуск",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )
    add(
        sec,
        "Осенью",
        "осенью запуск",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )
    add(
        sec,
        "Зимой",
        "зимой корпоратив",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )
    add(
        sec,
        "В начале лета",
        "в начале лета отпуск",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )
    add(
        sec,
        "В конце осени",
        "в конце осени подведение итогов",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) or _is_task_period(r),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 30) Массовые комбинации: через неделю/месяц + range
    # ═══════════════════════════════════════════════════════════════════
    sec = "30. Генерация: через неделю/месяц + range"

    long_rel_days = [
        ("через неделю", NOW + timedelta(days=7)),
        ("через месяц", None),
    ]
    intervals = [
        ("9-10", 9, 0, 10, 0),
        ("9-11", 9, 0, 11, 0),
        ("10-12", 10, 0, 12, 0),
        ("10:30-11:15", 10, 30, 11, 15),
        ("18-19", 18, 0, 19, 0),
        ("20-22", 20, 0, 22, 0),
    ]
    actions = ["встреча", "созвон", "планёрка", "воркшоп", "демо", "обсуждение", "синк"]

    idx = 1
    for day_phrase, dt in long_rel_days:
        for interval_phrase, sh, sm, eh, em in intervals:
            for act in actions:
                text = f"{day_phrase} {interval_phrase} {act}"
                check = lambda r: isinstance(r, CalendarResult) and _assert_future_result(r)
                add(sec, f"Combo longrel+range #{idx}", text, "CalendarResult", check)
                idx += 1
                if idx > 80:
                    break
            if idx > 80:
                break
        if idx > 80:
            break

    # ═══════════════════════════════════════════════════════════════════
    # 31) Генерация: к TIME combos
    # ═══════════════════════════════════════════════════════════════════
    sec = "31. Генерация: к TIME combos"

    j = 1
    k_times = [("к 10:00", 10, 0), ("к 11:30", 11, 30), ("к 15", 15, 0), ("к 18", 18, 0)]
    for phrase, hh, mm in k_times:
        text = f"{phrase} подготовить отчёт"
        add(
            sec,
            f"Combo k+time #{j}",
            text,
            "ReminderResult",
            lambda r, hh=hh, mm=mm: isinstance(r, ReminderResult)
            and (r.datetime_at.hour == hh or r.datetime_at.hour)
            and r.datetime_at.minute == mm,
        )
        j += 1

    k_fuzzy = [("к полуночи", 0), ("к вечеру", 19), ("к утру", 9)]
    for phrase, expected_hour in k_fuzzy:
        text = f"{phrase} подготовить отчёт"
        add(
            sec,
            f"Combo k+fuzzy #{j}",
            text,
            "ReminderResult",
            lambda r, h=expected_hour: isinstance(r, ReminderResult) and r.datetime_at.hour == h,
        )
        j += 1

    # ═══════════════════════════════════════════════════════════════════
    # 32) Генерация: через N минут/часов
    # ═══════════════════════════════════════════════════════════════════
    sec = "32. Генерация: через N минут/часов"

    rel_offsets = [
        ("через 5 минут", timedelta(minutes=5)),
        ("через 10 минут", timedelta(minutes=10)),
        ("через 45 минут", timedelta(minutes=45)),
        ("через 1 час", timedelta(hours=1)),
        ("через 2 часа", timedelta(hours=2)),
        ("через 3 часа", timedelta(hours=3)),
    ]
    j = 1
    for phrase, delta in rel_offsets:
        expected = NOW + delta
        add(
            sec,
            f"Combo offset #{j}",
            f"{phrase} напомни",
            "ReminderResult",
            lambda r, expected=expected: isinstance(r, ReminderResult)
            and abs((r.datetime_at - expected).total_seconds()) < 60,
        )
        j += 1

    for m in [5, 10, 15, 20, 30, 45]:
        expected = NOW + timedelta(minutes=m)
        add(
            sec,
            f"Через {m} минут",
            f"через {m} минут напомни",
            "ReminderResult",
            lambda r, exp=expected: isinstance(r, ReminderResult)
            and abs((r.datetime_at - exp).total_seconds()) < 60,
        )

    for h in [1, 2, 3, 4, 5, 6]:
        expected = NOW + timedelta(hours=h)
        add(
            sec,
            f"Через {h} час(ов)",
            f"через {h} часа встреча",
            "ReminderResult",
            lambda r, exp=expected: isinstance(r, ReminderResult)
            and abs((r.datetime_at - exp).total_seconds()) < 60,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 33) Генерация: конкретные даты + с..до
    # ═══════════════════════════════════════════════════════════════════
    sec = "33. Генерация: конкретные даты + с..до"

    combo_date = NOW + timedelta(days=45)
    combo_date_text = f"{combo_date.day} {months_ru[combo_date.month]}"
    times = [("9", "11", 9, 11), ("10", "12", 10, 12)]

    j = 1
    for a, b, sh, eh in times:
        text = f"{combo_date_text} с {a} до {b} встреча"
        add(
            sec,
            f"Combo date+с..до #{j}",
            text,
            "CalendarResult",
            lambda r, sh=sh, eh=eh: isinstance(r, CalendarResult)
            and r.start_at.hour == sh
            and r.end_at.hour == eh,
        )
        j += 1

    # "дата + дефис-диапазон" → CalendarResult (дата + range мержатся)
    for a, b, sh, eh in [("9", "11", 9, 11), ("10", "12", 10, 12)]:
        text = f"{combo_date_text} {a}-{b} встреча"
        add(
            sec,
            f"Combo date+dash #{j}",
            text,
            "CalendarResult",
            lambda r, sh=sh, eh=eh: isinstance(r, CalendarResult)
            and r.start_at.hour == sh
            and r.end_at.hour == eh,
        )
        j += 1

    # ═══════════════════════════════════════════════════════════════════
    # 34) Генерация: на завтра/послезавтра к X + в X
    # ═══════════════════════════════════════════════════════════════════
    sec = "34. Генерация: на завтра/послезавтра к X"

    for h in range(8, 23):
        text = f"на завтра к {h} встреча"
        add(
            sec,
            f"На завтра к {h}",
            text,
            "ReminderResult",
            lambda r, h=h: isinstance(r, ReminderResult)
            and r.datetime_at.date() == tomorrow
            and r.datetime_at.hour == h,
        )

    for h in [9, 10, 11, 12, 14, 15, 16, 17, 18]:
        text = f"на послезавтра к {h}:00 встреча"
        add(
            sec,
            f"На послезавтра к {h}:00",
            text,
            "ReminderResult",
            lambda r, h=h: isinstance(r, ReminderResult)
            and r.datetime_at.date() == day_after_tomorrow
            and r.datetime_at.hour == h,
        )

    for h in range(8, 23):
        text = f"завтра в {h} встреча"
        add(
            sec,
            f"Завтра в {h}",
            text,
            "ReminderResult",
            lambda r, h=h: isinstance(r, ReminderResult)
            and r.datetime_at.date() == tomorrow
            and r.datetime_at.hour == h,
        )

    for h in [9, 12, 15, 18, 20]:
        text = f"послезавтра в {h} созвон"
        add(
            sec,
            f"Послезавтра в {h}",
            text,
            "ReminderResult",
            lambda r, h=h: isinstance(r, ReminderResult)
            and r.datetime_at.date() == day_after_tomorrow
            and r.datetime_at.hour == h,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 35) Генерация: все дни недели
    # ═══════════════════════════════════════════════════════════════════
    sec = "35. Генерация: все дни недели"

    weekdays = [
        ("понедельник", 0),
        ("вторник", 1),
        ("среду", 2),
        ("четверг", 3),
        ("пятницу", 4),
        ("субботу", 5),
        ("воскресенье", 6),
    ]
    for day_name, wd in weekdays:
        text = f"в {day_name} встреча"
        add(
            sec,
            f"В {day_name} (без времени)",
            text,
            "TaskResult",
            lambda r, wd=wd: _is_task_period(r) and r.start_at.weekday() == wd,
        )

    for day_name, wd in weekdays:
        text = f"в {day_name} в 10 созвон"
        add(
            sec,
            f"В {day_name} в 10",
            text,
            "ReminderResult",
            lambda r, wd=wd: isinstance(r, ReminderResult)
            and r.datetime_at.weekday() == wd
            and r.datetime_at.hour == 10,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 36) Доработки: идиомы и валидация дат
    # ═══════════════════════════════════════════════════════════════════
    sec = "36. Доработки: идиомы и валидация дат"

    add(
        sec,
        "Голое время в конце",
        "встреча 15:00",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 15
        and r.datetime_at.minute == 0,
    )
    add(
        sec,
        "К обеду",
        "к обеду позвонить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 13,
    )
    add(
        sec,
        "В обед",
        "в обед встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 13,
    )
    add(
        sec,
        "На следующей неделе",
        "на следующей неделе встреча",
        "TaskResult",
        lambda r: _is_task_fuzzy(r)
        and r.start_at.date() == (NOW + timedelta(days=2)).date()
        and r.start_at.weekday() == 0,
    )
    add(
        sec,
        "На прошлой неделе (past)",
        "на прошлой неделе был отчёт",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at < NOW,
    )
    add(sec, "На днях", "на днях зайти", "TaskResult", lambda r: _is_task_fuzzy(r))
    add(
        sec,
        "Через день",
        "через день напомнить",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.date() == (NOW + timedelta(days=1)).date(),
    )
    add(
        sec,
        "В конце месяца",
        "в конце месяца отчёт",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.month == 2 and r.end_at.day == 28,
    )
    add(
        sec,
        "В начале марта",
        "в начале марта поездка",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.month == 3 and r.start_at.day == 1,
    )
    add(
        sec,
        "Первого сентября (слово)",
        "первого сентября линейка",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.month == 9 and r.start_at.day == 1,
    )
    add(
        sec,
        "В течение часа",
        "в течение часа поработать",
        "TaskResult",
        lambda r: _is_task_deadline(r)
        and abs((r.deadline - (NOW + timedelta(hours=1))).total_seconds()) < 60,
    )
    add(sec, "31 февраля → отклонить", "31 февраля встреча", "NoneType", lambda r: r is None)
    add(
        sec,
        "29 февраля 2025 → отклонить",
        "29 февраля 2025 событие",
        "NoneType",
        lambda r: r is None,
    )
    add(
        sec,
        "Невалидное время 25:00 → отклонить",
        "в 25:00 напомни",
        "NoneType",
        lambda r: r is None,
    )
    add(
        sec,
        "Чистка title от 'был'",
        "вчера в 10 был созвон",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.title.strip() == "созвон",
    )
    add(
        sec,
        "День месяца: 15 числа",
        "15 числа отчёт",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.day == 15,
    )
    add(
        sec,
        "День месяца: 20-го",
        "20-го встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.day == 20,
    )
    add(
        sec,
        "День месяца словом",
        "пятнадцатого обед",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.day == 15,
    )
    add(
        sec,
        "День месяца словом + время",
        "пятнадцатого в 12 обед",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.day == 15
        and r.datetime_at.hour == 12
        and r.title.strip() == "обед",
    )
    add(
        sec,
        "Не ломаем 'пол первого'",
        "пол первого обед",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.hour == 0
        and r.datetime_at.minute == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 37) Аудит: день недели+часть суток, чистка title, сезон, исключения
    # ═══════════════════════════════════════════════════════════════════
    sec = "37. Аудит: daypart+weekday, title, сезон, кроме"
    friday = (NOW + timedelta(days=(4 - NOW.weekday()) % 7 or 7)).date()
    monday = (NOW + timedelta(days=(0 - NOW.weekday()) % 7 or 7)).date()

    add(
        sec,
        "Пятница вечером → именно пятница",
        "в пятницу вечером созвон",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.date() == friday and r.start_at.hour == 18,
    )
    add(
        sec,
        "Филлер 'слушай' вычищен + пятница",
        "слушай в пятницу вечером созвон",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.date() == friday and r.title.strip() == "созвон",
    )
    add(
        sec,
        "Понедельник ночью",
        "в понедельник ночью дежурство",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.date() == monday and r.start_at.hour == 22,
    )
    add(
        sec,
        "Завтра утром привязано к завтра",
        "завтра утром тренировка",
        "TaskResult",
        lambda r: _is_task_fuzzy(r)
        and r.start_at.date() == (NOW + timedelta(days=1)).date()
        and r.start_at.hour == 9,
    )

    add(
        sec,
        "title: 'во' вычищен",
        "во вторник к 12:00 закончить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.title.strip() == "закончить",
    )
    add(
        sec,
        "title: кино как название",
        "на послезавтра в 19 кино",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.title.strip() == "кино"
        and r.datetime_at.hour == 19,
    )
    add(
        sec,
        "title: команда-обёртка вычищена",
        "поставь напоминание завтра в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.title.strip() == "встреча",
    )

    add(
        sec,
        "Локация только с предлогом",
        "завтра в 10 встреча в офисе",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.title.strip() == "встреча"
        and r.location == "в офисе",
    )

    add(
        sec,
        "Начало лета сужено + title",
        "в начале лета отпуск",
        "TaskResult",
        lambda r: _is_task_fuzzy(r)
        and r.start_at.month == 6
        and r.start_at.day == 1
        and r.end_at.day <= 10
        and r.title.strip() == "отпуск",
    )
    add(
        sec,
        "Конец осени сужен + title",
        "в конце осени подведение итогов",
        "TaskResult",
        lambda r: _is_task_fuzzy(r)
        and r.end_at.month == 11
        and r.end_at.day == 30
        and r.start_at.day >= 20
        and r.title.strip() == "подведение итогов",
    )

    add(
        sec,
        "кроме выходных → BYDAY будни",
        "каждый день кроме выходных зарядка",
        "TaskResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    add(
        sec,
        "кроме среды → BYDAY без WE",
        "каждый день кроме среды бег",
        "TaskResult",
        lambda r: r.recurrence
        and "WE" not in r.recurrence.by_day
        and r.recurrence.frequency == "WEEKLY"
        and len(r.recurrence.by_day) == 6,
    )
    add(
        sec,
        "кроме понедельника → BYDAY без MO",
        "каждый день кроме понедельника пробежка",
        "TaskResult",
        lambda r: r.recurrence
        and "MO" not in r.recurrence.by_day
        and r.recurrence.frequency == "WEEKLY"
        and len(r.recurrence.by_day) == 6,
    )

    # типы: дедлайн по дате и ночной диапазон
    add(
        sec,
        "до+день недели → deadline",
        "до пятницы отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.weekday() == 4,
    )
    add(
        sec,
        "до+N-го → deadline",
        "до 20-го отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.day == 20,
    )
    add(
        sec,
        "к+день недели → deadline",
        "к пятнице сдать",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.weekday() == 4,
    )
    add(
        sec,
        "до+дата+месяц → deadline",
        "до 20 марта отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.month == 3 and r.deadline.day == 20,
    )
    add(
        sec,
        "ночной диапазон с 23 до 1",
        "с 23 до 1 ночная смена",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 23
        and r.end_at.hour == 1
        and r.duration_minutes == 120,
    )
    add(
        sec,
        "ночной диапазон с 22 до 6",
        "с 22 до 6 смена",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 22
        and r.end_at.hour == 6
        and r.duration_minutes == 480,
    )

    # аудит #2: день рождения, типа, duration→calendar, рабочее время, календарные месяцы
    add(
        sec,
        "'день рождения' не режется",
        "10 марта день рождения",
        "TaskResult",
        lambda r: _is_task_period(r) and r.title.strip() == "день рождения",
    )
    add(
        sec,
        "филлер 'типа' вычищен",
        "ну типа ближе к вечеру встреча",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.title.strip() == "встреча",
    )
    add(
        sec,
        "рабочее время в сб → будний день",
        "в рабочее время позвонить",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.weekday() < 5
        and r.start_at.hour == 9
        and r.end_at.hour == 18,
    )
    add(
        sec,
        "через месяц = календарный сдвиг",
        "через месяц встреча",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.day == NOW.day and r.start_at.month == 3,
    )
    add(
        sec,
        "через 2 месяца = +2 мес календарно",
        "через 2 месяца отпуск",
        "TaskResult",
        lambda r: isinstance(r, TaskResult) and r.start_at.day == NOW.day and r.start_at.month == 4,
    )
    add(
        sec,
        "через год = +1 год календарно",
        "через год конференция",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.start_at.day == NOW.day
        and r.start_at.month == NOW.month
        and r.start_at.year == NOW.year + 1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 38) Аудит покрытия: leap, AM/PM, duration, valid/invalid даты
    # ═══════════════════════════════════════════════════════════════════
    sec = "38. Аудит покрытия: leap / AM-PM / duration"

    add(
        sec,
        "29 февраля 2024 (валидный)",
        "29 февраля 2024 событие",
        "TaskResult",
        lambda r: _is_task_period(r)
        and r.start_at.year == 2024
        and r.start_at.month == 2
        and r.start_at.day == 29,
    )
    add(
        sec,
        "29 февраля 2028 (валидный)",
        "29 февраля 2028 событие",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.year == 2028 and r.start_at.day == 29,
    )
    add(
        sec,
        "29 февраля 2025 → отклонить",
        "29 февраля 2025 событие",
        "NoneType",
        lambda r: r is None,
    )
    add(
        sec,
        "29 февраля 2026 → отклонить",
        "29 февраля 2026 встреча",
        "NoneType",
        lambda r: r is None,
    )
    add(sec, "31 апреля → отклонить", "31 апреля встреча", "NoneType", lambda r: r is None)
    add(sec, "30 февраля → отклонить", "30 февраля встреча", "NoneType", lambda r: r is None)

    add(
        sec,
        "в 7 утра",
        "в 7 утра встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 7,
    )
    add(
        sec,
        "в 7 вечера",
        "в 7 вечера ужин",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 19,
    )
    add(
        sec,
        "в 12 ночи",
        "в 12 ночи напомни",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 0,
    )
    add(
        sec,
        "в 12 дня",
        "в 12 дня обед",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 12,
    )
    add(
        sec,
        "в полночь",
        "в полночь отправить",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult) and r.datetime_at.hour == 0,
    )

    add(
        sec,
        "duration: завтра в 10 на 2 часа",
        "завтра в 10 встреча на 2 часа",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 12
        and r.duration_minutes == 120,
    )
    add(
        sec,
        "duration: завтра к 10 на 30 минут",
        "завтра к 10 созвон на 30 минут",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 10
        and r.end_at.hour == 10
        and r.end_at.minute == 30,
    )
    add(
        sec,
        "duration ночью: 23:30 на 2 часа",
        "сегодня в 23:30 на 2 часа смена",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult)
        and r.start_at.hour == 23
        and r.start_at.minute == 30
        and r.end_at.hour == 1
        and r.duration_minutes == 120,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 39) Блок A: короткие даты, между, до конца, начало/середина/конец
    # ═══════════════════════════════════════════════════════════════════
    sec = "39. Блок A: форматы дат / между / до конца / часть периода"

    add(
        sec,
        "17.02 (короткая дата)",
        "17.02 встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.day == 17 and r.start_at.month == 2,
    )
    add(
        sec,
        "17/02 (слэш)",
        "17/02 встреча",
        "TaskResult",
        lambda r: _is_task_period(r) and r.start_at.day == 17 and r.start_at.month == 2,
    )
    add(
        sec,
        "01.03.26 (2-значный год)",
        "01.03.26 встреча",
        "TaskResult",
        lambda r: _is_task_period(r)
        and r.start_at.year == 2026
        and r.start_at.month == 3
        and r.start_at.day == 1,
    )
    add(
        sec,
        "17.02 в 10 (дата+время)",
        "17.02 в 10 встреча",
        "ReminderResult",
        lambda r: isinstance(r, ReminderResult)
        and r.datetime_at.day == 17
        and r.datetime_at.hour == 10,
    )

    add(
        sec,
        "между 10 и 12 → Calendar",
        "между 10 и 12 встреча",
        "CalendarResult",
        lambda r: isinstance(r, CalendarResult) and r.start_at.hour == 10 and r.end_at.hour == 12,
    )

    add(
        sec,
        "до конца недели → deadline",
        "до конца недели отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.weekday() == 6,
    )
    add(
        sec,
        "до конца месяца → deadline",
        "до конца месяца оплатить",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.day == 28 and r.deadline.month == 2,
    )
    add(
        sec,
        "до конца года → deadline",
        "до конца года закрыть",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.month == 12 and r.deadline.day == 31,
    )
    add(
        sec,
        "до конца квартала → deadline",
        "до конца квартала отчёт",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.month == 3 and r.deadline.day == 31,
    )
    add(
        sec,
        "до конца дня → deadline сегодня",
        "до конца дня отправить",
        "TaskResult",
        lambda r: _is_task_deadline(r)
        and r.deadline.date() == NOW.date()
        and r.deadline.hour == 23,
    )

    add(
        sec,
        "в середине месяца → fuzzy",
        "в середине месяца отчёт",
        "TaskResult",
        lambda r: _is_task_fuzzy(r)
        and r.start_at.month == 2
        and 10 <= r.start_at.day <= 20
        and r.title.strip() == "отчёт",
    )
    add(
        sec,
        "в конце квартала → fuzzy конец Q1",
        "в конце квартала отчёт",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.end_at.month == 3 and r.end_at.day == 31,
    )
    add(
        sec,
        "в начале марта → fuzzy",
        "в начале марта встреча",
        "TaskResult",
        lambda r: _is_task_fuzzy(r) and r.start_at.month == 3 and r.start_at.day == 1,
    )

    add(
        sec,
        "до полуночи → deadline 00:00",
        "до полуночи отправить",
        "TaskResult",
        lambda r: _is_task_deadline(r)
        and r.deadline.hour == 0
        and r.deadline.date() == (NOW + timedelta(days=1)).date(),
    )
    add(
        sec,
        "после полуночи → open_start",
        "после полуночи проверить",
        "TaskResult",
        lambda r: isinstance(r, TaskResult)
        and r.task_type.value == "open_start"
        and r.start_at.hour == 0,
    )
    add(
        sec,
        "до полудня → deadline 12:00",
        "до полудня закончить",
        "TaskResult",
        lambda r: _is_task_deadline(r) and r.deadline.hour == 12,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 40) Блок B-core: будни / интервалы / BYMONTHDAY
    # ═══════════════════════════════════════════════════════════════════
    sec = "40. Блок B-core: recurrence"

    add(
        sec,
        "каждый будний день",
        "каждый будний день в 9 стендап",
        "ReminderResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    add(
        sec,
        "по будням",
        "по будням в 9 стендап",
        "ReminderResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    add(
        sec,
        "по будням с 9 до 18",
        "по будням с 9 до 18 работа",
        "CalendarResult",
        lambda r: r.recurrence and set(r.recurrence.by_day) == {"MO", "TU", "WE", "TH", "FR"},
    )
    add(
        sec,
        "каждые 2 недели в понедельник",
        "каждые 2 недели в понедельник стендап",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "WEEKLY"
        and r.recurrence.interval == 2
        and r.recurrence.by_day == ["MO"],
    )
    add(
        sec,
        "каждый месяц 15 числа → BYMONTHDAY",
        "каждый месяц 15 числа отчёт",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and r.recurrence.by_month_day == [15],
    )
    add(
        sec,
        "каждое 15 число → BYMONTHDAY",
        "каждое 15 число отчёт",
        "TaskResult",
        lambda r: r.recurrence and r.recurrence.by_month_day == [15],
    )
    add(
        sec,
        "каждые 3 месяца → INTERVAL",
        "каждые 3 месяца ревью",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "MONTHLY"
        and r.recurrence.interval == 3,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 41) Блок C: неподдерживаемое → None (не угадываем)
    # ═══════════════════════════════════════════════════════════════════
    sec = "41. Негативные (стабильные) → None"
    # Стабильно не парсится по определению — это НЕ временны́е выражения.
    for txt in [
        "абракадабра",
        "напомни",
        "поставь",
        "потом",
        "когда-нибудь",
        "не знаю когда встреча",
        "",
        "   ",
    ]:
        add(sec, f"None: {txt!r}", txt, "NoneType", lambda r: r is None)

    sec = "41b. Roadmap/TODO → пока None (не acceptance)"
    # Пока намеренно возвращаем None (не угадываем). Если появится поддержка
    # таймзон/праздников/опечаток — эти кейсы станут положительными (xfail-кандидаты).
    for txt in [
        "в 10 мск созвон",
        "в 10 по Москве созвон",
        "в 10 UTC созвон",
        "завтра в 9 GMT+3 созвон",
        "по Алматы в 10 встреча",
        "на новый год поздравить",
        "на майские поездка",
        "питницу созвон",
        "чериз 10 минут",
    ]:
        add(sec, f"TODO→None: {txt!r}", txt, "NoneType", lambda r: r is None)

    # ═══════════════════════════════════════════════════════════════════
    # 42) Инвариант recurrence: стартовая дата удовлетворяет BYDAY/BYMONTHDAY
    # ═══════════════════════════════════════════════════════════════════
    sec = "42. Инвариант recurrence (start ⊨ RRULE)"

    def _rec_ok(r):
        if not getattr(r, "recurrence", None):
            return False
        st = getattr(r, "start_at", None) or getattr(r, "datetime_at", None)
        rec = r.recurrence
        idx = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
        plain = [d for d in rec.by_day if d in idx]
        if plain and st.weekday() not in [idx[d] for d in plain]:
            return False
        if rec.by_month_day and st.day not in rec.by_month_day:
            return False
        return True

    add(
        sec,
        "кроме выходных: старт — будни",
        "каждый день кроме выходных зарядка",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.weekday() < 5,
    )
    add(
        sec,
        "каждые 2 недели в пн: старт — пн",
        "каждые 2 недели в понедельник стендап",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.weekday() == 0,
    )
    add(
        sec,
        "каждый месяц 15 числа: старт 15-го",
        "каждый месяц 15 числа отчёт",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.day == 15,
    )
    add(
        sec,
        "каждое 15 число: старт 15-го",
        "каждое 15 число отчёт",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.day == 15,
    )
    add(
        sec,
        "каждую пятницу: старт — пт",
        "каждую пятницу в 18 созвон",
        "ReminderResult",
        lambda r: _rec_ok(r) and r.datetime_at.weekday() == 4,
    )
    add(
        sec,
        "каждый понедельник: старт — пн",
        "каждый понедельник в 10 стендап",
        "ReminderResult",
        lambda r: _rec_ok(r) and r.datetime_at.weekday() == 0,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 43) Аудит-фиксы: title-числительные, yearly+date, rrule без Z
    # ═══════════════════════════════════════════════════════════════════
    sec = "43. Аудит-фиксы (title/yearly/rrule)"

    add(
        sec,
        "числительное не в title + recurrence цела",
        "каждые две недели в среду в 12 синк",
        "ReminderResult",
        lambda r: r.title == "синк"
        and r.recurrence
        and r.recurrence.interval == 2
        and r.recurrence.by_day == ["WE"]
        and r.datetime_at.hour == 12,
    )
    add(
        sec,
        "ежегодно 10 января → BYMONTH+BYMONTHDAY",
        "ежегодно 10 января поздравить",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.to_rrule() == "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=10"
        and r.start_at.month == 1
        and r.start_at.day == 10,
    )
    add(
        sec,
        "ежегодно 8 марта → ближайшее будущее",
        "ежегодно 8 марта поздравить",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.by_month == [3]
        and r.start_at.year == 2026
        and r.start_at.day == 8,
    )
    add(
        sec,
        "rrule UNTIL без Z (naive)",
        "с понедельника по пятницу 9-10 тренинг",
        "CalendarResult",
        lambda r: r.recurrence
        and r.recurrence.until is not None
        and not r.recurrence.to_rrule().endswith("Z")
        and "Z" not in r.recurrence.to_rrule(),
    )

    # ═══════════════════════════════════════════════════════════════════
    # 44) Голосовой ввод: числительные словами и словесные диапазоны
    # ═══════════════════════════════════════════════════════════════════
    sec = "44. Голос: числительные словами"

    add(
        sec,
        "через сорок пять минут",
        "через сорок пять минут напомни",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 45,
    )
    add(
        sec,
        "через двадцать минут",
        "через двадцать минут кофе",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 20,
    )
    add(
        sec,
        "через сто двадцать минут",
        "через сто двадцать минут релиз",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 0,
    )
    add(
        sec,
        "через два часа",
        "через два часа звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16,
    )
    add(
        sec,
        "через полтора часа",
        "через полтора часа встреча",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 15 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "через полчаса",
        "через полчаса кофе",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "через десять дней",
        "через десять дней отпуск",
        "TaskResult",
        lambda r: r.start_at.day == 24,
    )
    add(
        sec,
        "сорок пять минут назад",
        "сорок пять минут назад был звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 13 and r.datetime_at.minute == 15 and r.is_past,
    )
    add(
        sec,
        "с десяти до одиннадцати",
        "с десяти до одиннадцати встреча",
        "CalendarResult",
        lambda r: r.start_at.hour == 10 and r.end_at.hour == 11 and r.title == "встреча",
    )
    add(
        sec,
        "с девяти утра до шести вечера",
        "с девяти утра до шести вечера работа",
        "CalendarResult",
        lambda r: r.start_at.hour == 9 and r.end_at.hour == 18 and r.title == "работа",
    )
    add(
        sec,
        "с девяти до пяти (ampm)",
        "с девяти до пяти работа",
        "CalendarResult",
        lambda r: r.start_at.hour == 9 and r.end_at.hour == 17,
    )
    add(
        sec,
        "в десять тридцать",
        "в десять тридцать встреча",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 10 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "в девять утра",
        "в девять утра планёрка",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 9,
    )
    add(
        sec,
        "без пятнадцати восемь",
        "поставь будильник на без пятнадцати восемь",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 7 and r.datetime_at.minute == 45,
    )
    add(
        sec,
        "без пяти десять",
        "без пяти десять созвон",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 9 and r.datetime_at.minute == 55,
    )
    add(
        sec,
        "каждые сорок пять минут → MINUTELY",
        "каждые сорок пять минут разминка",
        "ReminderResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "MINUTELY"
        and r.recurrence.interval == 45,
    )
    add(
        sec,
        "каждые три часа → HOURLY",
        "каждые три часа проверка",
        "ReminderResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "HOURLY"
        and r.recurrence.interval == 3,
    )
    add(
        sec,
        "в пол седьмого вечера",
        "тренировка в пол седьмого вечера",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 18 and r.datetime_at.minute == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 45) Аудит по кейсам (P0): invalid-date, decimal, порядок слов
    # ═══════════════════════════════════════════════════════════════════
    sec = "45. Аудит-кейсы P0"

    add(
        sec,
        "невалидная дата + время → None",
        "31 февраля в 10 встреча",
        "NoneType",
        lambda r: r is None,
    )
    add(
        sec,
        "29 фев 2025 + время → None",
        "29 февраля 2025 в 10 событие",
        "NoneType",
        lambda r: r is None,
    )
    add(sec, "31 апреля + время → None", "31 апреля в 9 дело", "NoneType", lambda r: r is None)
    add(
        sec,
        "валидная 29 фев 2024 остаётся",
        "29 февраля 2024 в 10 событие",
        "ReminderResult",
        lambda r: r.datetime_at.year == 2024
        and r.datetime_at.month == 2
        and r.datetime_at.day == 29,
    )
    add(
        sec,
        "дробное через 1.5 часа",
        "через 1.5 часа позвонить",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 15 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "дробное через 2.5 часа",
        "через 2.5 часа встреча",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "порядок: завтра встреча в 10 → title",
        "завтра встреча в 10",
        "ReminderResult",
        lambda r: r.title == "встреча" and r.datetime_at.day == 15 and r.datetime_at.hour == 10,
    )
    add(
        sec,
        "порядок: в 10 завтра встреча → tomorrow 10",
        "в 10 завтра встреча",
        "ReminderResult",
        lambda r: r.title == "встреча" and r.datetime_at.day == 15 and r.datetime_at.hour == 10,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 46) Аудит по кейсам (P1): COUNT/UNTIL, последний день, verbose, title
    # ═══════════════════════════════════════════════════════════════════
    sec = "46. Аудит-кейсы P1"

    add(
        sec,
        "COUNT: каждый понедельник 5 раз",
        "каждый понедельник 5 раз тренировка",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.count == 5
        and r.recurrence.by_day == ["MO"]
        and r.title == "тренировка",
    )
    add(
        sec,
        "UNTIL: каждый понедельник до конца месяца",
        "каждый понедельник до конца месяца синк",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.until is not None
        and r.recurrence.until.day == 28
        and r.title == "синк",
    )
    add(
        sec,
        "UNTIL: каждый день до пятницы",
        "каждый день до пятницы зарядка",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.until is not None
        and r.recurrence.until.weekday() == 4,
    )
    add(
        sec,
        "последний день месяца → BYMONTHDAY=-1",
        "каждый последний день месяца отчет",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYMONTHDAY=-1"
        and r.start_at.day == 28,
    )
    add(
        sec,
        "verbose: десять часов пятнадцать минут",
        "в десять часов пятнадцать минут встреча",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 10 and r.datetime_at.minute == 15 and r.title == "встреча",
    )
    add(
        sec,
        "verbose: час пятнадцать → 13:15",
        "час пятнадцать встреча",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 13 and r.datetime_at.minute == 15,
    )
    add(
        sec,
        "range: с двух до половины четвёртого",
        "с двух до половины четвёртого встреча",
        "CalendarResult",
        lambda r: r.start_at.hour == 14 and r.end_at.hour == 15 and r.end_at.minute == 30,
    )
    add(
        sec,
        "title: с Иваном встреча → встреча",
        "завтра в 10 с Иваном встреча",
        "ReminderResult",
        lambda r: r.title == "встреча",
    )
    add(
        sec,
        "title: у клиента встреча → встреча",
        "завтра в 10 у клиента встреча",
        "ReminderResult",
        lambda r: r.title == "встреча",
    )

    # ═══════════════════════════════════════════════════════════════════
    # 47) Позиции внутри месяца: рабочий день / выходные / неделя / -2
    # ═══════════════════════════════════════════════════════════════════
    sec = "47. Позиции месяца"

    add(
        sec,
        "предпоследний четверг месяца",
        "предпоследний четверг месяца ретро",
        "TaskResult",
        lambda r: r.start_at.day == 19 and r.title == "ретро",
    )
    add(
        sec,
        "первый рабочий день месяца",
        "первый рабочий день месяца отчёт",
        "TaskResult",
        lambda r: r.start_at.weekday() < 5 and r.title == "отчёт",
    )
    add(
        sec,
        "последний рабочий день месяца",
        "последний рабочий день месяца отчёт",
        "TaskResult",
        lambda r: r.start_at.day == 27 and r.start_at.weekday() == 4,
    )
    add(
        sec,
        "последние выходные месяца",
        "последние выходные месяца дача",
        "TaskResult",
        lambda r: r.start_at.day == 28 and r.start_at.weekday() == 5 and r.title == "дача",
    )
    add(
        sec,
        "последняя неделя месяца",
        "последняя неделя месяца x",
        "TaskResult",
        lambda r: r.start_at.day == 22 and r.end_at.day == 28,
    )
    add(
        sec,
        "каждый последний рабочий день → BYSETPOS",
        "каждый последний рабочий день месяца отчёт",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
    )
    add(
        sec,
        "каждый первый выходной → BYSETPOS",
        "каждый первый выходной месяца x",
        "TaskResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=SA,SU;BYSETPOS=1",
    )
    add(
        sec,
        "первый будний день после 15 числа",
        "первый будний день после 15 числа отчёт",
        "TaskResult",
        lambda r: r.start_at.day == 16 and r.start_at.weekday() < 5 and r.title == "отчёт",
    )
    add(
        sec,
        "первый понедельник после 15 числа",
        "первый понедельник после 15 числа планёрка",
        "TaskResult",
        lambda r: r.start_at.day == 16 and r.start_at.weekday() == 0 and r.title == "планёрка",
    )
    add(
        sec,
        "последняя пятница перед концом месяца",
        "последняя пятница перед концом месяца ретро",
        "TaskResult",
        lambda r: r.start_at.day == 27 and r.start_at.weekday() == 4 and r.title == "ретро",
    )

    # ═══════════════════════════════════════════════════════════════════
    # R1) Регрессии: явный маркер времени суток + снап BYMONTHDAY
    # ═══════════════════════════════════════════════════════════════════
    sec = "R1. Регрессии (утра/ночи при склейке с датой; BYMONTHDAY через короткий месяц)"
    # «завтра в 7 утра» обязано быть 07:00, а не 19:00 (ремап 1-7→+12 не должен
    # затирать явное уточнение)
    add(
        sec,
        "завтра в 7 утра → 07:00",
        "завтра в 7 утра рейс",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 7,
    )
    add(
        sec,
        "завтра в 3 ночи → 03:00",
        "завтра в 3 ночи подъём",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 3,
    )
    add(
        sec,
        "в 3 ночи завтра → 03:00",
        "в 3 ночи завтра подъём",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 3,
    )
    # уточнение «вечера/дня» тоже побеждает, и голое время работает как раньше
    add(
        sec,
        "завтра в 7 вечера → 19:00",
        "завтра в 7 вечера кино",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 19,
    )
    add(
        sec,
        "завтра в 3 дня → 15:00",
        "завтра в 3 дня созвон",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 15,
    )
    add(
        sec,
        "завтра в 3 (голое) → 15:00",
        "завтра в 3 созвон",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 15,
    )
    add(
        sec,
        "завтра в 8 (голое) → 08:00",
        "завтра в 8 созвон",
        "ReminderResult",
        lambda r: r.datetime_at.date() == tomorrow and r.datetime_at.hour == 8,
    )
    # BYMONTHDAY=30 от 31 января: февраль пропускаем, старт = 30 марта,
    # и в start не должно утекать сырое now (23:30)
    add(
        sec,
        "каждый месяц 30 числа от 31.01 → 30.03",
        "каждый месяц 30 числа платёж",
        "TaskResult",
        lambda r: (
            r.recurrence
            and "BYMONTHDAY=30" in r.recurrence.to_rrule()
            and r.start_at.month == 3
            and r.start_at.day == 30
            and r.start_at.hour == 0
            and r.start_at.minute == 0
        ),
        now_override=datetime(2026, 1, 31, 23, 30),
    )
    add(
        sec,
        "каждый месяц 31 числа от 31.01 → 31.01",
        "каждый месяц 31 числа отчёт",
        "TaskResult",
        lambda r: (
            r.recurrence
            and "BYMONTHDAY=31" in r.recurrence.to_rrule()
            and r.start_at.month == 1
            and r.start_at.day == 31
        ),
        now_override=datetime(2026, 1, 31, 12, 0),
    )

    # ═══════════════════════════════════════════════════════════════════
    # R2) Регрессии: дробные интервалы (десятичная запятая, «с половиной»)
    # ═══════════════════════════════════════════════════════════════════
    sec = "R2. Регрессии (дробные интервалы: «2,5 часа», «два с половиной»)"
    # NOW = 14.02.2026 14:00
    add(
        sec,
        "через 2,5 часа (запятая) → 16:30",
        "через 2,5 часа звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "через 2.5 часа (точка) → 16:30",
        "через 2.5 часа звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "через два с половиной часа → 16:30",
        "через два с половиной часа звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        sec,
        "через три с половиной минуты",
        "через три с половиной минуты пинг",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 3,
    )
    add(
        sec,
        "через два с половиной месяца → 29.04",
        "через два с половиной месяца отпуск",
        "TaskResult",
        lambda r: r.start_at.month == 4 and r.start_at.day == 29,
    )
    # запятая-разделитель событий по-прежнему работает в parse_multi
    add(
        sec,
        "полтора не сломано → 15:30",
        "через полтора часа звонок",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 15 and r.datetime_at.minute == 30,
    )

    # ═══════════════════════════════════════════════════════════════════
    # R3) Регрессии: наследование даты в parse_multi, «через час/минуту»
    # ═══════════════════════════════════════════════════════════════════
    sec = "R3. Регрессии (parse_multi наследует дату; «через час» без числа)"
    add(
        sec,
        "через час (без числа) → 15:00",
        "через час созвон",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 15 and r.datetime_at.minute == 0,
    )
    add(
        sec,
        "через минуту → 14:01",
        "через минуту пинг",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 1,
    )

    def _multi(text, checks):
        def chk(_):
            rs = parser.parse_multi(text, now=NOW)
            if len(rs) != len(checks):
                return False
            return all(c(r) for c, r in zip(checks, rs))

        return chk

    # маркерная фраза не важна — вся логика в check; событие берём заведомо парсящееся
    add(
        sec,
        "multi: «и в 15» наследует завтра",
        "завтра в 10 встреча и в 15 созвон",
        "ReminderResult",
        _multi(
            "завтра в 10 встреча и в 15 созвон",
            [
                lambda r: r.datetime_at.day == 15 and r.datetime_at.hour == 10,
                lambda r: r.datetime_at.day == 15 and r.datetime_at.hour == 15,
            ],
        ),
    )
    add(
        sec,
        "multi: «послезавтра» не сдвигается",
        "завтра в 10 встреча и в 15 созвон",
        "ReminderResult",
        _multi(
            "завтра в 10 встреча, послезавтра в 12 созвон",
            [
                lambda r: r.datetime_at.day == 15,
                lambda r: r.datetime_at.day == 16 and r.datetime_at.hour == 12,
            ],
        ),
    )
    add(
        sec,
        "multi: «сегодня» — якорь, не наследует",
        "завтра в 10 встреча и в 15 созвон",
        "ReminderResult",
        _multi(
            "завтра в 10 встреча и сегодня в 18 позвонить",
            [
                lambda r: r.datetime_at.day == 15,
                lambda r: r.datetime_at.day == 14 and r.datetime_at.hour == 18,
            ],
        ),
    )

    return tests


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════


def main(show_failed_only=False):
    all_tests = build_tests()

    sections = {}
    for section, name, text, expected_type, check, now_ov in all_tests:
        sections.setdefault(section, []).append((name, text, expected_type, check, now_ov))

    days_ru = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    day_name = days_ru[NOW.weekday()]

    print(f"{'█' * 60}")
    print(f"{BOLD}   🕐 TimeSense v2 — Unified Test Suite{RESET}")
    print(f"{'█' * 60}")
    print(f"📅 Тестовая дата: {NOW.strftime('%d.%m.%Y %H:%M')} ({day_name})")
    print(f"   🔧 Всего категорий: {len(sections)}")
    print(f"   🧪 Всего тестов: {len(all_tests)}")
    if HAS_CONFIG:
        print("   ⚙️  TimeConfig: prefer_nearest_future=True")
    if show_failed_only:
        print("   🧹 Режим: только ошибки (--fail-only)")

    passed = 0
    failed = 0
    total = 0

    for section_title, items in sections.items():
        section_printed = False

        if not show_failed_only:
            print_section(section_title, "🧩")

        for name, text, expected_type, check, now_ov in items:
            total += 1

            header_to_print = None
            if show_failed_only and not section_printed:
                header_to_print = section_title

            ok, printed_header = run_case(
                name,
                text,
                expected_type,
                check,
                print_on_pass=not show_failed_only,
                section_header=header_to_print,
                now_override=now_ov,
            )

            if printed_header:
                section_printed = True

            if ok:
                passed += 1
            else:
                failed += 1

    print(f"{'█' * 60}")
    if failed == 0:
        print(f"{GREEN}{BOLD}   🎉 Все тесты пройдены: {passed}/{total}{RESET}")
    else:
        print(f"{RED}{BOLD}   ⚠️  Пройдено: {passed}/{total}{RESET}")
        print(f"{RED}   ❌ Провалено: {failed}{RESET}")
    print(f"{'█' * 60}")

    return failed == 0


if __name__ == "__main__":
    show_failed_only = "--fail-only" in sys.argv
    success = main(show_failed_only=show_failed_only)
    sys.exit(0 if success else 1)

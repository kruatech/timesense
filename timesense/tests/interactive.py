"""
TimeSense Interactive Console

Запуск:
    python interactive.py

Инструкция:
- Вводите текст с датой/временем (например: "завтра в 10 встреча")
- Нажмите Enter, чтобы увидеть результат
- Нажмите Ctrl+C, чтобы выйти
"""

import sys
import os

# Добавляем путь к корню проекта, чтобы импортировать timesense
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from timesense import TimeSenseParser, CalendarResult, ReminderResult, TaskResult

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Можно задать дату через переменную окружения для тестов (как в test_fixes)
# Например: TEST_NOW="2026-01-13 14:00" python interactive.py
_now_override = os.environ.get("TEST_NOW")
if _now_override:
    NOW = datetime.strptime(_now_override, "%Y-%m-%d %H:%M")
else:
    NOW = datetime.now().replace(second=0, microsecond=0)

parser = TimeSenseParser()

# Colors for terminal
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ═══════════════════════════════════════════════════════════════════
# HELPERS (Функции форматирования из test_fixes)
# ═══════════════════════════════════════════════════════════════════


def format_result_type(result):
    """Форматирует тип результата с эмодзи"""
    if isinstance(result, CalendarResult):
        return "📅 CalendarResult"
    if isinstance(result, ReminderResult):
        return "⏰ ReminderResult"
    if isinstance(result, TaskResult):
        return f"📋 TaskResult ({result.task_type.value})"
    return f"❔ {type(result).__name__}"


def format_datetime_info(result):
    """Форматирует информацию о дате/времени"""
    lines = []

    if isinstance(result, CalendarResult):
        start = result.start_at.strftime("%d.%m.%Y %H:%M")
        end = result.end_at.strftime("%d.%m.%Y %H:%M")
        duration = result.duration_minutes
        lines.append(f"   📍 Период: {start} → {end}")
        lines.append(f"   ⏱️  Длительность: {duration} мин")

    elif isinstance(result, ReminderResult):
        dt = result.datetime_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"   📍 Время: {dt}")

    elif isinstance(result, TaskResult):
        if result.task_type.value == "deadline" and result.deadline:
            dl = result.deadline.strftime("%d.%m.%Y %H:%M")
            lines.append(f"   🎯 Дедлайн: {dl}")
        elif result.start_at and result.end_at:
            start = result.start_at.strftime("%d.%m.%Y %H:%M")
            end = result.end_at.strftime("%d.%m.%Y %H:%M")
            lines.append(f"   📍 Период: {start} → {end}")

    return lines


def extract_task_text(result, original_text: str) -> str:
    """Извлекает текст задачи/события для печати."""
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

    s = (original_text or "").strip()
    if not s:
        return ""

    months = {
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
    }
    stop = {
        "в",
        "с",
        "до",
        "по",
        "к",
        "на",
        "сегодня",
        "завтра",
        "послезавтра",
        "через",
        "час",
        "часа",
        "часов",
        "минут",
        "минуты",
        "минуту",
        "день",
        "дня",
        "дней",
        "неделю",
        "недели",
        "недель",
        "месяц",
        "месяца",
        "месяцев",
        "следующей",
        "следующем",
        "следующая",
        "следующий",
        "неделе",
        "неделя",
        "месяце",
        "месяц",
        "выходных",
        "будни",
        "буднях",
        "утром",
        "днём",
        "днем",
        "вечером",
        "ночью",
        "вроде",
        "типа",
        "ну",
        "ээ",
        "эээ",
        "короче",
        "слушай",
        "так",
    }

    def looks_like_time(tok: str) -> bool:
        if ":" in tok:
            a, _, b = tok.partition(":")
            return a.isdigit() and b.isdigit()
        return False

    def looks_like_range(tok: str) -> bool:
        for sep in ("-", "–", "—"):
            if sep in tok:
                a, _, b = tok.partition(sep)
                return a.isdigit() and b.isdigit()
        return False

    def looks_like_date(tok: str) -> bool:
        if "." in tok:
            parts = tok.split(".")
            if len(parts) in (2, 3) and all(p.isdigit() for p in parts if p):
                return True
        return False

    raw_tokens = s.replace(",", " ").replace(";", " ").replace(":", ":").split()
    kept = []
    for t in raw_tokens:
        tok = t.strip(".!?()[]{}\"'" "«»")
        low = tok.lower()

        if not tok:
            continue
        if low in months:
            continue
        if low in stop:
            continue
        if looks_like_time(tok) or looks_like_range(tok) or looks_like_date(tok):
            continue
        if low.isdigit():
            continue

        kept.append(tok)

    if not kept:
        return s

    core = " ".join(kept).strip()
    return core[:1].upper() + core[1:] if core else core


# ═══════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════


def main():
    print(f"{'█' * 60}")
    print(f"{BOLD}   🕐 TimeSense Interactive Console{RESET}")
    print(f"{'█' * 60}")
    print(f"📅 Текущее время: {NOW.strftime('%d.%m.%Y %H:%M')}")
    print(f"{DIM}Введите фразу с датой или временем (Ctrl+C для выхода){RESET}")
    print()

    try:
        while True:
            try:
                text = input(f"{CYAN}Введите текст:{RESET} ")
                if not text.strip():
                    continue

                result = parser.parse(text, now=NOW)
                if result is None:
                    print(f"   {DIM}Type:{RESET}  ❓ не распознано\n")
                    continue

                print(f"   {DIM}Type:{RESET}  {format_result_type(result)}")

                for line in format_datetime_info(result):
                    print(line)

                # строка с задачей/событием
                task_text = extract_task_text(result, text)
                if task_text:
                    print(f"   📝 {task_text}")

                print()  # Пустая строка для читаемости

            except Exception as e:
                print(f"{RED}⚠️ Ошибка парсинга: {e}{RESET}\n")

    except KeyboardInterrupt:
        print(f"\n\n{GREEN}👋 До свидания!{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()

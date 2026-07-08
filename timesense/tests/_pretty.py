# -*- coding: utf-8 -*-
"""Читаемый вывод для стресс-наборов (RU/EN). Только форматирование."""
from __future__ import annotations
from datetime import datetime
from typing import Any

_L = {
    "ru": {
        "reminder": "⏰ Напоминание", "task": "📋 Задача", "calendar": "📆 Событие",
        "deadline": "⏳ Дедлайн", "recurring": "🔁 Повтор", "empty": "⭕ Пусто",
        "period": "период", "past": "🕓 прошлое", "query": "📝 Запрос", "result": "🎯 Действие", "type_w": "Тип", "result_w": "Действие", "when_w": "Когда", "place_w": "Место",
        "start": "старт", "until_word": "до", "min": "мин", "expected": "(ожидаемо)",
        "now": "Сейчас", "lang": "Русский", "lang_name": "🌐 Русский",
        "cases": "Кейсов", "mode": "Режим", "mode_all": "все", "mode_errors": "только ошибки",
        "by_type": "По типам", "of_them": "Из них",
        "ranges": "диапазонов", "recurs": "повторов", "deadlines": "дедлайнов", "locs": "локаций",
        "passed": "Пройдено", "errors_w": "Ошибок", "crashes": "Крашей",
        "every": "каждые", "every1": "каждый", "week_u": "нед", "interval_pfx": "каждые",
        "multi": "🔗 Составные фразы (несколько задач в одной строке)", "multi_found": "найдено", "multi_exp": "ожидалось ≥", "multi_err": "ОШИБКА",
    },
    "en": {
        "reminder": "⏰ Reminder", "task": "📋 Task", "calendar": "📆 Event",
        "deadline": "⏳ Deadline", "recurring": "🔁 Recurring", "empty": "⭕ Empty",
        "period": "period", "past": "🕓 past", "query": "📝 Query", "result": "🎯 Action", "type_w": "Type", "result_w": "Action", "when_w": "When", "place_w": "Place",
        "start": "start", "until_word": "by", "min": "min", "expected": "(expected)",
        "now": "Now", "lang": "English", "lang_name": "🌐 English",
        "cases": "Cases", "mode": "Mode", "mode_all": "all", "mode_errors": "errors only",
        "by_type": "By type", "of_them": "Of them",
        "ranges": "ranges", "recurs": "recurring", "deadlines": "deadlines", "locs": "locations",
        "passed": "Passed", "errors_w": "Errors", "crashes": "Crashes",
        "every": "every", "every1": "every", "week_u": "wk", "interval_pfx": "every",
        "multi": "🔗 Compound phrases (several tasks in one line)", "multi_found": "found", "multi_exp": "expected ≥", "multi_err": "ERROR",
    },
}

_WD_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_RRULE_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_WD_FULL_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_WD_FULL_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fmt_dt(iso: str | None, with_time: bool = True) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return d.strftime("%Y-%m-%d %H:%M") if with_time else d.strftime("%Y-%m-%d")


def _has_time(iso: str | None) -> bool:
    if not iso:
        return False
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return False
    return (d.hour, d.minute) != (0, 0)


def _rrule_human(rec: dict, lang: str) -> str:
    L = _L[lang]
    wd = _WD_RU if lang == "ru" else _WD_EN
    parts = []
    freq = rec.get("frequency", "")
    interval = rec.get("interval", 1) or 1
    fmap = {
        "DAILY": ("каждый день" if lang == "ru" else "daily"),
        "WEEKLY": ("каждую неделю" if lang == "ru" else "weekly"),
        "MONTHLY": ("каждый месяц" if lang == "ru" else "monthly"),
        "YEARLY": ("каждый год" if lang == "ru" else "yearly"),
    }
    if interval > 1:
        unit = {"WEEKLY": L["week_u"], "DAILY": "дн" if lang == "ru" else "d",
                "MONTHLY": "мес" if lang == "ru" else "mo",
                "YEARLY": "г" if lang == "ru" else "y"}.get(freq, "")
        parts.append(f"{L['interval_pfx']} {interval} {unit}")
    else:
        parts.append(fmap.get(freq, freq.lower()))
    by_day = rec.get("by_day") or []
    days_simple = [d for d in by_day if d in _RRULE_WD]
    if days_simple:
        parts.append(", ".join(wd[_RRULE_WD[d]] for d in days_simple))
    elif by_day:  # позиционные (1TU и т.п.)
        parts.append(", ".join(by_day))
    bmd = rec.get("by_month_day")
    if bmd:
        parts.append((f"{bmd[0]} числа" if lang == "ru" else f"day {bmd[0]}"))
    return " · ".join(parts)


def _kind(data: dict | None) -> str:
    """reminder|task|calendar|deadline|recurring|empty (+ period-флаг снаружи)."""
    if data is None:
        return "empty"
    if data.get("recurrence"):
        return "recurring"
    if data.get("task_type") == "deadline" or data.get("deadline"):
        return "deadline"
    cls = (data.get("type") or "").lower()
    if cls == "calendar":
        return "calendar"
    if cls == "task":
        return "task"
    return "reminder"


def _when(data: dict, kind: str, lang: str) -> str:
    L = _L[lang]
    if kind == "deadline":
        dl = data.get("deadline") or data.get("start")
        return f"{L['until_word']} {_fmt_dt(dl)}"
    if kind == "recurring":
        start = data.get("datetime") or data.get("start")
        rule = _rrule_human(data["recurrence"], lang)
        return f"{L['start']} {_fmt_dt(start)} · {rule}"
    start = data.get("datetime") or data.get("start")
    end = data.get("end")
    # событие с интервалом времени
    if data.get("duration_minutes") and end and _has_time(start):
        s = _fmt_dt(start)
        e = datetime.fromisoformat(end).strftime("%H:%M")
        return f"{s}–{e} ({data['duration_minutes']} {L['min']})"
    # период (диапазон дат) — «→» только если даты РАЗНЫЕ
    if end and not _has_time(start) and (data.get("task_type") == "period" or data.get("fuzzy")):
        try:
            sd = datetime.fromisoformat(start).date()
            ed = datetime.fromisoformat(end).date()
        except (ValueError, TypeError):
            sd = ed = None
        if sd is not None and sd != ed:
            return f"{_fmt_dt(start, False)} → {_fmt_dt(end, False)}"
        return _fmt_dt(start, False)
    return _fmt_dt(start, with_time=_has_time(start))


def card(row: dict[str, Any], lang: str) -> str:
    L = _L[lang]
    data = row.get("result")
    errors = row.get("errors") or []
    kind = _kind(data)
    mark = "❌" if errors else "✅"
    lines = [f"{mark} {row['id']}"]
    lines.append(f"   {L['query']}:    {row['text']}")
    if data is None:
        empty = L["empty"] + (
            f" {L['expected']}" if "expected_none" in row.get("tags", []) else ""
        )
        icon = empty.split()[0]
        lines.append(f"   {icon} {L['type_w']}:       {empty[len(icon)+1:]}")
        return "\n".join(lines + [f"      ⚠️  {e}" for e in errors])
    # тип (иконка + текст, + приписки период/прошлое)
    label = L[kind]
    if data.get("task_type") == "period" and kind == "task":
        label = f"{L['task']} · {L['period']}"
    if data.get("is_past"):
        label = f"{label} · {L['past']}"
    icon = label.split()[0]
    # ширина текстовой подписи (без иконки) для выравнивания значений
    w = max(len(L["type_w"]), len(L["result_w"]), len(L["when_w"]), len(L["place_w"]))

    def _row(ic, lab, val):
        return f"   {ic} {(lab + ':').ljust(w + 1)}  {val}"
    lines.append(_row(icon, L["type_w"], label[len(icon) + 1:]))
    title = data.get("title") or "—"
    lines.append(_row("🎯", L["result_w"], title))
    lines.append(_row("📅", L["when_w"], _when(data, kind, lang)))
    loc = data.get("location")
    if loc:
        lines.append(_row("📍", L["place_w"], loc))
    for e in errors:
        lines.append(f"      ⚠️  {e}")
    return "\n".join(lines)


def header(snapshot: dict, lang: str, mode_all: bool) -> str:
    L = _L[lang]
    now = datetime.fromisoformat(snapshot["now"])
    wd_full = _WD_FULL_RU if lang == "ru" else _WD_FULL_EN
    dow = wd_full[now.weekday()]
    mode = L["mode_all"] if mode_all else L["mode_errors"]
    bar = "═" * 60
    return (
        f"{bar}\n"
        f"📅 {L['now']}: {now.strftime('%Y-%m-%d %H:%M')} ({dow})   {L['lang_name']}\n"
        f"🧪 {L['cases']}: {snapshot['case_count']}      🧹 {L['mode']}: {mode}"
    )


def summary(snapshot: dict, lang: str) -> str:
    L = _L[lang]
    tc = snapshot["type_counts"]
    tags = snapshot.get("tag_counts", {})
    bar = "═" * 60
    n_reminder = tc.get("ReminderResult", 0)
    n_task = tc.get("TaskResult", 0)
    n_cal = tc.get("CalendarResult", 0)
    n_none = tc.get("None", 0)
    passed = snapshot["case_count"] - len(snapshot["failures"]) - len(snapshot["crashes"])
    lines = [
        bar,
        f"{L['by_type']}:   ⏰ {n_reminder}   📋 {n_task}   📆 {n_cal}   ⭕ {n_none}",
        f"{L['of_them']}:     {L['ranges']} {tags.get('range', 0)} · "
        f"{L['recurs']} {tags.get('recurrence', 0)} · "
        f"{L['deadlines']} {tags.get('deadline', 0)} · "
        f"{L['locs']} {tags.get('location', 0)}",
        f"✅ {L['passed']}: {passed}/{snapshot['case_count']}     "
        f"❌ {L['errors_w']}: {len(snapshot['failures'])}     "
        f"💥 {L['crashes']}: {len(snapshot['crashes'])}",
        bar,
    ]
    return "\n".join(lines)


def _mini(data: dict, lang: str) -> str:
    """Одна задача из составной фразы: иконка + действие + когда."""
    kind = _kind(data)
    label = _L[lang][kind]
    icon = label.split()[0]
    title = data.get("title") or "—"
    when = _when(data, kind, lang)
    return f"{icon} {title:<32} {when}"


def multi_block(multi: list[dict], lang: str) -> str:
    L = _L[lang]
    out = [L["multi"], ""]
    for i, item in enumerate(multi, 1):
        if "error_type" in item:
            out.append(f"❌ multi_{i}   {L['multi_err']}: {item['error_type']}: {item['error']}")
            out.append(f"   {L['query']}:    {item['text']}")
            out.append("")
            continue
        cnt, exp = item["count"], item["expected_min"]
        mark = "✅" if cnt >= exp else "❌"
        out.append(f"{mark} multi_{i} · {L['multi_found']} {cnt} ({L['multi_exp']}{exp})")
        out.append(f"   {L['query']}:    {item['text']}")
        results = item.get("results") or []
        for j, r in enumerate(results):
            if r is None:
                continue
            branch = "└─" if j == len(results) - 1 else "├─"
            out.append(f"   {branch} {_mini(r, lang)}")
        out.append("")
    return "\n".join(out).rstrip()

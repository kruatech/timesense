"""
TimeSense — English locale test runner (human-readable output).

Run (same style as the Russian runner):
    cd <parent_of_timesense>
    python -m timesense.tests.test_en_fixes
    python -m timesense.tests.test_en_fixes --fail-only

Reference NOW = 2026-02-14 14:00 (Saturday). Prints one block per case
(Input / Type / times / recurrence / title) and a final NN/NN summary.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timedelta
from timesense import TimeSenseParser
from timesense.models.event_types import CalendarResult, ReminderResult, TaskResult

NOW = datetime(2026, 2, 14, 14, 0)  # Saturday
parser = TimeSenseParser()

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ── helpers ──────────────────────────────────────────────────────────────
def fmt_type(r):
    if isinstance(r, CalendarResult):
        return "📅 CalendarResult"
    if isinstance(r, ReminderResult):
        return "⏰ ReminderResult"
    if isinstance(r, TaskResult):
        return "📋 TaskResult (%s)" % r.task_type.value
    if r is None:
        return "🚫 None"
    return "❔ %s" % type(r).__name__


def fmt_info(r):
    lines = []
    if isinstance(r, CalendarResult):
        lines.append(
            "   📍 Period: %s → %s"
            % (r.start_at.strftime("%d.%m.%Y %H:%M"), r.end_at.strftime("%d.%m.%Y %H:%M"))
        )
        lines.append("   ⏱️  Duration: %s min" % r.duration_minutes)
    elif isinstance(r, ReminderResult):
        lines.append("   📍 Time: %s" % r.datetime_at.strftime("%d.%m.%Y %H:%M"))
    elif isinstance(r, TaskResult):
        if r.task_type.value == "deadline" and r.deadline:
            lines.append("   🎯 Deadline: %s" % r.deadline.strftime("%d.%m.%Y %H:%M"))
        elif r.start_at and r.end_at:
            lines.append(
                "   📍 Period: %s → %s"
                % (r.start_at.strftime("%d.%m.%Y %H:%M"), r.end_at.strftime("%d.%m.%Y %H:%M"))
            )
    if getattr(r, "recurrence", None):
        lines.append("   🔁 Recurrence: %s" % r.recurrence.to_rrule())
    if getattr(r, "detected_language", None):
        lines.append("   🌐 Language: %s" % r.detected_language)
    if getattr(r, "title", None):
        lines.append("   🧾 %s" % r.title)
    return lines


def is_task(r, kind):
    return isinstance(r, TaskResult) and r.task_type.value == kind


def print_section(title):
    print("═" * 64)
    print("%s  %s%s" % (BOLD + CYAN, title, RESET))
    print("═" * 64)


# ── test table ─────────────────────────────────────────────────────────────
def build_tests():
    T = []

    def add(section, name, text, expected_type, check=None):
        T.append((section, name, text, expected_type, check))

    s = "1. Relative days & weekdays"
    add(
        s,
        "tomorrow at time",
        "tomorrow at 5pm meeting",
        "ReminderResult",
        lambda r: r.datetime_at.day == 15 and r.datetime_at.hour == 17 and r.title == "meeting",
    )
    add(
        s,
        "today at time",
        "today at 9am call",
        "ReminderResult",
        lambda r: r.datetime_at.day == 14 and r.datetime_at.hour == 9,
    )
    add(
        s,
        "tonight → evening",
        "tonight call",
        "TaskResult",
        lambda r: is_task(r, "fuzzy") and r.start_at.hour == 18,
    )
    add(
        s,
        "day after tomorrow",
        "day after tomorrow at noon lunch",
        "ReminderResult",
        lambda r: r.datetime_at.day == 16 and r.datetime_at.hour == 12,
    )
    add(
        s,
        "next Friday",
        "next Friday at 10 sync",
        "ReminderResult",
        lambda r: r.datetime_at.day == 27 and r.datetime_at.hour == 10,
    )  # next = nearest + 7
    add(
        s,
        "this Monday",
        "this Monday at 9 standup",
        "ReminderResult",
        lambda r: r.datetime_at.day == 16,
    )
    add(
        s,
        "last Friday (past)",
        "last Friday review",
        "TaskResult",
        lambda r: is_task(r, "period") and r.start_at.day == 13,
    )
    add(
        s,
        "bare weekday → upcoming",
        "Friday deadline",
        "TaskResult",
        lambda r: is_task(r, "period") and r.start_at.day == 20,
    )

    s = "2. Month-name & numeric dates"
    add(
        s,
        "Mon DD",
        "Feb 17 dentist",
        "TaskResult",
        lambda r: r.start_at.month == 2 and r.start_at.day == 17,
    )
    add(s, "DD Mon", "17 Feb dentist", "TaskResult", lambda r: r.start_at.day == 17)
    add(
        s,
        "Mon DDrd",
        "March 3rd party",
        "TaskResult",
        lambda r: r.start_at.month == 3 and r.start_at.day == 3,
    )
    add(
        s,
        "Mon DD YYYY",
        "Feb 17 2027 conference",
        "TaskResult",
        lambda r: r.start_at.year == 2027 and r.start_at.day == 17,
    )
    add(
        s,
        "US MM/DD",
        "3/17 review",
        "TaskResult",
        lambda r: r.start_at.month == 3 and r.start_at.day == 17,
    )
    add(
        s,
        "ISO + time",
        "2026-02-17 at 10 sync",
        "ReminderResult",
        lambda r: r.datetime_at.day == 17 and r.datetime_at.hour == 10,
    )

    s = "3. Times & AM/PM"
    add(s, "7am", "at 7am workout", "ReminderResult", lambda r: r.datetime_at.hour == 7)
    add(s, "7pm", "at 7pm dinner", "ReminderResult", lambda r: r.datetime_at.hour == 19)
    add(s, "12pm noon", "at 12pm lunch", "ReminderResult", lambda r: r.datetime_at.hour == 12)
    add(s, "12am midnight", "at 12am reminder", "ReminderResult", lambda r: r.datetime_at.hour == 0)
    add(s, "noon", "noon lunch", "ReminderResult", lambda r: r.datetime_at.hour == 12)
    add(s, "midnight", "midnight backup", "ReminderResult", lambda r: r.datetime_at.hour == 0)
    add(s, "24h", "at 17:00 sync", "ReminderResult", lambda r: r.datetime_at.hour == 17)
    add(s, "H:MM am", "9:30am standup", "ReminderResult", lambda r: r.datetime_at.minute == 30)

    s = "4. Relative 'in N units'"
    add(s, "in 2 hours", "in 2 hours call", "ReminderResult", lambda r: r.datetime_at.hour == 16)
    add(
        s,
        "in 30 minutes",
        "in 30 minutes coffee",
        "ReminderResult",
        lambda r: r.datetime_at.minute == 30,
    )
    add(s, "in 3 days", "in 3 days review", "TaskResult", lambda r: r.start_at.day == 17)
    add(s, "in 2 weeks", "in 2 weeks demo", "TaskResult", lambda r: r.start_at.day == 28)

    s = "5. Ranges → Calendar"
    add(
        s,
        "9 to 5 (PM heuristic)",
        "from 9 to 5 work shift",
        "CalendarResult",
        lambda r: r.start_at.hour == 9 and r.end_at.hour == 17,
    )
    add(s, "9am-11am", "9am-11am call", "CalendarResult", lambda r: r.duration_minutes == 120)
    add(
        s,
        "between 10 and 12",
        "between 10 and 12 be available",
        "CalendarResult",
        lambda r: r.start_at.hour == 10 and r.end_at.hour == 12,
    )
    add(
        s,
        "range on date",
        "tomorrow from 9am to 11am workshop",
        "CalendarResult",
        lambda r: r.start_at.day == 15 and r.start_at.hour == 9 and r.end_at.hour == 11,
    )

    s = "6. Recurrence"
    add(
        s,
        "every day",
        "every day at 9am standup",
        "ReminderResult",
        lambda r: r.recurrence.to_rrule() == "FREQ=DAILY",
    )
    add(
        s,
        "every Monday",
        "every Monday at 10 sync",
        "ReminderResult",
        lambda r: r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO",
    )
    add(
        s,
        "every weekday",
        "every weekday at 9 standup",
        "ReminderResult",
        lambda r: r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    add(
        s,
        "on weekdays",
        "on weekdays standup",
        "TaskResult",
        lambda r: r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )
    add(
        s,
        "every 2 weeks on Monday",
        "every 2 weeks on Monday review",
        "TaskResult",
        lambda r: r.recurrence.interval == 2 and r.recurrence.by_day == ["MO"],
    )
    add(
        s,
        "every other week",
        "every other week sync",
        "TaskResult",
        lambda r: r.recurrence.interval == 2,
    )
    add(
        s,
        "every month on 15th",
        "every month on the 15th report",
        "TaskResult",
        lambda r: r.recurrence.by_month_day == [15],
    )
    add(s, "daily", "daily standup", "TaskResult", lambda r: r.recurrence.frequency == "DAILY")

    s = "7. Recurrence modifiers (COUNT / UNTIL / EXCEPT)"
    add(
        s,
        "N times → COUNT",
        "every Monday 5 times gym",
        "TaskResult",
        lambda r: r.recurrence.count == 5 and r.title == "gym",
    )
    add(
        s,
        "until end of March",
        "every Friday until end of March sync",
        "TaskResult",
        lambda r: r.recurrence.until.month == 3
        and r.recurrence.until.day == 31
        and r.title == "sync",
    )
    add(
        s,
        "until <date>",
        "every day until March 20 standup",
        "TaskResult",
        lambda r: r.recurrence.until.day == 20 and r.title == "standup",
    )
    add(
        s,
        "except weekends",
        "every day except weekends workout",
        "TaskResult",
        lambda r: r.recurrence.to_rrule() == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        and r.title == "workout",
    )
    add(
        s,
        "except Sunday",
        "every day except Sunday run",
        "TaskResult",
        lambda r: "SU" not in r.recurrence.by_day
        and len(r.recurrence.by_day) == 6
        and r.title == "run",
    )

    s = "8. Deadlines / duration / dayparts"
    add(
        s,
        "by Friday",
        "by Friday submit report",
        "TaskResult",
        lambda r: is_task(r, "deadline") and r.deadline.day == 20,
    )
    add(
        s,
        "by 5pm",
        "by 5pm finish",
        "TaskResult",
        lambda r: is_task(r, "deadline") and r.deadline.hour == 17,
    )
    add(
        s,
        "by end of month",
        "by end of month pay invoice",
        "TaskResult",
        lambda r: is_task(r, "deadline") and r.deadline.day == 28,
    )
    add(
        s,
        "duration + time",
        "meeting tomorrow at 10 for 2 hours",
        "CalendarResult",
        lambda r: r.start_at.hour == 10 and r.end_at.hour == 12,
    )
    add(
        s,
        "Friday evening",
        "this Friday evening call",
        "TaskResult",
        lambda r: is_task(r, "fuzzy") and r.start_at.day == 20 and r.start_at.hour == 18,
    )

    s = "9. Language routing"
    add(
        s,
        "auto-detect en",
        "meeting tomorrow at 3pm",
        "ReminderResult",
        lambda r: r.detected_language == "en",
    )
    add(
        s,
        "today at 9am → past flagged (#4)",
        "today at 9am call",
        "ReminderResult",
        lambda r: r.datetime_at.day == 14 and r.datetime_at.hour == 9 and r.is_past is True,
    )
    add(
        s,
        "12am reminder keeps title (#9)",
        "at 12am reminder",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 0 and r.title == "reminder",
    )

    # ═══════════════════════════════════════════════════════════════════
    # GENERATIVE SECTIONS (mass combinations) — expectations mirror parser
    # ═══════════════════════════════════════════════════════════════════
    WD_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    RRULE = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    def next_wd(wd):
        # Конвенция: next X = ближайший X (включая сегодня) + неделя (как в RU)
        return NOW + timedelta(days=(wd - NOW.weekday()) % 7 + 7)

    def this_wd(wd):
        return NOW + timedelta(days=(wd - NOW.weekday()) % 7)

    def last_wd(wd):
        return NOW - timedelta(days=((NOW.weekday() - wd) % 7) or 7)

    def bare_wd(wd):
        delta = (wd - NOW.weekday()) % 7
        return NOW + timedelta(days=delta or 7)

    def exp_month(mo, d):
        y = NOW.year
        if datetime(y, mo, d).date() < NOW.date():
            y += 1
        return (y, mo, d)

    # G1) next <weekday> at <H>pm  (7 × 5 = 35)
    s = "G1. next <weekday> at H pm"
    for wd in range(7):
        for h in (1, 2, 3, 4, 5):
            d = next_wd(wd)
            add(
                s,
                "next %s %dpm" % (WD_NAMES[wd], h),
                "next %s at %dpm meeting" % (WD_NAMES[wd], h),
                "ReminderResult",
                lambda r, dd=d, hh=h: r.datetime_at.date() == dd.date()
                and r.datetime_at.hour == hh + 12,
            )

    # G2) next <weekday> at <H>am  (7 × 5 = 35)
    s = "G2. next <weekday> at H am"
    for wd in range(7):
        for h in (7, 8, 9, 10, 11):
            d = next_wd(wd)
            add(
                s,
                "next %s %dam" % (WD_NAMES[wd], h),
                "next %s at %dam standup" % (WD_NAMES[wd], h),
                "ReminderResult",
                lambda r, dd=d, hh=h: r.datetime_at.date() == dd.date()
                and r.datetime_at.hour == hh,
            )

    # G3) this/last <weekday> at 10  (7 × 2 = 14)
    s = "G3. this/last <weekday> at 10"
    for wd in range(7):
        dt_this = this_wd(wd)
        add(
            s,
            "this %s" % WD_NAMES[wd],
            "this %s at 10 sync" % WD_NAMES[wd],
            "ReminderResult",
            lambda r, dd=dt_this: r.datetime_at.date() == dd.date() and r.datetime_at.hour == 10,
        )
        dt_last = last_wd(wd)
        add(
            s,
            "last %s" % WD_NAMES[wd],
            "last %s at 10 review" % WD_NAMES[wd],
            "ReminderResult",
            lambda r, dd=dt_last: r.datetime_at.date() == dd.date() and r.datetime_at.hour == 10,
        )

    # G4) bare <weekday> (upcoming, all-day task)  (7)
    s = "G4. bare <weekday> → upcoming"
    for wd in range(7):
        d = bare_wd(wd)
        add(
            s,
            "%s task" % WD_NAMES[wd],
            "%s deadline task" % WD_NAMES[wd],
            "TaskResult",
            lambda r, dd=d: is_task(r, "period") and r.start_at.date() == dd.date(),
        )

    # G5) month-name × day  (12 × 3 = 36)
    s = "G5. <Month> <day>"
    MON_ABBR = [
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    for mo in range(1, 13):
        for d in (5, 15, 25):
            ey, em, ed = exp_month(mo, d)
            add(
                s,
                "%s %d" % (MON_ABBR[mo], d),
                "%s %d report" % (MON_ABBR[mo], d),
                "TaskResult",
                lambda r, Y=ey, M=em, D=ed: is_task(r, "period")
                and r.start_at.year == Y
                and r.start_at.month == M
                and r.start_at.day == D,
            )

    # G6) at H am / pm (hour resolution)  (11 + 11 = 22)
    s = "G6. at H am/pm"
    for h in range(1, 12):
        add(
            s,
            "at %dam" % h,
            "at %dam task" % h,
            "ReminderResult",
            lambda r, hh=h: r.datetime_at.hour == hh,
        )
    for h in range(1, 12):
        add(
            s,
            "at %dpm" % h,
            "at %dpm task" % h,
            "ReminderResult",
            lambda r, hh=h: r.datetime_at.hour == hh + 12,
        )

    # G7) in N hours / minutes / days / weeks  (8 + 6 + 14 + 4 = 32)
    s = "G7. in N units"
    for n in range(1, 9):
        add(
            s,
            "in %d hours" % n,
            "in %d hours call" % n,
            "ReminderResult",
            lambda r, nn=n: r.datetime_at.hour == 14 + nn and r.datetime_at.day == 14,
        )
    for n in (5, 10, 15, 20, 30, 45):
        add(
            s,
            "in %d minutes" % n,
            "in %d minutes ping" % n,
            "ReminderResult",
            lambda r, nn=n: r.datetime_at.hour == 14 + nn // 60 and r.datetime_at.minute == nn % 60,
        )
    for n in range(1, 15):
        d = NOW + timedelta(days=n)
        add(
            s,
            "in %d days" % n,
            "in %d days review" % n,
            "TaskResult",
            lambda r, dd=d: is_task(r, "period") and r.start_at.date() == dd.date(),
        )
    for n in range(1, 5):
        d = NOW + timedelta(weeks=n)
        add(
            s,
            "in %d weeks" % n,
            "in %d weeks demo" % n,
            "TaskResult",
            lambda r, dd=d: is_task(r, "period") and r.start_at.date() == dd.date(),
        )

    # G8) every <weekday> → BYDAY  (7)
    s = "G8. every <weekday>"
    for wd in range(7):
        add(
            s,
            "every %s" % WD_NAMES[wd],
            "every %s sync" % WD_NAMES[wd],
            "TaskResult",
            lambda r, RR=RRULE[wd]: r.recurrence
            and r.recurrence.frequency == "WEEKLY"
            and r.recurrence.by_day == [RR],
        )

    # G9) every N weeks/months → INTERVAL  (5 + 5 = 10)
    s = "G9. every N weeks/months"
    for n in (2, 3, 4, 5, 6):
        add(
            s,
            "every %d weeks" % n,
            "every %d weeks sync" % n,
            "TaskResult",
            lambda r, nn=n: r.recurrence
            and r.recurrence.frequency == "WEEKLY"
            and r.recurrence.interval == nn,
        )
    for n in (2, 3, 4, 5, 6):
        add(
            s,
            "every %d months" % n,
            "every %d months review" % n,
            "TaskResult",
            lambda r, nn=n: r.recurrence
            and r.recurrence.frequency == "MONTHLY"
            and r.recurrence.interval == nn,
        )

    # G10) by <weekday> → deadline  (7)
    s = "G10. by <weekday> → deadline"
    for wd in range(7):
        d = bare_wd(wd)
        add(
            s,
            "by %s" % WD_NAMES[wd],
            "by %s submit report" % WD_NAMES[wd],
            "TaskResult",
            lambda r, dd=d: is_task(r, "deadline") and r.deadline.date() == dd.date(),
        )

    # G11) ranges H am - H am → Calendar  (durations)
    s = "G11. H am - H am ranges"
    for x, y in ((7, 9), (8, 10), (9, 11), (7, 11), (8, 11)):
        add(
            s,
            "%dam-%dam" % (x, y),
            "%dam-%dam work" % (x, y),
            "CalendarResult",
            lambda r, X=x, Y=y: r.start_at.hour == X and r.duration_minutes == (Y - X) * 60,
        )

    # G12) adverb recurrence  (4)
    s = "G12. adverb recurrence"
    for w, fr in (
        ("daily", "DAILY"),
        ("weekly", "WEEKLY"),
        ("monthly", "MONTHLY"),
        ("yearly", "YEARLY"),
    ):
        add(
            s,
            w,
            "%s standup" % w,
            "TaskResult",
            lambda r, F=fr: r.recurrence and r.recurrence.frequency == F,
        )

    # G13) invariant: recurrence start satisfies BYDAY/BYMONTHDAY
    s = "G13. recurrence start ⊨ RRULE"

    def _rec_ok(r):
        st = getattr(r, "start_at", None) or getattr(r, "datetime_at", None)
        rec = getattr(r, "recurrence", None)
        if rec is None or st is None:
            return False
        plain = [d for d in rec.by_day if d in {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}]
        if plain and RRULE.index(RRULE[st.weekday()]) not in [RRULE.index(d) for d in plain]:
            return False
        if rec.by_month_day and st.day not in rec.by_month_day:
            return False
        return True

    add(
        s,
        "every month on 15th → start 15th",
        "every month on the 15th report",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.day == 15,
    )
    add(
        s,
        "every 2 weeks on Monday → start Mon",
        "every 2 weeks on Monday review",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.weekday() == 0,
    )
    add(
        s,
        "except weekends → start weekday",
        "every day except weekends workout",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.weekday() < 5,
    )
    add(
        s,
        "every Monday → start Mon",
        "every Monday at 10 sync",
        "ReminderResult",
        lambda r: _rec_ok(r) and r.datetime_at.weekday() == 0,
    )
    add(
        s,
        "every Friday → start Fri",
        "every Friday until end of March sync",
        "TaskResult",
        lambda r: _rec_ok(r) and r.start_at.weekday() == 4,
    )

    # G14) voice / spelled-out numbers
    s = "G14. voice: spelled-out numbers"
    add(
        s,
        "in forty five minutes",
        "in forty five minutes call",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 45 and r.title == "call",
    )
    add(
        s,
        "in twenty minutes",
        "in twenty minutes coffee",
        "ReminderResult",
        lambda r: r.datetime_at.minute == 20,
    )
    add(s, "in an hour", "in an hour meeting", "ReminderResult", lambda r: r.datetime_at.hour == 15)
    add(
        s,
        "in half an hour",
        "in half an hour coffee",
        "ReminderResult",
        lambda r: r.datetime_at.minute == 30,
    )
    add(
        s,
        "at ten thirty",
        "at ten thirty meeting",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 10 and r.datetime_at.minute == 30,
    )
    add(
        s,
        "half past ten",
        "half past ten standup",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 10 and r.datetime_at.minute == 30,
    )
    add(
        s,
        "quarter past nine",
        "quarter past nine sync",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 9 and r.datetime_at.minute == 15,
    )
    add(
        s,
        "quarter to eight",
        "quarter to eight alarm",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 7 and r.datetime_at.minute == 45,
    )
    add(
        s,
        "ten oclock",
        "ten oclock meeting",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 10 and r.datetime_at.minute == 0,
    )
    add(
        s,
        "from nine to five",
        "from nine to five work",
        "CalendarResult",
        lambda r: r.start_at.hour == 9 and r.end_at.hour == 17,
    )
    add(
        s,
        "every forty five minutes",
        "every forty five minutes break",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "MINUTELY"
        and r.recurrence.interval == 45,
    )
    add(
        s,
        "every thirty minutes",
        "every thirty minutes standup",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.frequency == "MINUTELY"
        and r.recurrence.interval == 30,
    )
    add(
        s,
        "weekday + half past nine",
        "next friday at half past nine standup",
        "ReminderResult",
        lambda r: r.datetime_at.day == 27
        and r.datetime_at.hour == 9
        and r.datetime_at.minute == 30,
    )  # next = nearest + 7

    # G15) ordinal-of-month
    s = "G15. ordinal of the month"
    add(
        s,
        "first Thursday of the month",
        "first Thursday of the month report",
        "TaskResult",
        lambda r: r.start_at.weekday() == 3 and r.title == "report",
    )
    add(
        s,
        "last Thursday of the month",
        "last Thursday of the month retro",
        "TaskResult",
        lambda r: r.start_at.day == 26 and r.title == "retro",
    )
    add(
        s,
        "second-to-last Thursday",
        "second-to-last Thursday of the month x",
        "TaskResult",
        lambda r: r.start_at.day == 19,
    )
    add(
        s,
        "first business day",
        "first business day of the month report",
        "TaskResult",
        lambda r: r.start_at.weekday() < 5 and r.title == "report",
    )
    add(
        s,
        "last business day",
        "last business day of the month report",
        "TaskResult",
        lambda r: r.start_at.day == 27,
    )
    add(
        s,
        "first weekend",
        "first weekend of the month trip",
        "TaskResult",
        lambda r: r.start_at.weekday() == 5 and r.title == "trip",
    )
    add(
        s,
        "last Saturday of the month",
        "last Saturday of the month x",
        "TaskResult",
        lambda r: r.start_at.day == 28 and r.start_at.weekday() == 5,
    )
    add(
        s,
        "last week of the month",
        "last week of the month x",
        "TaskResult",
        lambda r: r.start_at.day == 22 and r.end_at.day == 28,
    )
    add(
        s,
        "every first Monday → BYDAY=1MO",
        "every first Monday of the month standup",
        "TaskResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=1MO",
    )
    add(
        s,
        "every last business day → BYSETPOS",
        "every last business day of the month report",
        "TaskResult",
        lambda r: r.recurrence
        and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
    )
    add(
        s,
        "every last Thursday → BYDAY=-1TH",
        "every last Thursday of the month retro",
        "TaskResult",
        lambda r: r.recurrence and r.recurrence.to_rrule() == "FREQ=MONTHLY;BYDAY=-1TH",
    )
    add(
        s,
        "every last Friday at 5pm",
        "every last Friday of the month at 5pm retro",
        "ReminderResult",
        lambda r: r.recurrence and "-1FR" in r.recurrence.to_rrule() and r.datetime_at.hour == 17,
    )
    add(
        s,
        "first weekday after the 15th",
        "first weekday after the 15th report",
        "TaskResult",
        lambda r: r.start_at.day == 16 and r.start_at.weekday() < 5 and r.title == "report",
    )
    add(
        s,
        "first Monday after the 15th",
        "first Monday after the 15th standup",
        "TaskResult",
        lambda r: r.start_at.day == 16 and r.start_at.weekday() == 0,
    )
    add(
        s,
        "last Friday before end of month",
        "last Friday before the end of the month retro",
        "TaskResult",
        lambda r: r.start_at.day == 27 and r.start_at.weekday() == 4 and r.title == "retro",
    )

    # ═══════════════════════════════════════════════════════════════════
    # R1) Regressions: crashes on invalid input, next-weekday convention
    # ═══════════════════════════════════════════════════════════════════
    s = "R1. Regressions (invalid input must be None, not a crash)"
    add(s, "at 25:00 → None", "at 25:00 broken", "None")
    add(s, "at 12:60 → None", "at 12:60 broken", "None")
    add(s, "bare 99:99 → None", "99:99 broken", "None")
    add(s, "from 30 to 50 → not a crash", "from 30 to 50 nonsense", "None")
    add(s, "in 999999999 years → None", "in 999999999 years party", "None")
    add(s, "in 999999999 days → None", "in 999999999 days party", "None")
    # NOW = Sat 14.02: nearest Thu = 19.02 → next Thursday = 26.02 (nearest + 7)
    add(
        s,
        "next Thursday = nearest + 7",
        "next Thursday sync",
        "TaskResult",
        lambda r: r.start_at.day == 26,
    )
    # NOW = Sat: nearest Saturday = today 14.02 → next Saturday = 21.02
    add(
        s,
        "next Saturday (same weekday) = today + 7",
        "next Saturday brunch",
        "TaskResult",
        lambda r: r.start_at.day == 21,
    )
    # valid time still parses after validation was added
    add(
        s,
        "at 23:59 still valid",
        "at 23:59 release",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 23 and r.datetime_at.minute == 59,
    )
    add(s, "12pm is noon", "at 12pm lunch", "ReminderResult", lambda r: r.datetime_at.hour == 12)
    add(s, "12am is midnight", "at 12am job", "ReminderResult", lambda r: r.datetime_at.hour == 0)

    # ═══════════════════════════════════════════════════════════════════
    # R2) Regressions: fractional intervals & "by end of <month>"
    # ═══════════════════════════════════════════════════════════════════
    s = "R2. Regressions (and-a-half intervals, by end of <month>)"
    # NOW = Sat 14.02.2026 14:00
    add(
        s,
        "in an hour and a half → 15:30",
        "in an hour and a half call",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 15 and r.datetime_at.minute == 30,
    )
    add(
        s,
        "in two and a half hours → 16:30",
        "in two and a half hours call",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        s,
        "in 2 and a half hours (digit) → 16:30",
        "in 2 and a half hours call",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 30,
    )
    add(
        s,
        "in a minute and a half",
        "in a minute and a half ping",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 14 and r.datetime_at.minute == 1,
    )
    add(
        s,
        "plain in 2 hours not broken",
        "in 2 hours call",
        "ReminderResult",
        lambda r: r.datetime_at.hour == 16 and r.datetime_at.minute == 0,
    )
    add(
        s,
        "by end of March → 31.03 23:59",
        "by end of March report",
        "TaskResult",
        lambda r: r.deadline.month == 3 and r.deadline.day == 31 and r.deadline.hour == 23,
    )
    add(
        s,
        "by end of past month → next year",
        "by end of January report",
        "TaskResult",
        lambda r: r.deadline.year == 2027 and r.deadline.month == 1 and r.deadline.day == 31,
    )
    add(
        s,
        "by end of month still works",
        "by end of month report",
        "TaskResult",
        lambda r: r.deadline.month == 2 and r.deadline.day == 28,
    )

    # ═══════════════════════════════════════════════════════════════════
    # R3) Regressions: location extraction (parity with RU)
    # ═══════════════════════════════════════════════════════════════════
    s = "R3. Regressions (location extraction)"
    add(
        s,
        "at the office → location",
        "at the office tomorrow at 10 meeting",
        "ReminderResult",
        lambda r: r.location == "at the office" and r.title == "meeting",
    )
    add(
        s,
        "at the gym → location",
        "meeting at the gym tomorrow at 10",
        "ReminderResult",
        lambda r: r.location == "at the gym" and r.title == "meeting",
    )
    add(
        s,
        "in the park → location",
        "tomorrow at 10 meeting in the park",
        "ReminderResult",
        lambda r: r.location == "in the park" and r.title == "meeting",
    )
    add(
        s,
        "no location → None",
        "tomorrow at 10 meeting",
        "ReminderResult",
        lambda r: r.location is None,
    )
    add(
        s,
        "in the morning is NOT location",
        "tomorrow in the morning run",
        "TaskResult",
        lambda r: r.location is None,
    )

    def _multi_en(text, checks):
        def chk(_):
            rs = parser.parse_multi(text, now=NOW, language="en")
            if len(rs) != len(checks):
                return False
            return all(c(r) for c, r in zip(checks, rs))

        return chk

    add(
        s,
        "multi: second event inherits tomorrow",
        "meeting tomorrow at 10 and call at 3pm",
        "ReminderResult",
        _multi_en(
            "meeting tomorrow at 10 and call at 3pm",
            [
                lambda r: r.datetime_at.day == 15 and r.datetime_at.hour == 10,
                lambda r: r.datetime_at.day == 15 and r.datetime_at.hour == 15,
            ],
        ),
    )

    return T


def run_case(name, text, expected_type, check, fail_only):
    r = parser.parse(text, now=NOW, language="en")
    actual = type(r).__name__ if r is not None else "None"
    type_ok = actual == expected_type
    check_ok = True
    if check:
        try:
            check_ok = bool(check(r))
        except Exception:
            check_ok = False
    passed = type_ok and check_ok
    if passed and fail_only:
        return passed
    status = (GREEN + "✅ PASS" + RESET) if passed else (RED + "❌ FAIL" + RESET)
    print("%s  %s%s%s" % (status, BOLD, name, RESET))
    print('   %sInput:%s "%s"' % (DIM, RESET, text))
    print("   %sType:%s  %s" % (DIM, RESET, fmt_type(r)))
    for ln in fmt_info(r):
        print(ln)
    if not type_ok:
        print("   %s⚠️  expected %s, got %s%s" % (RED, expected_type, actual, RESET))
    elif not check_ok:
        print("   %s⚠️  value check failed%s" % (RED, RESET))
    return passed


def main(fail_only=False):
    tests = build_tests()
    sections = {}
    for section, name, text, et, check in tests:
        sections.setdefault(section, []).append((name, text, et, check))

    print("█" * 64)
    print("%s   🕐 TimeSense — English locale test suite%s" % (BOLD, RESET))
    print("█" * 64)
    print("📅 Reference now: %s (Saturday)" % NOW.strftime("%d.%m.%Y %H:%M"))
    print("   🔧 Sections: %d" % len(sections))
    print("   🧪 Tests: %d" % len(tests))
    print("   🌐 language='en'")
    if fail_only:
        print("   🧹 Mode: failures only (--fail-only)")

    passed = total = 0
    for section, items in sections.items():
        if not fail_only:
            print_section(section)
        for name, text, et, check in items:
            total += 1
            if run_case(name, text, et, check, fail_only):
                passed += 1

    print("█" * 64)
    if passed == total:
        print("%s%s   🎉 All English tests passed: %d/%d%s" % (GREEN, BOLD, passed, total, RESET))
    else:
        print("%s%s   ⚠️  Passed: %d/%d%s" % (RED, BOLD, passed, total, RESET))
        print("%s   ❌ Failed: %d%s" % (RED, total - passed, RESET))
    print("█" * 64)
    return passed == total


if __name__ == "__main__":
    ok = main(fail_only="--fail-only" in sys.argv)
    sys.exit(0 if ok else 1)

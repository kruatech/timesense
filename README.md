# TimeSense

**Languages:** **English** · [Русский](https://github.com/kruatech/timesense/blob/main/README.ru.md)

[![CI](https://github.com/kruatech/timesense/actions/workflows/ci.yml/badge.svg)](https://github.com/kruatech/timesense/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/timesense.svg)](https://pypi.org/project/timesense/)
[![Python](https://img.shields.io/pypi/pyversions/timesense.svg)](https://pypi.org/project/timesense/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://pypi.org/project/timesense/)
[![No ML](https://img.shields.io/badge/ML%20models-none-blue)](#why-timesense)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/kruatech/timesense/blob/main/LICENSE)

Natural-language date/time & event parser for **Russian and English**.

TimeSense turns phrases like `"tomorrow at 10 meeting"`, `"from 9 to 5 work"`, or
`"every Monday standup"` — and their Russian equivalents — into structured event
objects, ready to export as JSON, an iCalendar `rrule`, or a full `.ics`
file. It is **pure Python**,
has **no required dependencies**, and is designed for turning voice/ASR
transcripts into structured dates.

There is **no machine learning inside** — the engine is dictionaries and
regular expressions. It needs no GPU, downloads no models, and runs comfortably
on the cheapest VPS, a Raspberry-Pi-class board, or inside a serverless
function: ~0.2 s cold start, a few MB of RAM, and under a millisecond per
phrase (~1,000+ phrases/sec on a single modest core). That makes it practical
to call inline on every utterance of a live transcription pipeline —
speech-to-text output goes in, calendar-ready events come out.

| Footprint | |
|---|---|
| Required dependencies | **0** — pure Python 3.9–3.13, stdlib only |
| ML models / GPU | **none** — dictionaries & regular expressions |
| Cold start | ~0.2 s (interpreter + import) |
| Memory | a few MB |
| Latency | **<1 ms** per phrase — 1,000+ phrases/sec on a single modest core |
| Deployment | cheapest VPS · Raspberry-Pi-class boards · serverless |

```python
from datetime import datetime
from timesense import TimeSenseParser

parser = TimeSenseParser()
r = parser.parse("tomorrow at 10 meeting", now=datetime(2026, 2, 14, 14, 0))

type(r).__name__     # 'ReminderResult'
r.title              # 'meeting'
r.human_readable()   # '15.02.2026 10:00'
r.to_dict()
# {'type': 'reminder', 'title': 'meeting', 'source': 'tomorrow at 10 meeting',
#  'confidence': 0.9, 'is_past': False, 'language': 'en',
#  'datetime': '2026-02-15T10:00:00'}
```

Russian works out of the box too — the language is auto-detected:

```python
parser.parse("каждый понедельник в 10 планёрка").to_dict()["recurrence"]["rrule"]
# 'FREQ=WEEKLY;BYDAY=MO'
```

## Why TimeSense?

| | **TimeSense** | Classic date parsers¹ | LLM / ML pipelines |
|---|:---:|:---:|:---:|
| Dates & times from free text | ✅ | ✅ | ✅ |
| Event classification (reminder / calendar / task) | ✅ | ❌ | 🟡 prompt-dependent |
| Recurrence → RFC 5545 `RRULE` | ✅ | ❌ | 🟡 |
| Ready-to-import `.ics` export | ✅ | ❌ | ❌ |
| Event title & location extraction | ✅ | ❌ | ✅ |
| Zero dependencies | ✅ | ❌ | ❌ |
| Deterministic (same input → same output) | ✅ | ✅ | ❌ |
| No GPU, no model downloads, fully offline | ✅ | ✅ | ❌ |
| Runs on Raspberry-Pi-class hardware | ✅ | ✅ | ❌ |

¹ e.g. `dateparser`, `parsedatetime` — great at extracting a `datetime`, but they stop there.

**Contents:**
[Features](#features) ·
[Installation](#installation) ·
[Quick start](#quick-start) ·
[Showcase](#showcase-complex-phrases) ·
[Result types](#result-types) ·
[Recurrence](#recurring-events-rrule) ·
[.ics export](#calendar-export-ics) ·
[Configuration](#configuration) ·
[Multiple events](#multiple-events-in-one-phrase) ·
[Patterns](#supported-patterns-excerpt) ·
[Parsing policy](#status-languages--parsing-policy) ·
[Development](#development--tests)

## Features

- **Times:** `at 5pm`, `9:30am`, `at 17:00`, `noon`, `half past ten`,
  `quarter to eight` · RU: `в 15:30`, `в 10 утра`, `без пяти десять`.
- **Relative:** `in 2 hours`, `in an hour and a half`, `in forty five minutes`,
  `tomorrow`, `next Friday` · RU: `через 2 часа`, `через час`, `через полтора часа`,
  `через 2,5 часа` (decimal comma), `через два с половиной часа`, `через неделю`,
  `5 минут назад`.
- **Dates:** `Feb 17`, `March 3rd`, `3/17`, ISO `2026-02-17` · RU: `10 января`,
  `первого сентября`, `15 числа`, `в пятницу`.
- **Ranges → `CalendarResult`:** `from 9 to 5`, `9am-11am`, `between 10 and 12`
  · RU: `с 9 до 10`, `с десяти до одиннадцати`, `с понедельника по среду`.
- **Recurrence → `rrule`:** `every day`, `every weekday`, `every 2 weeks on Monday`,
  `every month on the 15th`, `N times` (COUNT), `until end of March` (UNTIL),
  `except weekends` (BYDAY) · RU: `каждый понедельник`, `по будням`, `каждые 2 недели`.
- **Deadlines:** `by Friday`, `by 5pm`, `by end of month`, `by end of March`
  · RU: `до пятницы`, `до конца марта`, `не позднее 20-го`, `в течение часа`.
- **Duration & location:** `for 2 hours`, `на 2 часа`, `at the office`, `в офисе`.
- **Result classification:** reminder / calendar event / task, with `is_past`,
  `detected_language`, JSON and `rrule` export.

## Installation

```bash
pip install timesense
```

No dependencies — pure Python (3.9–3.13). Morphology is optional; without it the
parser uses built-in word-form dictionaries. For improved Russian lemmatization:

```bash
pip install "timesense[morph]"   # pulls in pymorphy3
```

## Quick start

`parse()` returns a single object (`ReminderResult` / `CalendarResult` /
`TaskResult`) or `None` when no date/time is found. Pin the reference time with
`now`, and force a language with `language=` (otherwise it is auto-detected):

```python
from datetime import datetime
from timesense import TimeSenseParser

parser = TimeSenseParser()
now = datetime(2026, 2, 14, 14, 0)

parser.parse("in forty five minutes call", now=now)     # ReminderResult 14:45
parser.parse("from 9 to 5 work", now=now)               # CalendarResult 09:00–17:00
parser.parse("every weekday at 9 standup", now=now)     # rrule FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
parser.parse("в 10 мск созвон", now=now)                # None (timezones unsupported)
parser.parse("tomorrow at 10", now=now, language="en")  # explicit language
```

## Showcase: complex phrases

One phrase can carry a recurrence rule, a time, a location and a title at once —
and the result type is picked automatically. All outputs below are real
(`now = 2026-07-06 15:41`, a Monday):

```python
# Recurrence + time + location → ReminderResult with an RRULE
p.parse("every second Friday of the month at 6:30pm retro in the meeting room")
# ReminderResult · title='retro' · location='in the meeting room'
# datetime=2026-07-10 18:30 · rrule='FREQ=MONTHLY;BYDAY=2FR'

# Range crossing midnight → CalendarResult
p.parse("next Tuesday from 23:15 to 00:45 check the maintenance window")
# CalendarResult · 2026-07-14 23:15 → 2026-07-15 00:45 · duration_minutes=90

# Business-day arithmetic → TaskResult (deadline)
p.parse("two business days before end of month remind about closing documents")
# TaskResult · task_type=deadline · deadline=2026-07-29 23:59

# Season → TaskResult (fuzzy period)
p.parse("in winter run the security audit")
# TaskResult · 2026-12-01 → 2027-02-28

# Mixed types in one line → parse_multi
p.parse_multi("today by 18 close the contract, tomorrow at 9 show the demo, "
              "Friday at 16 collect retro notes")
# TaskResult(deadline 2026-07-06 18:00) · ReminderResult(2026-07-07 09:00)
# · ReminderResult(2026-07-10 16:00)
```

## Result types

All results share a common interface: `.title`, `.source`, `.confidence`,
`.is_past`, `.location`, `.duration_minutes`, `.recurrence`, `.exclusions`,
`.detected_language`, `.event_type` (an `EventType` enum), plus `.to_dict()` and
`.human_readable()`.

### `ReminderResult` — a point in time

```python
r = parser.parse("at 3:30pm sync")
r.datetime_at        # datetime(..., 15, 30)
```

### `CalendarResult` — an event with start and end

```python
r = parser.parse("from 10 to 11 sync")
r.start_at           # datetime(..., 10, 0)
r.end_at             # datetime(..., 11, 0)
r.duration_minutes   # 60
```

### `TaskResult` — a task (period / deadline / open-start / fuzzy)

```python
from timesense import TaskType

r = parser.parse("by Friday submit report")
r.task_type          # TaskType.PERIOD | DEADLINE | OPEN_START | FUZZY
r.deadline           # deadline datetime (for TaskType.DEADLINE)
r.start_at, r.end_at # start/end when applicable
r.fuzzy              # bool
```

## Recurring events (`rrule`)

```python
r = parser.parse("every Monday standup")
r.recurrence.to_rrule()      # 'FREQ=WEEKLY;BYDAY=MO'
r.to_dict()["recurrence"]
# {'frequency': 'WEEKLY', 'interval': 1, 'by_day': ['MO'],
#  'until': None, 'count': None, 'rrule': 'FREQ=WEEKLY;BYDAY=MO'}

parser.parse("every Friday until end of March sync").recurrence.to_rrule()
# 'FREQ=WEEKLY;BYDAY=FR;UNTIL=20260331T235900'   (naive: no trailing Z)
```

The start date always satisfies its own rule: a `BYDAY`/`BYMONTHDAY` recurrence
snaps `DTSTART` to the first valid occurrence.

## Calendar export (`.ics`)

Export any result — or a whole list — to an iCalendar file that opens in
Google Calendar, Apple Calendar and Outlook:

```python
from timesense import TimeSenseParser, to_ics_calendar

p = TimeSenseParser()
events = [
    p.parse("every Monday at 10 standup", language="en"),
    p.parse("meeting Friday 18:00 to 20:00", language="en"),
]
with open("events.ics", "w", encoding="utf-8") as f:
    f.write(to_ics_calendar(events))

# single event:
p.parse("tomorrow at 10 call the client", language="en").to_ics()
```

RFC 5545 `VEVENT`s carry `DTSTART`/`DTEND`/`RRULE`/`SUMMARY`/`LOCATION`.
Periods and deadlines are emitted as all-day (`VALUE=DATE`) events; text is
escaped and long lines folded per the spec.

## Configuration

```python
from timesense import TimeSenseParser, TimeConfig

config = TimeConfig(
    prefer_nearest_future=True,   # shift past times into the nearest future
    default_hour_for_one=13,      # "at one" → 13:00
    default_language="auto",      # "auto" | "ru" | "en"
    timezone="Europe/Amsterdam",  # stored but NOT applied — datetimes are naive
    working_hours={"start": 9, "end": 18},
    custom_times={"briefing": (11, 30)},  # custom word → (hour, minute)
)

parser = TimeSenseParser(config)
```

Presets: `TimeConfig.default()` and `TimeConfig.strict()`
(`prefer_nearest_future=False`, `default_hour_for_one=1`). Invalid language
values raise `ValueError`.

### Production / working calendar

Load a working calendar so that all "business day" logic honours public holidays
(excluded) and transferred working weekends (included):

```python
from timesense import TimeSenseParser, TimeConfig, WorkingCalendar

cal = WorkingCalendar(
    holidays=["2026-02-26", "2026-02-27"],   # non-working days
    working_weekends=["2026-02-28"],          # a Saturday declared working
    holiday_names={"new year": "2026-01-01"},
)
parser = TimeSenseParser(TimeConfig(calendar=cal))
parser.parse("last business day of the month report")  # → 2026-02-28 (skips the holidays)
```

`WorkingCalendar` accepts `date`, `datetime` or `"YYYY-MM-DD"` strings, loads from
`WorkingCalendar.from_dict(...)` / `from_json(path_or_str)`, and exposes
`is_working_day`, `is_holiday`, `next_working_day`, `prev_working_day`,
`resolve_holiday`. With no calendar, a business day is simply Mon–Fri.

## Multiple events in one phrase

```python
parser.parse_multi("meeting tomorrow at 10 and lunch at 12")
# [ReminderResult('meeting'), ReminderResult('lunch')]
```

`parse_multi()` splits heuristically on `,` `;` `and` / `then` (en) and
`« и »` (ru). A separator inside an event title may cause a false split;
`between X and Y` is not split, and a decimal comma (`через 2,5 часа`) is
never treated as a separator.

A time-only segment **inherits the date of the previous event**:
`"завтра в 10 встреча и в 15 созвон"` puts both events on tomorrow. Segments
with their own date words (`послезавтра`, weekdays, `today`/`сегодня`, …)
keep their own anchor.

## Supported patterns (excerpt)

| Category    | Examples (EN) |
|-------------|---------------|
| Times       | `at 5pm`, `9:30am`, `at 17:00`, `noon`, `midnight` |
| Word times  | `at ten thirty`, `half past ten`, `quarter to eight` |
| Relative    | `in 2 hours`, `in forty five minutes`, `in 3 days` |
| Dates       | `Feb 17`, `March 3rd`, `3/17`, `2026-02-17` |
| Weekdays    | `next Friday`, `this Monday`, `Friday` |
| Ranges      | `from 9 to 5`, `9am-11am`, `between 10 and 12` |
| Recurrence  | `every day`, `every weekday`, `every 2 weeks on Monday`, `every month on the 15th` |
| Modifiers   | `5 times` (COUNT), `until end of March` (UNTIL), `except weekends` (BYDAY) |
| Deadlines   | `by Friday`, `by 5pm`, `by end of month` |

Russian examples are listed in the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md).

## Status, languages & parsing policy

- **Status:** stable (1.0.0). The public API (`parse`, `parse_multi`,
  `TimeConfig`, result types, `detected_language`, `to_dict()`) is frozen;
  breaking changes only in the next major (semver).
- **Python:** 3.9–3.13.
- **Languages:** Russian is the primary, most complete locale; English is a
  dedicated locale (`timesense/locales/en.py`) covering the core grammar,
  including spelled-out numbers (`in forty five minutes`, `at ten thirty`,
  `half past ten`, `quarter to eight`, `from nine to five`,
  `every forty five minutes`). The language is auto-detected
  (`default_language="auto"`) or set explicitly via `parse(text, language=...)`;
  the chosen language is reported in `detected_language`.
- **Time zones:** not supported. All `datetime`s are **naive** (no `tzinfo`).
  `TimeConfig.timezone` is stored but never applied. Zone-bearing phrases
  (`в 10 мск`, `UTC`, `GMT+3`) deliberately return `None`.
- **Smart-hour:** a bare hour after the current time is read as the nearest
  future. Example: with `now=14:00`, `"at 10"` → **22:00** today (not 10:00
  tomorrow); bare hours `1–7` shift to PM. Explicit minutes disable this:
  `"at 10:00"` → 10:00 sharp (tomorrow if already past). An explicit day-part
  marker always wins over the heuristics: `"завтра в 7 утра"` → 07:00,
  `"завтра в 3 ночи"` → 03:00, `"tomorrow at 3am"` → 03:00. Turn smart-hour
  off with `prefer_nearest_future=False`.
- **"Next" weekday:** plain weekday means the nearest upcoming one; `next` /
  `следующий` means the nearest one **plus a week** — the same convention in
  both languages. On Saturday, `"Friday"` → the coming Friday and
  `"next Friday"` / `"в следующую пятницу"` → a week after it.
- **Reminder / Calendar / Task:** a point in time → `ReminderResult`; an interval
  with start and end → `CalendarResult`; period / deadline / open-start / fuzzy →
  `TaskResult`. Past events are flagged with `is_past=True`.

### Known limitations

- Time zones are not applied (naive datetimes).
- Spelled-out numbers are supported, including compounds and verbose forms
  (`in forty five minutes`, `from nine to five`, `every forty five minutes`;
  RU `в десять часов пятнадцать минут`, `час пятнадцать`, `с двух до половины
  четвёртого`). A few rare colloquialisms (e.g. English `"ten fifteen"` with no
  `at`/idiom) still need explicit forms.
- `parse_multi()` splits into multiple events only when every segment is self-contained (parses on its own); otherwise it returns a single result, so plain lists like `buy milk and bread tomorrow` are not broken apart.
- Holidays and typo correction are out of scope (they return `None`).

## Development & tests

Tests are **not shipped in the wheel** (`pip install timesense` does not
include them), but they **are** included in the source distribution. They
live in the repository; run them from a clone:

```bash
git clone https://github.com/kruatech/timesense
cd timesense
pip install -e ".[dev]"

python -m timesense.tests.test_fixes --fail-only     # RU runner
python -m timesense.tests.test_en_fixes --fail-only  # EN runner
pytest -q                                            # wrappers + EN pytest suite

# release checks
python -m build
python -m twine check dist/*
```

Examples run as a module from the repo root:

```bash
python -m examples.basic_usage
```

## Contributing

Pull requests are welcome. For larger changes, please open an issue first.
See [CONTRIBUTING.md](https://github.com/kruatech/timesense/blob/main/CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](https://github.com/kruatech/timesense/blob/main/CODE_OF_CONDUCT.md)
and [SECURITY.md](https://github.com/kruatech/timesense/blob/main/SECURITY.md).

## License

MIT — see [LICENSE](https://github.com/kruatech/timesense/blob/main/LICENSE).

## Author & contact

**Anton Krutilin**

- GitHub: <https://github.com/kruatech>
- Telegram: [@kruatech](https://t.me/kruatech)
- Email: a@krutilin.pro

Bugs & feature requests: <https://github.com/kruatech/timesense/issues>

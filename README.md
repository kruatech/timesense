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
| Required dependencies | **0** — pure Python 3.9–3.14, stdlib only |
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

Russian works out of the box too — the language is auto-detected. Russian examples
are in the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md).

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
[Command line](#quick-check-from-the-command-line) ·
[Result types](#result-types) ·
[For chat bots](#for-chat-bots-analyze-and-when) ·
[Recurrence](#recurring-events-rrule) ·
[.ics export](#calendar-export-ics) ·
[Configuration](#configuration) ·
[Time zones](#time-zones) ·
[Holidays](#holidays) ·
[Multiple events](#multiple-events-in-one-phrase) ·
[Patterns](#supported-patterns-excerpt) ·
[Parsing policy](#status-languages--parsing-policy) ·
[Development](#development--tests)

## Features

Both languages have the same feature set; Russian examples are in the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md).

- **Times:** `at 5pm`, `9:30am`, `at 17:00`, `noon`, `midnight`, `half past ten`,
  `quarter to eight`, `at 1930`, `7.30pm`, `around 5`, `5ish`.
- **Relative:** `in 2 hours`, `in an hour and a half`, `in an hour fifteen`,
  `in a couple of hours`, `in 30 seconds`, `3 days from now`, `5 minutes ago`,
  `3 years ago`.
- **Dates:** `Feb 17`, `March 3rd`, `3/17`, `25/09`, ISO `2026-02-17`, `on the 5th`,
  `next week on Wednesday`, `in 3 weeks on Monday`, `friday after next`,
  historic dates (`april 12 1961`).
- **Day parts:** `tonight at 8:30`, `tomorrow morning`, `this afternoon`,
  `towards evening`, `last night`.
- **Ranges → `CalendarResult`:** `from 9 to 5`, `9am-11am`, `from 3 to 4:30pm`,
  `between 10 and 12`, `from 10am to noon`, `from 9am on april 12 to 11am`,
  `Sep 25 - Oct 3`, `from june 22 1941 to may 9 1945`.
- **Periods:** `in October`, `in 2027`, `next month`, `beginning of next month`,
  `mid October`, `second week of October`, `this weekend`, `the whole week`, `in Q1`,
  `last winter`.
- **Recurrence → `rrule`:** `every Monday and Wednesday`, `every weekday except Friday`,
  `every morning at 7`, `every 15th`, `every last day of the month`,
  `last business day of every month`, `every March 5`,
  `every year on the last friday of october`, `N times` (COUNT),
  `until end of March` (UNTIL). Intervals: `biweekly`, `fortnightly`, `every other week`,
  `every second/third week`, `every quarter`, `every six months`, `every hour`.
  Series bounds: `starting october 1`, `from october 1 to december 1`. Excluded dates
  (`EXDATE`): `except december 31`. Hour windows (`BYHOUR`): `every 30 minutes from 9
  to 6 on weekdays`. Even/odd days: `on even days`.
- **Deadlines:** `by Friday`, `by 5pm on Friday`, `until 6pm`, `before lunch`, `eod`,
  `within 2 hours`, `in the next 2 hours`, `through tuesday`, `by the 20th`,
  `by new year`.
- **N days before:** `two days before friday`, `2 business days before july 20`,
  `a week before july 20`, `two days before end of month` — the start of that day
  (09:00); business days honour the holiday calendar.
- **Open start:** `after 5pm`, `after lunch`, `no earlier than 10am`.
- **Time windows:** `after 10 but before 12`, `from morning to noon`,
  `from lunch to evening`.
- **Titles:** a preposition stays with its own word (`to the doctor`, `with the team`)
  and is dropped only when it points at consumed material (`meeting for 2 hours` →
  `meeting`).
- **Duration & location:** `for 2 hours`, `for 1.5 hours`, `lasting 2 hours`,
  `at the office`.
- **Holidays:** `christmas party at 7pm`, `by thanksgiving`, `every christmas`.
- **Typos & chat shorthand:** `tmrw`, `firday`, `wensday`, `remind me to …`.
- **Time zones:** `at 10 EST`, `london time`, `utc+3` — converted to the user's zone
  (`tz=`).
- **Result classification:** reminder / calendar event / task, with `is_past`,
  `detected_language`, JSON, `rrule` and `.ics` export.

## Installation

```bash
pip install timesense
```

No dependencies — pure Python (3.9–3.14). Optional extras:

```bash
pip install "timesense[morph]"   # pymorphy3 — Russian lemmatization
pip install "timesense[tz]"      # tzdata — IANA zones for systems without them
```

Morphology barely changes the results but makes parsing about 5× slower. For bots
on modest hardware turn it off: `TimeConfig(use_morph=False)` or the environment
variable `TIMESENSE_MORPH=0`.

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
parser.parse("at 10am EST call", now=now)               # None (no user tz given)
parser.parse("at 10am EST call", now=now, tz="Europe/Amsterdam")  # aware, converted from EST
parser.parse("tomorrow at 10", now=now, language="en")  # explicit language
```

## Showcase: complex phrases

One phrase can carry a recurrence rule, a time, a location and a title at once — and
the result type is picked automatically. All outputs below are real and reproducible:
`--now` pins the reference time (Monday, July 6, 2026). In code the same comes from
`parser.parse(phrase, now=...)`, and the one-line breakdown from `result.summary()`.

**Every other week + time + until end of year** — a reminder with an `RRULE`:

```console
$ python -m timesense --now "2026-07-06 15:41" "every other wednesday at 11 sync with the designer until end of year"
reminder ⟳ FREQ=WEEKLY;INTERVAL=2;BYDAY=WE;UNTIL=20261231T235900  08.07.2026 11:00  «sync with the designer»
```

**Recurrence + time + location:**

```console
$ python -m timesense --now "2026-07-06 15:41" "every second Friday of the month at 6:30pm retro in the meeting room"
reminder ⟳ FREQ=MONTHLY;BYDAY=2FR  10.07.2026 18:30  @in the meeting room  «retro»
```

**Range crossing midnight** — a calendar event with a duration:

```console
$ python -m timesense --now "2026-07-06 15:41" "next Tuesday from 23:15 to 00:45 check the maintenance window"
calendar  14.07.2026 23:15 → 15.07.2026 00:45  (90 min)  «check the maintenance window»
```

**Business-day arithmetic:**

```console
$ python -m timesense --now "2026-07-06 15:41" "two business days before end of month remind about closing documents"
task/period  29.07.2026 09:00  «closing documents»
```

**Season** — a fuzzy period:

```console
$ python -m timesense --now "2026-07-06 15:41" "in winter run the security audit"
task/fuzzy  01.12.2026 00:00 → 28.02.2027 23:59  ~approx  «run the security audit»
```

**Mixed types in one line** (`--multi`; in code — `parse_multi()`):

```console
$ python -m timesense --now "2026-07-06 15:41" --multi "today by 18 close the contract, tomorrow at 9 show the demo, Friday at 16 collect retro notes"
task/deadline  by 06.07.2026 18:00  «close the contract»
reminder  07.07.2026 09:00  «show the demo»
reminder  10.07.2026 16:00  «collect retro notes»
```

## Quick check from the command line

```console
$ python -m timesense --now "2026-09-22 14:00" "tomorrow at 10 meeting for 2 hours"
calendar  23.09.2026 10:00 → 12:00  (120 min)  «meeting»

$ python -m timesense --now "2026-09-22 14:00" "every monday at 10 standup"
reminder ⟳ FREQ=WEEKLY;BYDAY=MO  28.09.2026 10:00  «standup»

$ python -m timesense --now "2026-09-22 14:00" "monday or tuesday call"
monday or tuesday call
    not recognized: ambiguous (alternatives: several dates/times offered)
    option: task/period  28.09.2026 00:00 → 23:59  «call»
    option: task/period  29.09.2026 00:00 → 23:59  «call»
```

After `pip install timesense` the same is available as a plain `timesense "phrase"`
command. Flags: `--now "2026-09-22 14:00"`, `--tz Europe/Moscow`, `--lang ru|en`,
`--multi`, `--json`, `--ics`, `--no-morph`; phrases are also read from stdin.
Exit code is 1 when nothing was recognised. The same one-liner is available in
code as `result.summary()` — kind, start, end, duration, recurrence, location
and title for every result type.

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

## For chat bots: `analyze()` and `.when`

`parse()` returns `None` on any failure. A bot usually needs to know *why* —
to ask the right follow-up question. `analyze()` returns the same result plus a
status, a reason and, for ambiguous input, the parsed alternatives:

```python
from timesense import TimeSenseParser, ParseStatus

p = TimeSenseParser()
a = p.analyze("monday or tuesday call", tz="Europe/Amsterdam")
a.status          # ParseStatus.AMBIGUOUS
a.alternatives    # [Task(Mon 28.09), Task(Tue 29.09)] — offer them as buttons
a.to_dict()       # JSON-ready

if a.ok:
    schedule(a.result.when, a.result.title)   # .when: reminder time, deadline or start
elif a.status is ParseStatus.NEEDS_TIMEZONE:
    ask("Which time zone are you in?")
elif a.status is ParseStatus.INVALID_DATE:
    ask("That date doesn't exist — did you mean another one?")
```

`analyze_multi()` does the same for several events in one message
(`"tomorrow 10am standup, 1pm lunch and 6pm gym"` → three `ok` analyses).

Statuses: `ok`, `empty`, `too_long`, `no_datetime`, `ambiguous`, `invalid_date`,
`needs_timezone`, `multiple` (several separate events — `"on monday, wednesday and
friday at 10"` — all of them are in `alternatives`, and `parse_multi()` returns them). `result.when` is available on every result type
(`ReminderResult.datetime_at`, `TaskResult.deadline`, otherwise `start_at`).

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
snaps `DTSTART` to the first valid occurrence — and never before an explicit start
date. More rule features, all reproducible:

```console
$ python -m timesense --now "2026-09-22 14:00" "every monday from october 1 to december 1 standup"
task/period ⟳ FREQ=WEEKLY;BYDAY=MO;UNTIL=20261201T235900  05.10.2026  all day  «standup»
$ python -m timesense --now "2026-09-22 14:00" "every day at 8 except dec 31 and jan 1 workout"
reminder ⟳ FREQ=DAILY except 31.12.2026, 01.01.2027  23.09.2026 08:00  «workout»
$ python -m timesense --now "2026-09-22 14:00" "every 30 minutes from 9 to 6 stretch"
reminder ⟳ FREQ=MINUTELY;INTERVAL=30;BYHOUR=9,10,11,12,13,14,15,16,17  22.09.2026 14:00  «stretch»
$ python -m timesense --now "2026-09-22 14:00" "every other wednesday at 11 sync"
reminder ⟳ FREQ=WEEKLY;INTERVAL=2;BYDAY=WE  23.09.2026 11:00  «sync»
$ python -m timesense --now "2026-09-22 14:00" "on odd days at 9 water plants"
reminder ⟳ FREQ=MONTHLY;BYMONTHDAY=1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31  23.09.2026 09:00  «water plants»
```

`to_dict()["recurrence"]` gains `exdates` and `by_hour` only when they are present, so
the format of every other result is unchanged. Excluded dates are stored at the series'
time, so each one matches a real occurrence. An exclusion with no series
(`"except december 31"`) is not an event on that date and returns `None`.

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
escaped and long lines folded per the spec. `DTSTAMP` is UTC; recurring events
in a user time zone get `DTSTART;TZID=…` plus a generated `VTIMEZONE` (DST rules
derived from the IANA database), so series don't drift across DST changes.
Excluded dates become `EXDATE` of the same type as `DTSTART` (DATE, floating or
`TZID`). Add a reminder with `to_ics(result, alarm_minutes=15)` (`VALARM`).

## Configuration

```python
from timesense import TimeSenseParser, TimeConfig

config = TimeConfig(
    prefer_nearest_future=True,   # shift past times into the nearest future
    default_hour_for_one=13,      # "at one" → 13:00
    default_language="auto",      # "auto" | "ru" | "en"
    timezone="Europe/Amsterdam",  # stored but NOT applied — pass tz= to parse() instead
    max_text_length=1000,         # longer input → None (None = no limit)
    use_morph=None,               # None=auto, False=off (faster), True=on
    default_tz="Europe/Amsterdam",  # user zone when parse() gets no tz= (None = naive)
    working_hours={"start": 9, "end": 18},
    custom_times={"briefing": (11, 30)},  # custom word → (hour, minute)
)

parser = TimeSenseParser(config)
```

Presets: `TimeConfig.default()` and `TimeConfig.strict()`
(`prefer_nearest_future=False`, `default_hour_for_one=1`). Strict mode reads
hours literally in both languages: `at 5` → 05:00, `from 2 to 4` → 02:00–04:00.

For bots on modest hardware: `TimeConfig(use_morph=False)` (or env
`TIMESENSE_MORPH=0`) skips pymorphy3 — ~5× faster, ~2× less RAM, practically
identical results. Invalid language
values raise `ValueError`.

### Production / working calendar

Load a working calendar so that all "business day" logic honours public holidays
(excluded) and transferred working weekends (included):

```python
from timesense import TimeSenseParser, TimeConfig, WorkingCalendar

cal = WorkingCalendar(
    holidays=["2026-02-26", "2026-02-27"],   # non-working days
    working_weekends=["2026-02-28"],          # a Saturday declared working
    holiday_names={"company day": "2026-10-15"},
)
parser = TimeSenseParser(TimeConfig(calendar=cal))
parser.parse("last business day of the month report")  # → 2026-02-28 (skips the holidays)
parser.parse("company day at 6pm party")               # → 2026-10-15 18:00
```

`WorkingCalendar` accepts `date`, `datetime` or `"YYYY-MM-DD"` strings, loads from
`WorkingCalendar.from_dict(...)` / `from_json(path_or_str)`, and exposes
`is_working_day`, `is_holiday`, `next_working_day`, `prev_working_day`,
`resolve_holiday`. With no calendar, a business day is simply Mon–Fri.

## Time zones

By default every `datetime` is **naive**, and phrases with a zone (`at 10 EST`,
`london time`, `UTC`, `GMT+3`) return `None`: without the user's zone there is
nothing to convert to.

Pass the user's zone — `parse(text, tz="Europe/Moscow")`,
`TimeConfig(default_tz=...)` or a tz-aware `now` — and every datetime in the
result becomes tz-aware in that zone, with zone markers in the text converted to it:

```python
p.parse("tomorrow at 10am EST call", tz="Europe/Moscow").when   # 17:00 Moscow time
p.parse("tomorrow at 10 london time call", tz="Asia/Tokyo").when  # 18:00 Tokyo
```

Understood markers include `EST/PST/CET/…`, `london time`, `utc+3`, `GMT+3`, and the
Russian ones listed in the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md).
Durations in hours and minutes stay exact across DST switches (`in 24 hours` is 24
elapsed hours); days and weeks are calendar-based (`in 2 days` keeps the wall-clock
time). Uses stdlib `zoneinfo`; on systems without the IANA database install
`timesense[tz]`. Zones without DST (Moscow etc.) also work without it.

## Holidays

Common holidays are recognised by name and resolved to the nearest upcoming
date; time, deadlines and recurrence then work as usual:

| Phrase | Result |
|---|---|
| `christmas party at 7pm` | December 25, 19:00 |
| `by christmas finish the report` | deadline December 25, 23:59 |
| `on thanksgiving dinner at 6pm` | fourth Thursday of November, 18:00 |
| `easter brunch at 11` | Western Easter (computed) |
| `every christmas call grandma` | yearly on December 25 |
| `by new year finish the project` | deadline **December 31**, 23:59 |
| `on new year's day brunch` | January 1 |
| `by new year at 11:50pm send wishes` | deadline **December 31**, 23:50 |

New Year is a *moment* (January 1, 00:00), so `by / before new year` mean the end
of December 31; the holiday itself (`on new year's day`) is January 1. Other
holidays keep their own day: `by christmas` → December 25.

Built in — EN: New Year's Day/Eve, Christmas (Dec 25) and Christmas Eve, Boxing Day,
Valentine's Day, St. Patrick's Day, Halloween, Independence Day, Thanksgiving,
Easter (Western); Russian: New Year, Old New Year, New Year's night and holidays,
Orthodox Christmas (Jan 7), Defender of the Fatherland Day, International Women's Day,
the May holidays, May Day, Victory Day, Russia Day, Knowledge Day, Unity Day, Orthodox
Easter (see the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md)). Company or local holidays
come from `WorkingCalendar(holiday_names=...)` and take priority.

## Multiple events in one phrase

```python
parser.parse_multi("meeting tomorrow at 10 and lunch at 12")
# [ReminderResult('meeting'), ReminderResult('lunch')]
```

`parse_multi()` splits heuristically on `,` `;` `and` / `then` (and their Russian
equivalents). A separator inside an event title may cause a false split;
`between X and Y` is not split, and a decimal comma (`2,5`) is never treated as a
separator.

Several separate days in one phrase are several events. `parse()` returns `None` for
them (picking one would silently lose the others), `analyze()` reports `multiple`, and
`parse_multi()` returns all of them:

```console
$ python -m timesense --now "2026-09-22 14:00" "on monday, wednesday and friday at 10 call"
on monday, wednesday and friday at 10 call
    not recognized: multiple (several separate events; use parse_multi())
    option: reminder  28.09.2026 10:00  «call»
    option: reminder  23.09.2026 10:00  «call»
    option: reminder  25.09.2026 10:00  «call»
$ python -m timesense --now "2026-09-22 14:00" --multi "on monday, wednesday and friday at 10 call"
reminder  28.09.2026 10:00  «call»
reminder  23.09.2026 10:00  «call»
reminder  25.09.2026 10:00  «call»
```

Recurring forms (`every monday and wednesday`, `on mondays and fridays`) are a single
rule, not a list of events.

A time-only segment **inherits the date of the previous event**:
`"meeting tomorrow at 10 and call at 3pm"` puts both events on tomorrow. Segments
with their own date words (`day after tomorrow`, weekdays, `today`, …) keep their
own anchor.

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
| Modifiers   | `5 times` (COUNT), `until end of March` (UNTIL), `except weekends` (BYDAY), `except december 31` (EXDATE) |
| Series      | `starting october 1 every monday`, `every day from october 1 to october 10`, `every 30 minutes from 9 to 6` |
| Windows     | `after 10 but before 12`, `from morning to noon`, `no earlier than 10am` |
| Deadlines   | `by Friday`, `by 5pm`, `until 6pm`, `before lunch`, `by end of month`, `eod` |
| Open start  | `after 5pm`, `after lunch` |
| Periods     | `in October`, `in 2027`, `next month`, `second week of October`, `this weekend`, `from Monday to Wednesday`, `Sep 25 - Oct 3` |
| Shorthand   | `tmrw`, `eod`, `at 1930`, `7.30pm`, `in 30 secs`, `3 days from now` |

Russian examples are listed in the [Russian README](https://github.com/kruatech/timesense/blob/main/README.ru.md).

## Status, languages & parsing policy

- **Status:** stable (1.1.0). The public API (`parse`, `parse_multi`,
  `TimeConfig`, result types, `detected_language`, `to_dict()`) is frozen;
  breaking changes only in the next major (semver).
- **Python:** 3.9–3.14.
- **Languages:** English and Russian are both fully supported, with the same
  feature set: times and dates, relative and spelled-out expressions
  (`in forty five minutes`, `half past ten`), ranges,
  recurrence → `RRULE`, deadlines, open-start tasks, durations, periods
  (months, years, weekends, parts of a period), time zones, business days,
  chat shorthand (`tmrw`, `eod`), and titles/locations. Both locales follow the
  same parsing policy (smart-hour, `next` weekday, ambiguity → `None`), and
  `human_readable()` speaks the language of the phrase. The language is
  auto-detected (`default_language="auto"`) or set explicitly via
  `parse(text, language=...)`; the chosen language is reported in
  `detected_language`. Digit-only input (`17.02 10:00`) has no language signal
  and falls back to Russian — set `default_language="en"` to change that.
- **Time zones:** opt-in — see [the section above](#time-zones).
- **Nearest future:** a period already over rolls to the next one — `in March` in
  September is March 2027, `in spring` after the season is next year, and
  `beginning of the month` on the 22nd is next month's beginning. Explicit wording
  wins: `beginning of this month`, `early September`, `last week`, `last winter` stay
  where they are said and get `is_past=True` when over.
- **Smart-hour:** a bare hour after the current time is read as the nearest
  future. Example: with `now=14:00`, `"at 10"` → **22:00** today (not 10:00
  tomorrow); bare hours `1–7` shift to PM. Explicit minutes disable this:
  `"at 10:00"` → 10:00 sharp (tomorrow if already past). An explicit day-part
  marker always wins over the heuristics: `"tomorrow at 7 in the morning"` → 07:00,
  `"tomorrow at 3am"` → 03:00. Turn smart-hour
  off with `prefer_nearest_future=False`.
- **"Next" weekday:** plain weekday means the nearest upcoming one; `next` means the
  nearest one **plus a week** — the same convention in both languages. On Saturday,
  `"Friday"` → the coming Friday and `"next Friday"` → a week after it. On the same
  weekday (Tuesday → `"on Tuesday"` / `"next Tuesday"`) both mean a week from today.
  `"next week on Wednesday"` is Wednesday of the next calendar week.
- **Ambiguity:** alternatives (`"monday or tuesday"`, `"at 5 or 6"`) and
  contradictions (`"yesterday and tomorrow"`) return `None`; the options are available via
  `analyze()`. Several separate days (`"on monday, wednesday and friday at 10"`) also
  return `None` from `parse()` — use `parse_multi()`, or `analyze()` (status `multiple`).
- **Reminder / Calendar / Task:** a point in time → `ReminderResult`; an interval
  with start and end → `CalendarResult`; period / deadline / open-start / fuzzy →
  `TaskResult`. Past events are flagged with `is_past=True`.

### Known limitations

- Time zones are applied only when `tz=`, `default_tz` or a tz-aware `now` is given.
- Typos are corrected only in temporal words one letter away from a single known
  word (`firday`, `wensday`); other typos are not guessed.
- The Russian May holidays are built in as May 1–10 without the year-specific
  transfers — set exact dates via `WorkingCalendar(holiday_names=...)`.
- Vague terms with no concrete time (`in a few minutes`, `soon`, `asap`,
  `twice a week`) return `None`:
  the days or the time are not named and are not guessed.
- `parse()` picks a single event; use `parse_multi()` / `analyze_multi()` for
  several. Splitting happens only when every segment is self-contained, so plain
  lists like `buy milk and bread tomorrow` are not broken apart.

## Development & tests

Tests are **not shipped in the wheel** (`pip install timesense` does not
include them), but they **are** included in the source distribution. They
live in the repository; run them from a clone:

```bash
git clone https://github.com/kruatech/timesense
cd timesense
python3 -m venv .venv            # Homebrew/Debian Python forbid pip outside a venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/python -m timesense.tests.test_fixes --fail-only     # RU runner
.venv/bin/python -m timesense.tests.test_en_fixes --fail-only  # EN runner
.venv/bin/python -m pytest -q                                  # full suite incl. RU/EN parity

# release checks
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
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

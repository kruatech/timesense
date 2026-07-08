# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-07-07

Initial public release.

### Highlights

- Natural-language date/time & event parser for **Russian and English** with
  automatic language detection.
- Pure Python 3.9–3.13, **no required dependencies, no ML** — dictionary and
  regex engine: ~0.2 s cold start, a few MB of RAM, <1 ms per phrase. Built
  for turning voice/ASR transcripts into structured events on modest hardware.
- Result classification: `ReminderResult` (point in time), `CalendarResult`
  (start–end interval), `TaskResult` (period / deadline / open-start / fuzzy),
  with `is_past`, `location`, `duration_minutes`, JSON export.
- Recurring events exported as iCalendar `rrule` (`FREQ`, `INTERVAL`, `BYDAY`,
  `BYMONTHDAY`, `BYSETPOS`, `COUNT`, `UNTIL`), with `DTSTART` snapped to the
  first valid occurrence.
- **iCalendar (`.ics`) export** via `result.to_ics()` and
  `to_ics_calendar([...])` — RFC 5545 `VEVENT`s (`DTSTART`/`DTEND`/`RRULE`/
  `SUMMARY`/`LOCATION`), all-day `VALUE=DATE` for periods and deadlines,
  proper escaping and line folding; opens in Google Calendar, Apple Calendar
  and Outlook.
- Fractional intervals: `через 2,5 часа` (decimal comma), `через два с
  половиной часа`, `in an hour and a half`, `in two and a half hours`.
- Deadlines incl. named months: `до конца марта`, `by end of March`.
- Location extraction in both languages: `в офисе`, `at the office`.
- `parse_multi()` splits multi-event phrases; time-only segments inherit the
  date of the previous event (`завтра в 10 встреча и в 15 созвон` → both on
  tomorrow).
- Documented conventions, identical in both languages: smart-hour
  (nearest-future bare hours, explicit day-part markers win), *next weekday* =
  nearest occurrence + 7 days.
- Optional `WorkingCalendar` (holidays / transferred working weekends) for all
  business-day logic; optional `pymorphy3` morphology (`timesense[morph]`).
- Invalid input never raises — out-of-range times (`at 25:00`), impossible
  dates (`31 февраля`), overflow offsets and timezone-bearing phrases return
  `None`.
- Test suite: 1126 cases (RU/EN stress 500 each, semantic runners, regression
  suite), wired into CI across Python 3.9–3.13.

[1.0.0]: https://github.com/kruatech/timesense/releases/tag/v1.0.0

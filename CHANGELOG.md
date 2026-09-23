# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-09-23

A large feature and quality release focused on chat bots and voice assistants:
time zones, holidays, typo tolerance, a diagnostics API, much richer recurrence
(series bounds, excluded dates, hour windows, intervals), RFC-compliant `.ics`,
a command-line tool, and full English/Russian parity checked by tests. The public
API is backward compatible: nothing was removed or renamed, and all new parameters
are optional keyword arguments with defaults. See **Changed** for behaviour that
differs from 1.0.0.

### Added

#### API

- `parser.analyze(text, now, language, tz)` → `ParseAnalysis(result, status, reason,
  alternatives, language)` — the same result as `parse()` plus the reason when nothing
  was recognised. `ParseStatus`: `ok`, `empty`, `too_long`, `no_datetime`, `ambiguous`,
  `invalid_date`, `needs_timezone`, `multiple`. For `ambiguous` (`monday or tuesday`,
  `в 5 или 6`) and `multiple` (`в пн, ср и пт в 10`) the parsed options are in
  `alternatives`, ready to be offered as buttons. `ParseAnalysis.to_dict()` is JSON-ready.
- `parser.analyze_multi()` — the same for several events in one message.
- `result.when` on every result type — the main moment: reminder time, deadline or start.
- `result.summary()` — one line with kind, start, end, duration, recurrence (with excluded
  dates), location, flags and title; labels follow the language of the phrase
  (`min`, `by`, `~approx`, `all day`, `PAST` / `мин`, `до`, `~примерно`, `весь день`,
  `ПРОШЛО`), e.g.
  `reminder ⟳ FREQ=WEEKLY;BYDAY=MO  28.09.2026 10:00  «планёрка»`.
- `parse(..., tz=...)`, `parse_multi(..., tz=...)` and `TimeConfig(default_tz=...)` — the
  user's time zone (IANA name or `tzinfo`); see **Time zones**.
- `TimeConfig(use_morph=False)` or env `TIMESENSE_MORPH=0` — skip pymorphy3: about 5×
  faster and 2× less memory with practically identical results.
- `TimeConfig(max_text_length=1000)` — longer input returns `None` (`None` = no limit).
- `RecurrenceRule.exdates` (excluded occurrences) and `RecurrenceRule.by_hour` (hour window);
  in `to_dict()["recurrence"]` they appear only when present, so every other result keeps
  exactly the 1.0.0 format.
- Command line: `python -m timesense "фраза"` and, after `pip install`, the `timesense`
  command. Flags `--now`, `--tz`, `--lang`, `--multi`, `--json`, `--ics`, `--no-morph`;
  phrases can be piped via stdin; exit code 1 when nothing is recognised (the `analyze()`
  reason and alternatives are printed).
- Extras: `timesense[tz]` (tzdata for systems without the IANA database); `timesense[dev]`
  now also installs `python-dateutil`, `mypy` and `ruff`.

#### Time zones (opt-in)

- With `tz=`, `default_tz` or a tz-aware `now`, every datetime in the result is tz-aware in
  the user's zone. Without them behaviour is unchanged (naive datetimes).
- Zone markers in text are converted to the user's zone: `в 10 мск`, `по Москве`,
  `по московскому времени`, `utc+3`, `мск+2`, `по Киеву/Минску/Алматы/…`, `EST`, `PST`,
  `CET`, `london time`. Without a user zone such phrases still return `None`
  (`analyze()` → `needs_timezone`).
- Durations in hours/minutes stay exact across DST switches (`через 24 часа`,
  `in 24 hours` = 24 elapsed hours); days and weeks stay calendar-based.
- stdlib `zoneinfo`; zones without DST (Moscow etc.) work even without tzdata.

#### Holidays by name

- Resolved to the nearest upcoming date and then parsed as usual (time, deadline, period,
  recurrence). Russian: новый год, старый новый год, новогодняя ночь, новогодние каникулы,
  рождество (Jan 7), 23 февраля, 8 марта, майские (May 1–10), первомай, день Победы,
  день России, день знаний, день народного единства, Пасха (Orthodox, computed).
  English: New Year's Day/Eve, Christmas (Dec 25) and Christmas Eve, Boxing Day,
  Valentine's Day, St. Patrick's Day, Halloween, Independence Day, Thanksgiving (computed),
  Easter (Western, computed).
- `до нового года` / `by christmas` → deadline; `каждый новый год` / `every christmas` →
  yearly; `в новом году` → the whole next year.
- New Year is a moment (January 1, 00:00): `до / к / перед новым годом`,
  `by / before new year` mean the end of December 31; `на новый год` is January 1.
- `WorkingCalendar(holiday_names=...)` is now used by the parser and takes priority over
  built-ins (in 1.0.0 it was stored but ignored).

#### Recurrence

- Several weekdays: `каждый понедельник и среду`, `каждый пн, ср и пт`,
  `every monday and wednesday`, `every monday, wednesday and friday`.
- Intervals in everyday wording: `раз в 2 недели`, `раз в три недели`,
  `каждую вторую/третью неделю`, `по средам через неделю`, `каждый второй месяц`,
  `раз в квартал`, `ежеквартально`, `раз в полгода`, `каждые полгода`, `раз в год`,
  `каждый год`, `раз в день`; `biweekly`, `fortnightly`, `every other week`,
  `every second/third week`, `once every two weeks`, `every quarter`, `quarterly`,
  `every six months`, `every other month`.
- Hourly: `каждый час`, `ежечасно`, `every hour`, `hourly`.
- Hour windows (`BYHOUR`): `каждые 30 минут с 9 до 18`, `каждый час с 9 до 18`,
  `every 30 minutes from 9 to 6`; the first occurrence is the next slot inside the window.
- Frequent rules with weekdays: `каждые 30 минут с 9 до 18 по будням`, `каждый час по субботам`,
  `every 30 minutes from 9 to 6 on weekdays` → `BYDAY` together with `BYHOUR`; the first slot
  is on an allowed day.
- Yearly by position: `каждый год в последнюю пятницу октября`,
  `every year on the last friday of october` → `YEARLY;BYDAY=-1FR;BYMONTH=10`.
- Series bounds: `начиная с 1 октября каждый понедельник`, `каждый понедельник с 1 октября
  по 1 декабря`, `по будням с 5 октября в 9`; `starting october 1 every monday`,
  `every monday from october 1 to december 1` — the first occurrence is not before the
  start date, and the range becomes `UNTIL`.
- Excluded dates (`EXDATE`): `каждый день кроме 31 декабря`, `кроме 1 и 8 января`,
  `за исключением 30 декабря`; `every day except december 31`, `excluding jan 1 and jan 8`.
  Stored at the series' time, so each one matches a real occurrence.
- Excluded weekdays in weekly rules: `каждый будний день кроме пятницы`,
  `every weekday except friday`.
- Monthly: `1 числа каждого месяца`, `раз в месяц 5 числа`, `каждый месяц в последний день`,
  `every 15th`, `every 1st of the month`, `once a month on the 5th`,
  `every last day of the month` (`BYMONTHDAY=-1`), `last business day of every month`
  (`BYSETPOS=-1`), `по чётным / нечётным числам`, `on even / odd days`.
- Yearly with a date: `каждый год 1 сентября`, `every march 5`, `every year on …`.
- Day parts: `каждое утро в 7`, `по вечерам`, `каждую ночь в 2`, `по выходным`,
  `каждые выходные`, `every morning at 7`, `weekdays at 9am`.
- `COUNT` / `UNTIL` are found anywhere after the rule, including after the title
  (`… созвон 5 раз`, `… синк до конца года`) and for rules from any recognizer.

#### Dates, periods and deadlines

- Deadlines: `до 18`, `до 18:00`, `до 6 вечера`, `до обеда`, `перед обедом`,
  `завтра до 18`, `в пятницу до 18:00`, `до 20 октября в 18:00`, `до конца месяца в 18:00`,
  `к концу дня / недели`, `в течение дня / недели`, `в ближайшие 2 часа`,
  `до вторника включительно`; `until 6pm`, `before lunch`, `eod`, `cob`, `by the 20th`,
  `by 5pm on friday`, `within 2 hours`, `in the next 2 hours`, `through tuesday`,
  `from now until friday`.
- Open start: `не раньше 10`, `after 5pm`, `after lunch`, `no earlier than 10am`.
- Time windows: `после 10 но до 12`, `не раньше 10 и не позже 12`, `с утра до полудня`,
  `с обеда до вечера`; `after 10 but before 12`, `from morning to noon`,
  `from lunch to evening`, `from 3 to 4:30pm`.
- "N days before": `за 2 дня до пятницы`, `за 3 рабочих дня до 20 июля`,
  `за неделю до 20 июля`, `за два дня до конца месяца`; `two days before friday`,
  `2 business days before july 20`, `a week before july 20` — the start of that working
  day (09:00). Business days honour `WorkingCalendar`.
- Weeks: `на следующей неделе в среду`, `через 3 недели в понедельник`,
  `next week on wednesday`, `in 3 weeks on monday`, `friday after next`,
  `the week after next`, `two weeks from friday`.
- Periods: months and years without a day (`в октябре`, `в 2027 году`, `in October`,
  `in 2027`), `в следующем месяце`, `next month`, parts of a period
  (`в начале следующего месяца`, `early next week`, `mid October`), week of a named month
  (`на второй неделе октября`, `second week of october`), quarters (`в первом квартале`,
  `в IV квартале`, `in Q1`, `next quarter`), weekends (`на следующих выходных`,
  `this weekend`), `весь день`, `всю неделю`, `the whole week`, weekday and date ranges
  (`пн-пт`, `from monday to wednesday`, `Sep 25 - Oct 3`).
- Dates: `в пн`, `on the 5th`, `25/09`, ISO `2026-10-01T09:00`, `day before yesterday`,
  `позавчера`, `first/last day of the month`, `last night`, `this morning`.

#### Times and day parts

- Exact time next to a day part: `сегодня вечером в 20`, `завтра утром в 8:30`,
  `tonight at 8:30`, `this evening at 7:30`.
- Spoken and written forms: `в 11 30`, `в 10-00`, `в 10ч30`, `в 1930`, `без 15 десять`,
  `в двадцать три ноль ноль`, `через час пятнадцать`, `через 30 секунд`, `at 1930`,
  `7.30pm`, `at half 10`, `in an hour fifteen`, `in 30 secs`, `around 5`, `5ish`,
  `at 5 sharp`, `в районе 5`.
- Durations: `на полтора часа`, `минут на 20`, `длительностью 2 часа`, `for 1.5 hours`,
  `for an hour and a half`, `lasting 2 hours`.
- `ближе к вечеру` / `towards evening` → 17:00–21:00; `вечерком`, `утречком`, `рано утром`.

#### Typos, chat shorthand, mixed input

- Typos in temporal words: `завтро`, `севодня`, `седня`, `понедельнек`, `пятницк`,
  `сентебря`, `firday`, `satruday`, `thurday`, `wensday`, `tomorow`, `ocotber` —
  conservatively (one edit away from a single known word; known words such as `вечера`,
  `завтрак`, `fridge` are never "corrected").
- Chat shorthand: `tmrw`, `2moro`, `eod`, `через пару часов`, `a couple of hours`,
  `3 days from now`, Russian relative days inside English (`завтра at 10`).

#### Titles

- `remind me [to]`, `set a reminder to`, `напомни [мне]` are not part of the title.
- A preposition stays with its own word (`к врачу`, `на тренировку`, `с командой`,
  `to the doctor`, `with the team`) and is dropped only when it pointed at consumed text
  (`встреча на 2 часа` → `встреча`). English titles keep inner words and original casing.
- No leftovers: `включительно`, `начиная`, `ближе`, `потом`, `затем`, `inclusive`,
  `starting`, `towards`, `early/late`, `рано/поздно`.
- `human_readable()` speaks the language of the phrase (`by …`, `after …`, `soon`).

#### Calendar export (`.ics`)

- Recurring events in a user zone get `DTSTART;TZID=…` and a generated `VTIMEZONE`
  (DST rules derived from the IANA database; cross-checked with dateutil for Europe,
  North America, Australia, New Zealand and zones without DST).
- `EXDATE` for excluded dates, of the same type as `DTSTART`.
- `to_ics(result, alarm_minutes=15)` / `to_ics_calendar(..., alarm_minutes=...)` → `VALARM`.

#### Quality and tooling

- New test suites: `test_parity.py` (87 RU/EN phrase pairs must give identical results),
  `test_hard_cases.py` (combined phrases with independently computed answers),
  `test_robustness.py` (fuzzing, mutated phrases, determinism, thread safety, latency
  budget — `TIMESENSE_SKIP_PERF=1` to skip), `test_docs.py` (every CLI example in both
  READMEs is run and compared verbatim), `test_super_hard.py` (32 super-hard combined
  phrases), `test_past.py` (past and historic dates), `test_prod_fixes.py`.
  1916 tests in total.
- CI matrix `.github/workflows/timesense-matrix.yml`: Python 3.9–3.14 × morphology on/off,
  Windows without tzdata, and a `typecheck` job (`mypy`, `ruff`).
- The package (marked `py.typed`) passes `mypy` with no errors.
- Python 3.14 supported.
- Documentation: `README.md` (English only, with a link to the Russian docs) and
  `README.ru.md` have the same structure and content, with reproducible CLI examples.

### Changed

Behaviour that differs from 1.0.0 — check these if you rely on exact results:

- `до 18 …` / `до 18:00 …` is now a deadline (`TaskResult`, `task_type=deadline`), not a
  reminder at 18:00.
- Alternatives (`в понедельник или вторник`, `в 5 или 6`, `monday or tuesday`) return
  `None` instead of silently picking the first; the options are in `analyze()`.
- Several separate days (`в пн, ср и пт в 10`, `on monday, wednesday and friday at 10`)
  return `None` from `parse()` instead of only the first day; `parse_multi()` returns all of
  them, `analyze()` reports `multiple`.
- English bare hours follow the documented smart-hour rule like Russian:
  `at 10` at 14:00 → 22:00 today (was 10:00 tomorrow).
- English clock idioms follow the Russian hour rule: `half past four` → 16:30
  (was 04:30 tomorrow), `4 o'clock` → 16:00.
- English `every N minutes/hours` is a `ReminderResult` starting now (was a `TaskResult`).
- English `N business days before end of month` is the 09:00 point of that day, like
  Russian (was a 23:59 deadline).
- Nearest-future also applies to seasons and parts of a period: `весной` on Dec 31 is next
  spring; `в начале месяца` on the 22nd is next month's beginning. Explicit forms
  (`в начале этого месяца`, `в начале сентября`) stay as said and get `is_past=True`.
- `до / by new year` → December 31 (was January 1).
- `TimeConfig.strict()` reads hours literally in Russian too (`в 5` → 05:00); the 1–7 → PM
  shift used to be hardcoded.
- One-off events that ended before `now` get `is_past=True` (explicit past dates, passed
  deadlines, today's morning in the afternoon); empty series (`UNTIL` before the start) too.
- The beginning/middle/end window of quarters and years is 9 days in both languages
  (Russian used up to 40 days: `в конце года` started on November 21).
- Titles: prepositions stay with their word (`к врачу` instead of `врачу`); English titles
  keep articles and casing (`call the client`, `lunch with Anna`).

### Fixed

- A tz-aware `now` crashed with `TypeError` on phrases like `завтра в 10`.
- `.ics` RFC 5545: `DTSTAMP` is now UTC with `Z` (was floating in every event); `UNTIL` is
  a DATE for all-day series; recurring events with `TZID` now have a `VTIMEZONE`.
- Silently wrong dates, among others: `с 1 октября` read as 01:00; `в последнюю неделю
  октября` → the last week of the current month; `second week of october` → Oct 25–31;
  `в пн в 10` ignored the weekday; `на следующей неделе в среду` → this week's Wednesday;
  `next week on wednesday` / `last week on thursday` → Monday; `25/09` dropped the date;
  `day before yesterday` → yesterday; `this afternoon` at 14:00 → tomorrow;
  `beginning of next month` → the current month; `в 1 квартале` → 01:00;
  `завтро в 10` → today 22:00; `в двадцать три ноль ноль` → 20:03;
  `созвон минут на 20` → October 20; `в выходные в 10` → today 22:00;
  `за 2 дня до пятницы` → Friday; `до нового года в 23:50` → today 23:50;
  `в последний рабочий день месяца в 17` → today 17:00.
- Lost information: recurrence dropped in `каждые 30 минут с 9 до 18`, `каждое утро в 7`
  (was 19:00, no rule), `каждый год 1 сентября`, `каждые выходные`; the second weekday in
  `каждый понедельник и среду`; excluded weekdays and dates; `COUNT` / `UNTIL` after the
  title; the start in `после 10 но до 12`; the time in `сегодня вечером в 20`,
  `by friday 18:00`; the interval in `каждую вторую неделю по средам`.
- Exclusion without a series (`кроме 31 декабря`, `except december 31`) is no longer read as
  an event on that date.
- `в середине октября` had stray seconds; `через 2 дня` / `за два дня` produced a bogus
  12:00–17:00 day part from the word `дня`.
- Russian dates dropped any year before 2020 (`12 апреля 1961 года`, `12.04.1961`,
  `1961-04-12` were moved to the next April); years 1900–2199 are now kept (an amount such
  as `10 октября 2000 рублей` is not read as a year).
- Past and history: `в 1945 году` used to become today 19:45 (a year read as a compact
  time); `с 22 июня 1941 по 9 мая 1945`, `from june 22 1941 to may 9 1945` kept only the
  start; `прошлой зимой`, `прошлым летом`, `last winter`, `last summer` gave the *next*
  season (`этой` / `следующей` / `this` / `next` are handled too, including during the
  season itself); `3 года назад` gave one year ago; `N месяцев / лет назад` were not
  supported in Russian.
- A time range split by a date — `с 9 утра 12 апреля 1961 года до 11 утра`,
  `с 10 завтра до 12`, `from 9am on april 12 1961 to 11am`, `from 10pm on december 31 to
  2am` — used to keep only the start; it is now a calendar event on that date (crossing
  midnight when the end is earlier). Noon and midnight work as range bounds:
  `с 10 до полудня`, `с полудня до 15`, `с 22 до полуночи`, `from 10am to noon`,
  `from noon to 3pm`, `from 10pm to midnight` (they used to become deadlines or a single time).
- From a 32-phrase super-hard check: `в последний рабочий день каждого месяца в 17` lost the
  recurrence; `за 2 рабочих дня до конца месяца в 10` ignored the time; `каждые 30 минут … по
  будням` lost the 30-minute frequency (both languages); `half past six pm` lost the time;
  `по субботам` after a frequent rule was read as `UNTIL` Saturday.
- A regression test in 1.0.0 encoded a wrong date (`last week on Thursday` → Monday); corrected.

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

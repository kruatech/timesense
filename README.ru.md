# TimeSense

**Языки:** [English](https://github.com/kruatech/timesense/blob/main/README.md) · **Русский**

[![CI](https://github.com/kruatech/timesense/actions/workflows/ci.yml/badge.svg)](https://github.com/kruatech/timesense/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/timesense.svg)](https://pypi.org/project/timesense/)
[![Python](https://img.shields.io/pypi/pyversions/timesense.svg)](https://pypi.org/project/timesense/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://pypi.org/project/timesense/)
[![No ML](https://img.shields.io/badge/ML%20models-none-blue)](#почему-timesense)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/kruatech/timesense/blob/main/LICENSE)

Парсер дат, времени и событий из естественного языка для **русского и английского**.

TimeSense превращает фразы вроде `«завтра в 10 встреча»`, `«с 9 до 17 работа»`
или `«каждый понедельник планёрка»` — и их английские эквиваленты — в
структурированные объекты событий, готовые к экспорту в JSON, iCalendar
`rrule` или полноценный файл `.ics`. Это **чистый Python** **без обязательных зависимостей**, созданный для
превращения голосовых/ASR-транскриптов в структурированные даты.

Внутри **нет машинного обучения** — движок построен на словарях и регулярных
выражениях. Ему не нужен GPU, он не скачивает модели и спокойно работает на
самом дешёвом VPS, плате класса Raspberry Pi или внутри serverless-функции:
холодный старт ~0,2 с, несколько МБ памяти и меньше миллисекунды на фразу
(1000+ фраз/сек на одном скромном ядре). Поэтому его можно вызывать инлайн на
каждой реплике живого пайплайна транскрибации: на входе — вывод
speech-to-text, на выходе — готовые для календаря события.

| Footprint | |
|---|---|
| Обязательные зависимости | **0** — чистый Python 3.9–3.13, только stdlib |
| ML-модели / GPU | **нет** — словари и регулярные выражения |
| Холодный старт | ~0,2 с (интерпретатор + импорт) |
| Память | несколько МБ |
| Латентность | **<1 мс** на фразу — 1000+ фраз/сек на одном скромном ядре |
| Развёртывание | самый дешёвый VPS · платы класса Raspberry Pi · serverless |

```python
from datetime import datetime
from timesense import TimeSenseParser

parser = TimeSenseParser()
r = parser.parse("завтра в 10 встреча", now=datetime(2026, 2, 14, 14, 0))

type(r).__name__     # 'ReminderResult'
r.title              # 'встреча'
r.human_readable()   # '15.02.2026 10:00'
r.to_dict()
# {'type': 'reminder', 'title': 'встреча', 'source': 'завтра в 10 встреча',
#  'confidence': 0.9, 'is_past': False, 'language': 'ru',
#  'datetime': '2026-02-15T10:00:00'}
```

Английский работает из коробки — язык определяется автоматически:

```python
parser.parse("every Monday at 10 standup").to_dict()["recurrence"]["rrule"]
# 'FREQ=WEEKLY;BYDAY=MO'
```

## Почему TimeSense?

| | **TimeSense** | Классические date-парсеры¹ | LLM / ML-пайплайны |
|---|:---:|:---:|:---:|
| Даты и время из свободного текста | ✅ | ✅ | ✅ |
| Классификация события (напоминание / календарь / задача) | ✅ | ❌ | 🟡 зависит от промпта |
| Повторения → RFC 5545 `RRULE` | ✅ | ❌ | 🟡 |
| Готовый к импорту `.ics` | ✅ | ❌ | ❌ |
| Извлечение названия и места события | ✅ | ❌ | ✅ |
| Ноль зависимостей | ✅ | ❌ | ❌ |
| Детерминизм (один вход → один выход) | ✅ | ✅ | ❌ |
| Без GPU, без скачивания моделей, полностью офлайн | ✅ | ✅ | ❌ |
| Работает на железе класса Raspberry Pi | ✅ | ✅ | ❌ |

¹ например `dateparser`, `parsedatetime` — отлично достают `datetime`, но на этом останавливаются.

**Содержание:**
[Возможности](#возможности) ·
[Установка](#установка) ·
[Быстрый старт](#быстрый-старт) ·
[Витрина](#витрина-сложные-фразы) ·
[Типы результатов](#типы-результатов) ·
[Повторения](#повторяющиеся-события-rrule) ·
[Экспорт .ics](#экспорт-в-календарь-ics) ·
[Конфигурация](#конфигурация) ·
[Несколько событий](#несколько-событий-в-одной-фразе) ·
[Паттерны](#поддерживаемые-паттерны-выдержка) ·
[Политика парсинга](#статус-языки-и-политика-парсинга) ·
[Разработка](#разработка-и-тесты)

## Возможности

- **Время:** `в 15:30`, `в 10 утра`, `без пяти десять`, `в полдень`, `в полночь`
  · EN: `at 5pm`, `9:30am`, `at 17:00`, `noon`, `half past ten`, `quarter to eight`.
- **Относительные:** `через 2 часа`, `через час`, `через полтора часа`,
  `через 2,5 часа` (десятичная запятая), `через два с половиной часа`,
  `через неделю`, `5 минут назад` · EN: `in 2 hours`, `in an hour and a half`,
  `in forty five minutes`, `tomorrow`, `next Friday`.
- **Даты:** `10 января`, `первого сентября`, `15 числа`, `в пятницу`
  · EN: `Feb 17`, `March 3rd`, `3/17`, ISO `2026-02-17`.
- **Диапазоны → `CalendarResult`:** `с 9 до 10`, `с десяти до одиннадцати`,
  `с понедельника по среду` · EN: `from 9 to 5`, `9am-11am`, `between 10 and 12`.
- **Повторения → `rrule`:** `каждый понедельник`, `по будням`,
  `каждые 2 недели`, `каждый месяц 15 числа` · EN: `every day`, `every weekday`,
  `every 2 weeks on Monday`, `N times` (COUNT), `until end of March` (UNTIL),
  `except weekends` (BYDAY).
- **Дедлайны:** `до пятницы`, `до конца марта`, `не позднее 20-го`,
  `в течение часа` · EN: `by Friday`, `by 5pm`, `by end of month`,
  `by end of March`.
- **Длительность и место:** `на 2 часа`, `в офисе` · EN: `for 2 hours`,
  `at the office`.
- **Классификация результата:** напоминание / событие календаря / задача,
  с `is_past`, `detected_language`, экспортом в JSON и `rrule`.

## Установка

```bash
pip install timesense
```

Без зависимостей — чистый Python (3.9–3.13). Морфология опциональна: без неё
парсер использует встроенные словари словоформ. Для улучшенной русской
лемматизации:

```bash
pip install "timesense[morph]"   # подтянет pymorphy3
```

## Быстрый старт

`parse()` возвращает один объект (`ReminderResult` / `CalendarResult` /
`TaskResult`) или `None`, если дата/время не найдены. Точку отсчёта задаёт
параметр `now`, язык — параметр `language=` (иначе автоопределение):

```python
from datetime import datetime
from timesense import TimeSenseParser

parser = TimeSenseParser()
now = datetime(2026, 2, 14, 14, 0)

parser.parse("через сорок пять минут позвонить", now=now)  # ReminderResult 14:45
parser.parse("с 9 до 17 работа", now=now)                  # CalendarResult 09:00–17:00
parser.parse("по будням в 9 планёрка", now=now)            # rrule FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
parser.parse("в 10 мск созвон", now=now)                   # None (таймзоны не поддерживаются)
parser.parse("завтра в 10", now=now, language="ru")        # явный язык
```

## Витрина: сложные фразы

Одна фраза может нести правило повторения, время, место и название сразу —
а тип результата выбирается автоматически. Все ответы ниже настоящие
(`now = 2026-07-06 15:41`, понедельник):

```python
# Повторение + время + место → ReminderResult с RRULE
p.parse("каждую вторую пятницу месяца в 18:30 ретро в переговорке")
# ReminderResult · title='ретро' · location='в переговорке'
# datetime=2026-07-10 18:30 · rrule='FREQ=MONTHLY;BYDAY=2FR'

# Диапазон через полночь → CalendarResult
p.parse("в следующий вторник с 23:15 до 00:45 проверить ночное окно работ")
# CalendarResult · 2026-07-14 23:15 → 2026-07-15 00:45 · duration_minutes=90

# Арифметика рабочих дней → TaskResult
p.parse("за два рабочих дня до конца месяца напомнить про закрывающие документы")
# TaskResult · start=2026-07-29 09:00

# Сезон → TaskResult (нечёткий период)
p.parse("осенью подготовить крупный релиз")
# TaskResult · 2026-09-01 → 2026-11-30

# Разные типы в одной строке → parse_multi
p.parse_multi("до конца месяца закрыть финансовые документы, "
              "каждый понедельник проверять риски")
# TaskResult(дедлайн 31.07.2026 23:59)
# · TaskResult(rrule='FREQ=WEEKLY;BYDAY=MO')
```

## Типы результатов

У всех результатов общий интерфейс: `.title`, `.source`, `.confidence`,
`.is_past`, `.location`, `.duration_minutes`, `.recurrence`, `.exclusions`,
`.detected_language`, `.event_type` (enum `EventType`), плюс `.to_dict()` и
`.human_readable()`.

### `ReminderResult` — точка во времени

```python
r = parser.parse("в 15:30 синк")
r.datetime_at        # datetime(..., 15, 30)
```

### `CalendarResult` — событие с началом и концом

```python
r = parser.parse("с 10 до 11 синк")
r.start_at           # datetime(..., 10, 0)
r.end_at             # datetime(..., 11, 0)
r.duration_minutes   # 60
```

### `TaskResult` — задача (период / дедлайн / open-start / нечёткая)

```python
from timesense import TaskType

r = parser.parse("до пятницы сдать отчёт")
r.task_type          # TaskType.PERIOD | DEADLINE | OPEN_START | FUZZY
r.deadline           # datetime дедлайна (для TaskType.DEADLINE)
r.start_at, r.end_at # начало/конец, где применимо
r.fuzzy              # bool
```

## Повторяющиеся события (`rrule`)

```python
r = parser.parse("каждый понедельник планёрка")
r.recurrence.to_rrule()      # 'FREQ=WEEKLY;BYDAY=MO'
r.to_dict()["recurrence"]
# {'frequency': 'WEEKLY', 'interval': 1, 'by_day': ['MO'],
#  'until': None, 'count': None, 'rrule': 'FREQ=WEEKLY;BYDAY=MO'}

parser.parse("каждую пятницу до 31 марта синк").recurrence.to_rrule()
# 'FREQ=WEEKLY;BYDAY=FR;UNTIL=20260331T235900'   (naive: без завершающей Z)
```

Стартовая дата всегда удовлетворяет собственному правилу: у повторений с
`BYDAY`/`BYMONTHDAY` `DTSTART` снапится на первое валидное вхождение.

## Экспорт в календарь (`.ics`)

Любой результат — или целый список — можно выгрузить в файл iCalendar,
который открывается в Google Calendar, Apple Calendar и Outlook:

```python
from timesense import TimeSenseParser, to_ics_calendar

p = TimeSenseParser()
events = [
    p.parse("каждый понедельник в 10 планёрка", language="ru"),
    p.parse("в пятницу с 18:00 до 20:00 встреча", language="ru"),
]
with open("events.ics", "w", encoding="utf-8") as f:
    f.write(to_ics_calendar(events))

# одно событие:
p.parse("завтра в 10 позвонить клиенту", language="ru").to_ics()
```

`VEVENT` по RFC 5545 содержат `DTSTART`/`DTEND`/`RRULE`/`SUMMARY`/`LOCATION`.
Периоды и дедлайны выгружаются как события на весь день (`VALUE=DATE`); текст
экранируется, длинные строки сворачиваются согласно стандарту.

## Конфигурация

```python
from timesense import TimeSenseParser, TimeConfig

config = TimeConfig(
    prefer_nearest_future=True,   # прошедшее время сдвигать в ближайшее будущее
    default_hour_for_one=13,      # «в час» → 13:00
    default_language="auto",      # "auto" | "ru" | "en"
    timezone="Asia/Yekaterinburg",  # хранится, но НЕ применяется — datetime наивные
    working_hours={"start": 9, "end": 18},
    custom_times={"летучка": (11, 30)},  # своё слово → (час, минута)
)

parser = TimeSenseParser(config)
```

Пресеты: `TimeConfig.default()` и `TimeConfig.strict()`
(`prefer_nearest_future=False`, `default_hour_for_one=1`). Невалидные значения
языка вызывают `ValueError`.

### Производственный календарь

Подключите рабочий календарь, чтобы логика «рабочих дней» учитывала праздники
(исключаются) и перенесённые рабочие субботы (включаются):

```python
from timesense import TimeSenseParser, TimeConfig, WorkingCalendar

cal = WorkingCalendar(
    holidays=["2026-02-26", "2026-02-27"],   # нерабочие дни
    working_weekends=["2026-02-28"],          # рабочая суббота
    holiday_names={"новый год": "2026-01-01"},
)
parser = TimeSenseParser(TimeConfig(calendar=cal))
parser.parse("последний рабочий день месяца отчёт")  # → 2026-02-28 (праздники пропущены)
```

`WorkingCalendar` принимает `date`, `datetime` или строки `"YYYY-MM-DD"`,
загружается через `WorkingCalendar.from_dict(...)` / `from_json(path_or_str)`
и предоставляет `is_working_day`, `is_holiday`, `next_working_day`,
`prev_working_day`, `resolve_holiday`. Без календаря рабочий день — просто
пн–пт.

## Несколько событий в одной фразе

```python
parser.parse_multi("завтра в 10 встреча и в 12 обед")
# [ReminderResult('встреча'), ReminderResult('обед')]
```

`parse_multi()` разбивает эвристически по `,` `;` `« и »` (ru) и
`and` / `then` (en). Разделитель внутри названия события может дать ложное
разбиение; `between X and Y` не разбивается, а десятичная запятая
(`через 2,5 часа`) никогда не считается разделителем.

Сегмент, содержащий только время, **наследует дату предыдущего события**:
`«завтра в 10 встреча и в 15 созвон»` ставит оба события на завтра. Сегменты
со своими датными словами (`послезавтра`, дни недели, `сегодня`/`today`, …)
сохраняют собственную привязку.

## Поддерживаемые паттерны (выдержка)

| Категория   | Примеры (RU) |
|-------------|--------------|
| Время       | `в 17:00`, `в 10 утра`, `в полдень`, `в полночь` |
| Словами     | `в десять тридцать`, `половина одиннадцатого`, `без четверти восемь` |
| Относительные | `через 2 часа`, `через сорок пять минут`, `через 3 дня` |
| Даты        | `17 февраля`, `третьего марта`, `15 числа`, `2026-02-17` |
| Дни недели  | `в следующую пятницу`, `в этот понедельник`, `в пятницу` |
| Диапазоны   | `с 9 до 17`, `с десяти до одиннадцати`, `между 10 и 12` |
| Повторения  | `каждый день`, `по будням`, `каждые 2 недели по понедельникам`, `каждый месяц 15 числа` |
| Модификаторы | `5 раз` (COUNT), `до конца марта` (UNTIL), `кроме выходных` (BYDAY) |
| Дедлайны    | `до пятницы`, `к 17:00`, `до конца месяца` |

Английские примеры — в [английском README](https://github.com/kruatech/timesense/blob/main/README.md).

## Статус, языки и политика парсинга

- **Статус:** stable (1.0.0). Публичный API (`parse`, `parse_multi`,
  `TimeConfig`, типы результатов, `detected_language`, `to_dict()`) заморожен;
  ломающие изменения — только в следующем мажоре (semver).
- **Python:** 3.9–3.13.
- **Языки:** русский — основная, самая полная локаль; английский — отдельная
  локаль (`timesense/locales/en.py`), покрывающая базовую грамматику, включая
  числа словами (`in forty five minutes`, `at ten thirty`, `half past ten`,
  `quarter to eight`, `from nine to five`, `every forty five minutes`). Язык
  определяется автоматически (`default_language="auto"`) или задаётся явно
  через `parse(text, language=...)`; выбранный язык возвращается в
  `detected_language`.
- **Часовые пояса:** не поддерживаются. Все `datetime` — **наивные** (без
  `tzinfo`). `TimeConfig.timezone` хранится, но не применяется. Фразы с
  зонами (`в 10 мск`, `UTC`, `GMT+3`) намеренно возвращают `None`.
- **Smart-hour:** голый час после текущего времени читается как ближайшее
  будущее. Пример: при `now=14:00` `«в 10»` → **22:00** сегодня (не 10:00
  завтра); голые часы `1–7` сдвигаются в PM. Явные минуты отключают это:
  `«в 10:00»` → ровно 10:00 (завтра, если уже прошло). Явный маркер времени
  суток всегда побеждает эвристику: `«завтра в 7 утра»` → 07:00,
  `«завтра в 3 ночи»` → 03:00, `"tomorrow at 3am"` → 03:00. Smart-hour
  отключается через `prefer_nearest_future=False`.
- **«Следующий» день недели:** просто день недели означает ближайший
  предстоящий; `следующий` / `next` — ближайший **плюс неделя**; конвенция
  едина для обоих языков. В субботу `«в пятницу»` → ближайшая пятница, а
  `«в следующую пятницу»` / `"next Friday"` → на неделю позже неё.
- **Reminder / Calendar / Task:** точка во времени → `ReminderResult`;
  интервал с началом и концом → `CalendarResult`; период / дедлайн /
  open-start / нечёткое → `TaskResult`. Прошедшие события помечаются
  `is_past=True`.

### Известные ограничения

- Часовые пояса не применяются (наивные datetime).
- Числа словами поддерживаются, включая составные и развёрнутые формы
  (`через сорок пять минут`, `с девяти до пяти`, `в десять часов пятнадцать
  минут`, `час пятнадцать`, `с двух до половины четвёртого`). Отдельные редкие
  разговорные формы (например, английское `"ten fifteen"` без `at`/идиомы)
  требуют явной записи.
- `parse_multi()` разбивает на несколько событий, только когда каждый сегмент
  самодостаточен (парсится сам по себе); иначе возвращается один результат —
  списки вроде `«купить хлеб и молоко завтра»` не разрываются.
- Праздники «по названию» без календаря и исправление опечаток вне скоупа
  (возвращается `None`).

## Разработка и тесты

Тесты **не поставляются в wheel** (`pip install timesense` их не включает),
но **входят** в исходный дистрибутив (sdist). Они живут в репозитории;
запускайте из клона:

```bash
git clone https://github.com/kruatech/timesense
cd timesense
pip install -e ".[dev]"

python -m timesense.tests.test_fixes --fail-only     # RU-раннер
python -m timesense.tests.test_en_fixes --fail-only  # EN-раннер
pytest -q                                            # обёртки + EN pytest-набор

# релизные проверки
python -m build
python -m twine check dist/*
```

Примеры запускаются модулем из корня репозитория:

```bash
python -m examples.basic_usage
```

## Участие в разработке

Pull request'ы приветствуются. Для крупных изменений сначала откройте issue.
См. [CONTRIBUTING.md](https://github.com/kruatech/timesense/blob/main/CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](https://github.com/kruatech/timesense/blob/main/CODE_OF_CONDUCT.md)
и [SECURITY.md](https://github.com/kruatech/timesense/blob/main/SECURITY.md).

## Лицензия

MIT — см. [LICENSE](https://github.com/kruatech/timesense/blob/main/LICENSE).

## Автор и контакты

**Anton Krutilin**

- GitHub: <https://github.com/kruatech>
- Telegram: [@kruatech](https://t.me/kruatech)
- Email: a@krutilin.pro

Баги и предложения: <https://github.com/kruatech/timesense/issues>

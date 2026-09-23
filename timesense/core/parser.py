"""Основной парсер"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from .config import TimeConfig
from .tokenizer import Tokenizer
from .language import resolve_language
from .tz import TzLike, find_tz_marker, resolve_tz
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule
from ..models.event_types import CalendarResult, ReminderResult, TaskResult, TaskType
from ..recognizers.date import DateRecognizer
from ..recognizers.date_format import DateFormatRecognizer
from ..recognizers.time import TimeRecognizer
from ..recognizers.range import RangeRecognizer
from ..recognizers.relative import RelativeRecognizer
from ..recognizers.recurrence import RecurrenceRecognizer
from ..recognizers.combined import CombinedRecognizer
from ..recognizers.period import PeriodRecognizer
from ..recognizers.season import SeasonRecognizer
from ..recognizers.duration import DurationRecognizer
from ..recognizers.open_start import OpenStartRecognizer
from ..recognizers.deadline_synonym import DeadlineSynonymRecognizer
from ..recognizers.weekday_modifier import WeekdayModifierRecognizer
from ..recognizers.week_weekday import WeekWeekdayRecognizer
from ..recognizers.calendar_period import CalendarPeriodRecognizer
from ..recognizers.working_context import WorkingContextRecognizer
from ..recognizers.working_days import WorkingDaysRecognizer
from ..recognizers.custom_time import CustomTimeRecognizer
from ..recognizers.ordinal_day import OrdinalDayRecognizer
from ..recognizers.exclusion import ExclusionParser
from ..recognizers.location import LocationExtractor
from ..recognizers.time_of_day import TimeOfDayRecognizer
from ..dict.keywords import Keywords
from ..dict.morph_adapter import get_morph
from typing import Dict, List, Optional, Union

ParseResult = Union[ReminderResult, CalendarResult, TaskResult]

logger = logging.getLogger("timesense")


class TimeSenseParser:
    def __init__(self, config: Optional[TimeConfig] = None) -> None:
        self.config = config or TimeConfig()
        self.tokenizer = Tokenizer(get_morph(getattr(self.config, "use_morph", None)))
        self._init_recognizers()
        from ..locales.en import EnglishLocaleParser

        self._en = EnglishLocaleParser(self.config)

    def _init_recognizers(self):
        c = self.config
        self.recognizers = [
            DateFormatRecognizer(c),
            CombinedRecognizer(c),
            WeekWeekdayRecognizer(c),
            CalendarPeriodRecognizer(c),
            WeekdayModifierRecognizer(c),
            OrdinalDayRecognizer(c),
            RangeRecognizer(c),
            RecurrenceRecognizer(c),
            DeadlineSynonymRecognizer(c),
            WorkingDaysRecognizer(c),
            RelativeRecognizer(c),
            DateRecognizer(c),
            TimeRecognizer(c),
            PeriodRecognizer(c),
            SeasonRecognizer(c),
            DurationRecognizer(c),
            OpenStartRecognizer(c),
            WorkingContextRecognizer(c),
            CustomTimeRecognizer(c),
            TimeOfDayRecognizer(c),
        ]

    def parse_multi(
        self,
        text: str,
        now: Optional[datetime] = None,
        language: Optional[str] = None,
        tz: TzLike = None,
    ) -> List[ParseResult]:
        """Эвристически разбивает фразу на несколько событий по разделителям
        ',', ';', ' и ' и парсит каждый сегмент отдельно.

        Возвращает список результатов (ReminderResult/CalendarResult/TaskResult),
        пустые сегменты и None отбрасываются. Если разбиение не дало ни одного
        результата — возвращает одиночный разбор всей фразы (список из 0/1).

        Ограничение: разделители эвристические; 'и'/',' внутри названия события
        могут привести к ложному разбиению.
        """
        import re as _re

        if language is not None and language not in ("auto", "ru", "en"):
            raise ValueError("language must be 'auto', 'ru', 'en' or None, got %r" % (language,))
        if not text or not text.strip():
            return []
        if self._too_long(text):
            return []
        user_tz = self._user_tz(tz, now)
        now = self._local_now(now, user_tz)
        if user_tz is not None:
            tz = user_tz
        enum = self._enumerated_days(text)
        if enum:
            res: List[ParseResult] = []
            for t in enum:
                one = self.parse(t, now=now, language=language, tz=tz)
                if one is not None:
                    one.source = text
                    res.append(one)
            return res
        # Разделители: ',', ';', ' и ' (ru), ' and '/' then ' (en).
        # Запятая МЕЖДУ цифрами — десятичный разделитель («через 2,5 часа»),
        # не граница событий. ' and ' не трогаем, если во фразе есть 'between'
        # (там 'X and Y' — диапазон).
        sep = r"\s*;\s*|\s*(?<![0-9]),\s*|\s*,(?![0-9])\s*|\s+и\s+|\s+then\s+"
        if "between" not in text.lower():
            sep += r"|\s+and\s+"
        segments = _re.split(sep, text)
        seg_list = [s.strip() for s in segments if s and s.strip()]
        # Делим на несколько событий ТОЛЬКО если каждый сегмент самодостаточен
        # (парсится в результат). Иначе «купить хлеб и молоко завтра» — это один
        # список дел, а не два события: возвращаем единый разбор всей фразы,
        # не теряя элементы.
        if len(seg_list) >= 2:
            parsed = [self.parse(s, now=now, language=language, tz=tz) for s in seg_list]
            if all(r is not None for r in parsed):
                self._chain_multi_dates(seg_list, parsed, now, language)
                return [r for r in parsed if r is not None]
        single = self.parse(text, now=now, language=language, tz=tz)
        return [single] if single is not None else []

    # слова, при которых сегмент НЕ наследует дату предыдущего события
    _ANCHOR_WORDS = ("сегодня", "вчера", "сейчас", "today", "tonight", "yesterday", "right now")
    # маркеры собственной даты сегмента: при их наличии дата не наследуется
    _OWN_DATE_RE = None  # компилируется лениво в _seg_has_own_date

    @classmethod
    def _seg_has_own_date(cls, seg_low):
        """True, если в сегменте есть собственный маркер даты (день недели,
        «завтра», название месяца, числовая дата, относительный сдвиг и т.п.)."""
        import re as _re

        if cls._OWN_DATE_RE is None:
            words = [
                # RU относительные/дни
                r"завтра",
                r"послезавтра",
                r"сегодня",
                r"вчера",
                r"позавчера",
                r"через",
                r"назад",
                r"числ[ао]",
                r"следующ\w*",
                r"прошл\w*",
                r"ближайш\w*",
                r"выходн\w*",
                r"будн\w*",
                r"недел\w*",
                r"месяц\w*",
                r"год[ау]?",
                r"квартал\w*",
                r"понедельник\w*",
                r"вторник\w*",
                r"сред[ауые]",
                r"четверг\w*",
                r"пятниц\w*",
                r"суббот\w*",
                r"воскресень\w*",
                r"январ\w*",
                r"феврал\w*",
                r"март\w*",
                r"апрел\w*",
                r"ма[еяю]",
                r"июн\w*",
                r"июл\w*",
                r"август\w*",
                r"сентябр\w*",
                r"октябр\w*",
                r"ноябр\w*",
                r"декабр\w*",
                # EN
                r"tomorrow",
                r"today",
                r"tonight",
                r"yesterday",
                r"in\s+\d",
                r"next",
                r"last",
                r"this",
                r"week",
                r"month",
                r"year",
                r"mon(?:day)?",
                r"tue(?:s|sday)?",
                r"wed(?:nesday)?",
                r"thu(?:r|rs|rsday)?",
                r"fri(?:day)?",
                r"sat(?:urday)?",
                r"sun(?:day)?",
                r"jan\w*",
                r"feb\w*",
                r"mar(?:ch)?",
                r"apr\w*",
                r"may",
                r"jun\w*",
                r"jul\w*",
                r"aug\w*",
                r"sep\w*",
                r"oct\w*",
                r"nov\w*",
                r"dec\w*",
                # числовые даты: 15.02, 15/02, 2026-02-15
                r"\d{1,2}[./]\d{1,2}",
                r"\d{4}-\d{1,2}-\d{1,2}",
            ]
            cls._OWN_DATE_RE = _re.compile(r"\b(?:" + "|".join(words) + r")\b")
        return bool(cls._OWN_DATE_RE.search(seg_low))

    def _chain_multi_dates(self, seg_list, parsed, now, language):
        """Наследование даты в parse_multi: «завтра в 10 встреча и в 15 созвон»
        — сегмент только со временем получает ДАТУ предыдущего события,
        время остаётся как распознано (пост-сдвиг, без повторного парсинга,
        чтобы не ломать относительные даты вроде «послезавтра»).

        Не наследуют: сегменты с собственным маркером даты, со словами-якорями
        («сегодня»/today/...), и не-Reminder результаты (периоды/дедлайны).
        """
        for i in range(1, len(parsed)):
            prev = parsed[i - 1]
            anchor = getattr(prev, "datetime_at", None) or getattr(prev, "start_at", None)
            if anchor is None or getattr(prev, "is_past", False):
                continue
            if anchor.date() == now.date():
                continue  # наследовать нечего
            cur = parsed[i]
            cur_dt = getattr(cur, "datetime_at", None)
            if cur_dt is None:
                continue  # наследуем только «чистое время» (ReminderResult)
            if getattr(cur, "recurrence", None) is not None:
                continue
            seg_low = seg_list[i].lower()
            if any(w in seg_low for w in self._ANCHOR_WORDS):
                continue
            if self._seg_has_own_date(seg_low):
                continue
            a = anchor.astimezone(cur_dt.tzinfo) if anchor.tzinfo and cur_dt.tzinfo else anchor
            cur.datetime_at = cur_dt.replace(year=a.year, month=a.month, day=a.day)
            if cur.datetime_at >= now:
                cur.is_past = False

    def parse(
        self,
        text: str,
        now: Optional[datetime] = None,
        language: Optional[str] = None,
        tz: TzLike = None,
    ) -> Optional[ParseResult]:
        """Разбирает фразу. → ReminderResult | CalendarResult | TaskResult | None.

        tz: пояс пользователя ('Europe/Moscow' или tzinfo). Если задан tz или
        передан aware now — все даты результата aware в этом поясе, а маркер
        пояса в тексте («в 10 мск», «at 10 EST») учитывается с переводом времени.
        Без tz и с naive now — поведение прежнее (naive datetime).
        """
        if language is not None and language not in ("auto", "ru", "en"):
            raise ValueError("language must be 'auto', 'ru', 'en' or None, got %r" % (language,))
        if not text or not text.strip():
            return None
        if self._too_long(text):
            return None
        user_tz = self._user_tz(tz, now)
        if user_tz is None:
            ref = now or datetime.now()
            return self._finalize_past(self._parse_local(text, ref, language), ref)
        now_aware = self._local_now(now, user_tz)
        marker = find_tz_marker(text)
        if marker is None:
            naive_now = now_aware.replace(tzinfo=None)
            result = self._parse_local(text, naive_now, language)
            if self._is_elapsed_duration(result, text, naive_now):
                # «через 24 часа», «in 90 minutes» — прошедшая длительность: точна и при
                # переводе часов (переход на летнее/зимнее время)
                result.datetime_at = (
                    now_aware.astimezone(timezone.utc) + (result.datetime_at - naive_now)
                ).astimezone(user_tz)
            self._localize(result, user_tz, user_tz)
            return self._finalize_past(result, now_aware)
        src_tz, cleaned = marker
        if not cleaned.strip():
            return None
        src_now = now_aware.astimezone(src_tz).replace(tzinfo=None)
        result = self._parse_local(cleaned, src_now, language)
        if result is None:
            return None
        result.source = text
        self._localize(result, src_tz, user_tz)
        return self._finalize_past(result, now_aware)

    _ELAPSED_RE = None

    @classmethod
    def _is_elapsed_duration(cls, result, text, naive_now):
        """Разовое напоминание, заданное сдвигом в часах/минутах/секундах от now
        («через 24 часа», «через полтора часа», «in 90 minutes»), без явных
        часов/дат. Дни/недели («через 2 дня», «in a day») — календарные, сюда не входят."""
        import re as _re

        if result is None or type(result).__name__ != "ReminderResult" or result.recurrence:
            return False
        if cls._ELAPSED_RE is None:
            cls._ELAPSED_RE = (
                _re.compile(r"(?<![\w])через\s+[^,;]*?(?:час|часа|часов|полчаса|минут\w*|мин|секунд\w*|сек)(?![\w])",
                            _re.IGNORECASE),
                _re.compile(r"\bin\s+[^,;]*?\b(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\b", _re.IGNORECASE),
                _re.compile(r"(?<![\w])(?:завтра|послезавтра|сегодня|tomorrow|today|tonight|дн[яей]|недел\w*|"
                            r"days?|weeks?|\d{1,2}:\d{2}|утра|вечера|ночи|am|pm)(?![\w])", _re.IGNORECASE),
            )
        ru, en, anchored = cls._ELAPSED_RE
        if not (ru.search(text) or en.search(text)) or anchored.search(text):
            return False
        delta = result.datetime_at - naive_now
        return timedelta(0) < delta < timedelta(days=7)

    @staticmethod
    def _finalize_past(result, ref):
        """Общее правило для обоих языков: разовое событие, целиком закончившееся
        до now, — is_past=True («29 февраля 2024», «31 декабря в 23:30» в 23:59,
        прошедший дедлайн). Серия без вхождений (UNTIL раньше старта) — тоже.
        Флаг только выставляется, будущие события не трогаются."""
        if result is None or result.is_past:
            return result

        def _align(a, b):
            if (a.tzinfo is None) != (b.tzinfo is None):
                return a.replace(tzinfo=None), b.replace(tzinfo=None)
            return a, b

        rec = getattr(result, "recurrence", None)
        if rec is not None:
            w = result.when
            if rec.until is not None and w is not None:
                u, w2 = _align(rec.until, w)
                if u < w2:
                    result.is_past = True
            return result
        tt = getattr(result, "task_type", None)
        if tt == TaskType.OPEN_START:
            return result
        if tt == TaskType.DEADLINE and getattr(result, "deadline", None) is not None:
            last = result.deadline
        else:
            cands = [getattr(result, f, None) for f in ("datetime_at", "start_at", "end_at")]
            cands = [c for c in cands if c is not None]
            if not cands:
                return result
            last = max(cands)
        a, b = _align(last, ref)
        if a < b:
            result.is_past = True
        return result

    def analyze(
        self,
        text: str,
        now: Optional[datetime] = None,
        language: Optional[str] = None,
        tz: TzLike = None,
    ):
        """Как parse(), но с причиной неудачи и вариантами для уточнения.

        → ParseAnalysis(result, status, reason, alternatives, language).
        status: ok | empty | too_long | no_datetime | ambiguous | invalid_date |
        needs_timezone. Для ambiguous в alternatives — разобранные варианты
        («в понедельник или вторник» → оба дня), их удобно предложить кнопками.
        """
        import re as _re
        from .analysis import ParseAnalysis, ParseStatus as S

        if language is not None and language not in ("auto", "ru", "en"):
            raise ValueError("language must be 'auto', 'ru', 'en' or None, got %r" % (language,))
        if not text or not text.strip():
            return ParseAnalysis(None, S.EMPTY, "empty input")
        if self._too_long(text):
            return ParseAnalysis(None, S.TOO_LONG, "input longer than max_text_length=%s"
                                 % (self.config.max_text_length,))
        lang = resolve_language(text, language, self.config.default_language)
        result = self.parse(text, now=now, language=language, tz=tz)
        if result is not None:
            return ParseAnalysis(result, S.OK, "", language=result.detected_language or lang)

        def out(status, reason, alternatives=None):
            return ParseAnalysis(None, status, reason, alternatives, lang)

        if self._user_tz(tz, now) is None and find_tz_marker(text) is not None:
            return out(S.NEEDS_TIMEZONE, "time zone in text; pass tz= (user's zone) to convert")
        enum = self._enumerated_days(text)
        if enum:
            parsed = [self.parse(t, now=now, language=language, tz=tz) for t in enum]
            return out(S.MULTIPLE, "several separate events; use parse_multi()",
                       [r for r in parsed if r is not None])
        alts = self._alternative_texts(text)
        if alts:
            parsed = [self.parse(a, now=now, language=language, tz=tz) for a in alts]
            return out(S.AMBIGUOUS, "alternatives: several dates/times offered",
                       [r for r in parsed if r is not None])
        if self._conflicting_day_markers(text):
            return out(S.AMBIGUOUS, "conflicting day markers (e.g. yesterday and tomorrow)")
        m = _re.search(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])", text)
        if m and (int(m.group(1)) > 24 or int(m.group(2)) > 59):
            return out(S.INVALID_DATE, "impossible time %s" % m.group(0))
        if lang == "en":
            low = self._en._preprocess(text.lower())
            if self._en._invalid_date(low):
                return out(S.INVALID_DATE, "impossible calendar date")
            if self._en._ambiguous_last_period(low):
                return out(S.AMBIGUOUS, "past period without a specific day")
        else:
            tokens = self.tokenizer.tokenize(self._normalize_ru(text))
            if self._invalid_explicit_date(tokens):
                return out(S.INVALID_DATE, "impossible calendar date")
            if self._ambiguous_past_period(text):
                return out(S.AMBIGUOUS, "past period without a specific day")
        return out(S.NO_DATETIME, "no date or time found")

    def analyze_multi(
        self,
        text: str,
        now: Optional[datetime] = None,
        language: Optional[str] = None,
        tz: TzLike = None,
    ):
        """Как parse_multi(), но каждый элемент — ParseAnalysis.

        Если фраза разбилась на несколько событий — список анализов со статусом ok.
        Иначе — [analyze(text)] с причиной неудачи/вариантами для всей фразы.
        """
        from .analysis import ParseAnalysis, ParseStatus as S

        results = self.parse_multi(text, now=now, language=language, tz=tz)
        if len(results) >= 2:
            return [ParseAnalysis(r, S.OK, "", language=r.detected_language) for r in results]
        return [self.analyze(text, now=now, language=language, tz=tz)]

    # ── часовые пояса / лимиты ───────────────────────────────────────────
    def _too_long(self, text):
        limit = getattr(self.config, "max_text_length", None)
        if limit and len(text) > limit:
            logger.debug("input too long (%d > %d), skipped", len(text), limit)
            return True
        return False

    def _user_tz(self, tz, now):
        if tz is None:
            tz = getattr(self.config, "default_tz", None)
        z = resolve_tz(tz)
        if z is None and now is not None and now.tzinfo is not None:
            z = now.tzinfo
        return z

    @staticmethod
    def _local_now(now, user_tz):
        """now в поясе пользователя (aware) или как есть, если пояса нет."""
        if user_tz is None:
            return now or datetime.now()
        if now is None:
            return datetime.now(user_tz)
        if now.tzinfo is None:
            return now.replace(tzinfo=user_tz)
        return now.astimezone(user_tz)

    _TZ_FIELDS = ("datetime_at", "start_at", "end_at", "deadline")

    def _localize(self, result, src_tz, dst_tz):
        """naive-даты результата (в поясе src_tz) → aware в поясе dst_tz."""
        if result is None:
            return
        for f in self._TZ_FIELDS:
            v = getattr(result, f, None)
            if isinstance(v, datetime) and v.tzinfo is None:
                setattr(result, f, v.replace(tzinfo=src_tz).astimezone(dst_tz))
        rec = getattr(result, "recurrence", None)
        if rec is not None and isinstance(rec.until, datetime) and rec.until.tzinfo is None:
            rec.until = rec.until.replace(tzinfo=src_tz).astimezone(dst_tz)
        if rec is not None and getattr(rec, "exdates", None):
            rec.exdates = [x.replace(tzinfo=src_tz).astimezone(dst_tz) if x.tzinfo is None else x
                           for x in rec.exdates]

    def _parse_local(self, text, now, language):
        """Разбор в «локальном» naive-времени (прежний parse)."""
        lang = resolve_language(text, language, self.config.default_language)
        # праздники по названию → явная дата («на новый год», «by christmas»)
        from .holidays import apply_holidays

        text_h = apply_holidays(text, now.date(), lang, getattr(self.config, "calendar", None))
        if text_h != text:
            r = self._parse_local(text_h, now, lang)
            if r is not None:
                r.source = text
            return r
        # «в понедельник или во вторник», «в 5 или 6», «monday or tuesday» —
        # альтернатива между датами/временами: момент не определён → None
        # (та же политика, что и для конфликтующих «вчера/завтра»).
        if self._alternative_dates(text):
            return None
        # «в пн, ср и пт в 10» — несколько отдельных событий: одно выбрать нельзя,
        # не потеряв остальные → None; все события — в parse_multi() / analyze()
        if self._enumerated_days(text):
            return None
        # Английская локаль — отдельный regex-парсер.
        if lang == "en":
            if self._conflicting_day_markers(text):
                return None
            try:
                dt, title, duration, location = self._en.parse(text, now)
            except Exception:
                # Библиотека не должна ронять вызывающий код на кривом вводе
                # («at 25:00»): честный ответ — None. Причину пишем в debug-лог.
                logger.debug("EN locale parser failed on %r", text, exc_info=True)
                return None
            if dt is None:
                return None
            rec_sf = getattr(getattr(dt, "recurrence", None), "_series_from", None)
            self._snap_recurrence_start(dt, rec_sf if rec_sf is not None and rec_sf > now else now)
            self._finalize_exdates(dt)
            result = self._classify(dt, title, text, location, duration)
            if result is not None:
                result.detected_language = "en"
            return result
        tokens = self.tokenizer.tokenize(self._normalize_ru(text))
        if not tokens:
            return None
        # Невалидная явная дата («31 февраля», «29 февраля 2025», «31 апреля»)
        # → None для всей фразы, даже если рядом есть время.
        if self._invalid_explicit_date(tokens):
            return None
        # Взаимоисключающие относительные маркеры дней → неоднозначно, None.
        if self._conflicting_day_markers(text):
            return None
        # Периодный маркер прошлого («на прошлой неделе», «в прошлом
        # месяце/квартале/году») + время, но без конкретного дня недели/числа →
        # момент неоднозначен → None. Продуктивные случаи (неделя+день,
        # месяц+число) сюда не попадают и обрабатываются распознавателями.
        if self._ambiguous_past_period(text):
            return None
        # Таймзоны не поддерживаются — не угадываем абсолютное время.
        if self._has_timezone(tokens):
            return None
        # Защитная проверка: неизвестная локаль → None.
        if lang not in self._LOCALES:
            return None
        all_dates = []
        for recognizer in self.recognizers:
            try:
                results = recognizer.recognize(tokens, now)
                if results:
                    all_dates.extend(results)
            except Exception:
                logger.debug(
                    "recognizer %s failed on %r", type(recognizer).__name__, text, exc_info=True
                )
                continue
        ExclusionParser.find_exclusions(tokens, all_dates, now)
        all_dates = self._refine_daypart_time(all_dates, now)
        self._refine_daypart_word(all_dates, tokens)
        all_dates = self._combine_weeks_weekday(all_dates, tokens)
        all_dates = self._attach_time_to_weekend(all_dates, now)
        self._scan_recurrence_modifiers(all_dates, tokens, now)
        all_dates = self._drop_number_before_month_as_time(all_dates, tokens)
        all_dates = self._frequent_in_window(all_dates, now)
        all_dates = self._even_odd_days(all_dates, tokens, now)
        all_dates = self._yearly_ordinal_weekday(all_dates, tokens)
        all_dates = self._exclude_dates(all_dates, tokens)
        all_dates = self._series_bounds(all_dates, tokens)
        all_dates = self._split_range(all_dates, tokens, now)
        all_dates = self._explicit_date_range(all_dates, tokens, now)
        all_dates = self._days_before(all_dates, tokens, now)
        all_dates = self._attach_time_to_deadline(all_dates, now)
        self._apply_weekday_exclusions(all_dates)
        all_dates = self._merge_date_and_time(all_dates, now)
        all_dates = self._deduplicate(all_dates)
        if not all_dates:
            return None
        date_spans = [(d.start, d.end) for d in all_dates]
        location = LocationExtractor.extract(tokens, date_spans)
        title = self._extract_event_title(text, tokens, all_dates)
        duration = None
        for d in all_dates:
            if hasattr(d, "_is_duration") and d._is_duration:
                duration = d._duration_minutes
        best = self._select_best(all_dates)
        rec_b = getattr(best, "recurrence", None) if best is not None else None
        series_from = getattr(rec_b, "_series_from", None)
        if series_from is not None and series_from > now:
            # «начиная с 1 октября каждый понедельник» — первое вхождение не раньше даты
            self._snap_recurrence_start(best, series_from)
            if best.date_from.date() < series_from.date():
                # правило без дня недели («каждый день с 1 октября»)
                best.date_from = best.date_from.replace(
                    year=series_from.year, month=series_from.month, day=series_from.day)
            if not best.has_time:
                # серия без времени — на полночи (соглашение данных: start == end в 00:00)
                best.date_from = best.date_from.replace(hour=0, minute=0, second=0, microsecond=0)
                best.date_to = best.date_from
            elif best.date_to is None or best.date_to < best.date_from:
                best.date_to = best.date_from
        else:
            self._snap_recurrence_start(best, now)
        self._finalize_exdates(best)
        result = self._classify(best, title, text, location, duration)
        if result is not None:
            result.detected_language = lang
        return result

    _LOCALES = {"ru", "en"}

    @staticmethod
    def _daypart_of(tok):
        """Нечёткий токен части суток (утром/днём/вечером/ночью) → 'morning'|... | None."""
        if not (tok.type == DateTimeType.PERIOD and tok.fuzzy and tok.has_time
                and not tok.is_explicit_range and not tok.recurrence):
            return None
        span_h = (tok.date_to - tok.date_from).total_seconds() / 3600
        if span_h > 12:
            return None
        h = tok.date_from.hour
        if 5 <= h < 12:
            return "morning"
        if 12 <= h < 17:
            return "day"
        if 17 <= h < 22:
            return "evening"
        return "night"

    def _refine_daypart_time(self, dates, now):
        """«вечером в 20», «утром в 8:30», «ночью в 2»: точное время побеждает
        нечёткую часть суток; часть суток только уточняет AM/PM и день."""
        out = list(dates)
        for d in list(out):
            part = self._daypart_of(d)
            if part is None:
                continue
            # слово уже часть другого выражения («через 2 дня») — это не часть суток
            if any(o is not d and o.start <= d.start and o.end >= d.end for o in out):
                continue
            for t in out:
                if t is d or t.type != DateTimeType.FIXED or not t.has_time or t.is_deadline:
                    continue
                gap = t.start - d.end if t.start >= d.end else d.start - t.end
                if gap < 0 or gap > 3:
                    continue
                h = getattr(t, "_raw_hour", t.date_from.hour)
                m = getattr(t, "_raw_minute", t.date_from.minute)
                day = d.date_from
                if part in ("day", "evening") and 1 <= h <= 11:
                    h += 12
                elif part == "night":
                    if h == 12:
                        h = 0
                    elif 7 <= h <= 11:
                        h += 12
                    if h < 12:  # «ночью в 2» — после полуночи
                        day = d.date_from + timedelta(days=1) if d.date_from.hour >= 12 else day
                new = day.replace(hour=h, minute=m, second=0, microsecond=0)
                # окно части суток сдвинуто на завтра, т.к. уже началось («днём» в 14:00),
                # но точное время сегодня ещё впереди → сегодня
                if part != "night" and new.date() > now.date() and self.config.prefer_nearest_future:
                    today = new.replace(year=now.year, month=now.month, day=now.day)
                    if today >= now:
                        new = today
                t.date_from = t.date_to = new
                t.start, t.end = min(t.start, d.start), max(t.end, d.end)
                t._explicit_pod = True
                t._raw_hour, t._raw_minute = h, m
                t.is_past = new < now
                out.remove(d)
                break
        return out

    _DAYPART_WORDS = {
        "утром": "morning", "днём": "day", "днем": "day",
        "вечером": "evening", "ночью": "night",
    }

    def _refine_daypart_word(self, dates, tokens):
        """«каждый день утром в 7», «по вечерам в 9»: часть суток «съедена»
        повтором, но слово стоит прямо перед временем — уточняем AM/PM."""
        for t in dates:
            if t.type != DateTimeType.FIXED or not t.has_time or t.is_deadline:
                continue
            if getattr(t, "_explicit_pod", False):
                continue
            prev = [x for x in tokens if x.end <= t.start]
            if prev and prev[-1].value.lower() in ("в", "во"):
                prev = prev[:-1]
            if not prev or t.start - prev[-1].end > 4:
                continue
            part = self._DAYPART_WORDS.get(prev[-1].value.lower())
            if part is None:
                continue
            h = getattr(t, "_raw_hour", t.date_from.hour)
            m = getattr(t, "_raw_minute", t.date_from.minute)
            if part == "morning" and h == 12:
                h = 0
            elif part in ("day", "evening") and 1 <= h <= 11:
                h += 12
            elif part == "night" and 7 <= h <= 11:
                h += 12
            t.date_from = t.date_to = t.date_from.replace(hour=h, minute=m)
            t._explicit_pod = True
            t._raw_hour, t._raw_minute = h, m

    @staticmethod
    def _drop_number_before_month_as_time(dates, tokens):
        """«с 1 октября», «до 5 марта»: число перед названием месяца — день, а не час.
        Убираем ложное «время» (иначе «с 1 октября курс» давало 01:00)."""
        def month_word(tok):
            v, n = tok.value.lower(), tok.normalized
            return v in ("числа", "число") or any(v in f or n in f for f in Keywords.months())

        starts = {t.start: i for i, t in enumerate(tokens)}
        out = []
        for d in dates:
            if d.type == DateTimeType.FIXED and d.has_time and d.recurrence is None \
                    and not d.all_day and not d.is_deadline:
                nxt = next((t for t in tokens if t.start >= d.end), None)
                last = [t for t in tokens if d.start <= t.start < d.end]
                if nxt is not None and last and last[-1].value.isdigit() and month_word(nxt) \
                        and nxt.start - d.end <= 1:
                    continue
            out.append(d)
        return out

    @staticmethod
    def apply_hour_window(rec, start_dt, end_dt, now):
        """Частый повтор (MINUTELY/HOURLY) в окне часов → BYHOUR и первое вхождение ≥ now.
        Окно [start, end): «с 9 до 18» → 9..17 (при end с минутами — включая час end)."""
        h1, h2 = start_dt.hour, end_dt.hour
        if end_dt.minute > 0:
            h2 += 1
        if h2 <= h1:
            return None
        rec.by_hour = list(range(h1, h2))
        step = timedelta(minutes=rec.interval) if rec.frequency == "MINUTELY" else timedelta(hours=rec.interval)
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        allowed = set(rec.by_day or [])
        for k in range(9):
            day = day0 + timedelta(days=k)
            if allowed and codes[day.weekday()] not in allowed:
                continue
            slot = day.replace(hour=h1, minute=start_dt.minute)
            end = day.replace(hour=h2 - 1, minute=59)
            while slot <= end:
                if slot >= now.replace(second=0, microsecond=0):
                    return slot
                slot += step
        return day0 + timedelta(days=1, hours=h1)

    def _frequent_in_window(self, dates, now):
        """«каждые 30 минут с 9 до 18», «каждый час с 9 до 18»: повтор + диапазон часов."""
        r = next((d for d in dates if d.recurrence is not None
                  and d.recurrence.frequency in ("MINUTELY", "HOURLY")), None)
        if r is None:
            return dates
        # «каждые 30 минут … по будням»: дни недели из второго правила — в частое правило
        wk = next((d for d in dates if d is not r and d.recurrence is not None
                   and d.recurrence.frequency == "WEEKLY" and d.recurrence.by_day
                   and d.recurrence.interval == 1), None)
        if wk is not None and not r.recurrence.by_day:
            r.recurrence.by_day = list(wk.recurrence.by_day)
            r.used_spans = (getattr(r, "used_spans", None) or [(r.start, r.end)]) + [(wk.start, wk.end)]
            dates = [d for d in dates if d is not wk and not (wk.start <= d.start and d.end <= wk.end)]
        w = next((d for d in dates if d is not r and d.recurrence is None and d.has_time
                  and d.date_to is not None and d.date_to > d.date_from
                  and d.date_from.date() == d.date_to.date()), None)
        if w is None:
            return dates
        first = self.apply_hour_window(r.recurrence, w.date_from, w.date_to, now)
        if first is None:
            return dates
        r.date_from = r.date_to = first
        r.has_time, r.all_day = True, False
        r.used_spans = (getattr(r, "used_spans", None) or [(r.start, r.end)]) + [(w.start, w.end)]
        return [d for d in dates if d is not w]

    _ORD_RU = {"первую": 1, "вторую": 2, "третью": 3, "четвёртую": 4, "четвертую": 4,
               "последнюю": -1, "предпоследнюю": -2}
    _WD_ACC_RU = {"понедельник": "MO", "вторник": "TU", "среду": "WE", "четверг": "TH",
                  "пятницу": "FR", "субботу": "SA", "воскресенье": "SU"}

    def _yearly_ordinal_weekday(self, dates, tokens):
        """«каждый год (ежегодно) в последнюю пятницу октября» → YEARLY;BYMONTH=10;BYDAY=-1FR."""
        r = next((d for d in dates if d.recurrence is not None and d.recurrence.frequency == "YEARLY"
                  and not d.recurrence.by_month and not d.recurrence.by_day), None)
        if r is None:
            return dates
        vals = [t.value.lower() for t in tokens]
        for k in range(len(tokens) - 2):
            n = self._ORD_RU.get(vals[k])
            code = self._WD_ACC_RU.get(vals[k + 1])
            if n is None or code is None:
                continue
            mon = next((mi + 1 for mi, forms in enumerate(Keywords.months()) if vals[k + 2] in forms), None)
            if mon is None:
                continue
            r.recurrence.by_month = [mon]
            r.recurrence.by_day = ["%d%s" % (n, code)]
            span = (tokens[k].start, tokens[k + 2].end)
            anchor = next((d for d in dates if d is not r and d.recurrence is None
                           and d.start <= span[0] < d.end), None)
            if anchor is not None:  # дата ближайшего вхождения уже вычислена распознавателем
                r.date_from = r.date_to = anchor.date_from.replace(hour=0, minute=0)
                r.all_day, r.has_time = True, False
            r.used_spans = (getattr(r, "used_spans", None) or [(r.start, r.end)]) + [span]
            return [d for d in dates if d is r or not (span[0] <= d.start < span[1] or d.start <= span[0] < d.end)]
        return dates

    @staticmethod
    def _even_odd_days(dates, tokens, now):
        """«по чётным / нечётным числам (дням)» → ежемесячно BYMONTHDAY=2,4,…,30 / 1,3,…,31."""
        for k in range(len(tokens) - 2):
            w0, w1, w2 = (tokens[k].value.lower(), tokens[k + 1].value.lower(), tokens[k + 2].value.lower())
            if w0 != "по" or w2 not in ("числам", "дням"):
                continue
            if w1 in ("чётным", "четным"):
                days = list(range(2, 31, 2))
            elif w1 in ("нечётным", "нечетным"):
                days = list(range(1, 32, 2))
            else:
                continue
            rec = RecurrenceRule(frequency="MONTHLY", by_month_day=days)
            d = now.replace(hour=0, minute=0, second=0, microsecond=0)
            while d.day not in days:
                d += timedelta(days=1)
            tok = DateTimeToken(type=DateTimeType.FIXED, date_from=d, date_to=d, has_time=False,
                                all_day=True, recurrence=rec, start=tokens[k].start,
                                end=tokens[k + 2].end, confidence=0.95)
            return [x for x in dates if not (tok.start <= x.start < tok.end)] + [tok]
        return dates

    @staticmethod
    def _exclude_dates(dates, tokens):
        """«каждый день кроме 31 декабря», «кроме 1 и 8 января», «за исключением 31 декабря»:
        конкретные даты — исключённые вхождения серии (EXDATE)."""
        rec_tok = next((d for d in dates if d.recurrence is not None), None)
        words = [t.value.lower() for t in tokens]
        k = None
        for i, w in enumerate(words):
            if w in ("кроме", "исключая") or (w == "исключением" and i > 0 and words[i - 1] == "за"):
                k = i
                break
        if k is None:
            return dates
        after = tokens[k].end
        picked = []
        for d in sorted(dates, key=lambda x: x.start):
            if d.start < after or d.recurrence is not None:
                continue
            if not (d.type == DateTimeType.FIXED and d.all_day and not d.has_time):
                continue
            # только конкретные даты с месяцем («31 декабря»), не дни недели («пятницы»)
            span_words = [t.value.lower() for t in tokens if d.start <= t.start < d.end]
            if not any(any(w in f for f in Keywords.months()) for w in span_words):
                continue
            gap_words = [t.value.lower() for t in tokens if after <= t.start < d.start]
            if any(w not in ("и", ",", "также") for w in gap_words):
                break
            picked.append(d)
            after = d.end
        if not picked:
            return dates
        if rec_tok is None:
            # «кроме 31 декабря» без серии — исключать не из чего; это НЕ событие 31 декабря
            return [d for d in dates if d not in picked]
        dates_ex = getattr(rec_tok.recurrence, "_exdate_dates", [])
        rec_tok.recurrence._exdate_dates = dates_ex + [d.date_from.date() for d in picked]
        rec_tok.used_spans = (getattr(rec_tok, "used_spans", None) or [(rec_tok.start, rec_tok.end)]) + \
            [(tokens[k - 1 if words[k] == "исключением" else k].start, picked[-1].end)]
        return [d for d in dates if d not in picked]

    @staticmethod
    def _finalize_exdates(dt):
        """Даты-исключения → вхождения серии. Время берём у старта серии: по RFC 5545
        EXDATE должен совпадать с моментом вхождения, иначе календарь его не применит."""
        rec = getattr(dt, "recurrence", None) if dt is not None else None
        if rec is None or not getattr(rec, "_exdate_dates", None):
            return
        t = dt.date_from
        rec.exdates = [datetime.combine(d, t.time()) for d in sorted(set(rec._exdate_dates))]

    def _series_bounds(self, dates, tokens):
        """Границы серии: «каждый понедельник с 1 октября по 1 декабря» (старт + UNTIL),
        «начиная с 1 октября каждый понедельник», «каждый день с 1 октября» (старт)."""
        recs = [d for d in dates if d.recurrence is not None]
        if not recs:
            return dates
        r = recs[0]
        out = list(dates)

        def overlaps(a, b):
            return not (a.end <= b.start or a.start >= b.end)

        first_word = {t.start: t.value.lower() for t in tokens}
        # «с X по Y» — диапазон дат (именно со «с/со»: «по будням», «кроме выходных»
        # тоже дают периоды, но это дни правила, а не границы серии)
        for p in list(out):
            if p is r or p.recurrence is not None:
                continue
            if first_word.get(p.start) not in ("с", "со"):
                continue
            if p.type == DateTimeType.PERIOD and p.all_day and not p.fuzzy and not p.has_time \
                    and (p.date_to.date() - p.date_from.date()).days >= 1:
                r.recurrence._series_from = p.date_from.replace(hour=0, minute=0)
                if r.recurrence.until is None and r.recurrence.count is None:
                    r.recurrence.until = p.date_to.replace(hour=23, minute=59, second=0, microsecond=0)
                r.used_spans = (getattr(r, "used_spans", None) or [(r.start, r.end)]) + [(p.start, p.end)]
                out = [d for d in out if d is r or not (p.start <= d.start and d.end <= p.end)]
                return out
        # «(начиная) с X» — дата начала (перекрытие с правилом допустимо: «с» однозначно)
        for d in list(out):
            if d is r or d.recurrence is not None:
                continue
            if not (d.type == DateTimeType.FIXED and d.all_day and not d.has_time and not d.is_deadline):
                continue
            prev = [t for t in tokens if t.end <= d.start]
            if not prev or prev[-1].value.lower() not in ("с", "со"):
                continue
            s0 = prev[-1].start
            if len(prev) >= 2 and prev[-2].value.lower() in ("начиная", "начиная", "стартуя"):
                s0 = prev[-2].start
            r.recurrence._series_from = d.date_from.replace(hour=0, minute=0)
            r.used_spans = (getattr(r, "used_spans", None) or [(r.start, r.end)]) + [(s0, d.end)]
            out.remove(d)
            break
        return out

    @staticmethod
    def _explicit_date_range(dates, tokens, now):
        """«с 22 июня 1941 по 9 мая 1945»: две явные даты (с годом или без) → период.
        Одногодние диапазоны уже собирает RangeRecognizer; здесь — то, что он пропустил."""
        def word_before(pos):
            prev = [t for t in tokens if t.end <= pos]
            return (prev[-1].value.lower(), prev[-1].start) if prev else ("", pos)

        firsts = [d for d in dates if d.type == DateTimeType.FIXED and d.all_day and not d.has_time
                  and d.recurrence is None and not d.is_deadline]
        for d1 in firsts:
            w, wpos = word_before(d1.start)
            if w not in ("с", "со"):
                continue
            d2 = next((d for d in dates if d is not d1 and d.recurrence is None and not d.has_time
                       and 0 <= d.start - d1.end <= 2 and d.date_to is not None
                       and word_before(d.start)[0] in ("по", "до") or
                       (d is not d1 and d.recurrence is None and not d.has_time and d.date_to is not None
                        and d.start <= d1.end + 1 and d.start > d1.start and
                        [t.value.lower() for t in tokens if t.start == d.start][:1] in (["по"], ["до"]))), None)
            if d2 is None:
                continue
            end = d2.date_to.replace(hour=23, minute=59, second=0, microsecond=0)
            start = d1.date_from.replace(hour=0, minute=0, second=0, microsecond=0)
            if end <= start:
                continue
            rng = DateTimeToken(type=DateTimeType.PERIOD, date_from=start, date_to=end, has_time=False,
                                all_day=True, start=wpos, end=d2.end, confidence=0.98, is_past=end < now)
            rng.is_explicit_range = True
            return [d for d in dates if not (wpos <= d.start < d2.end)] + [rng]
        return dates

    def _split_range(self, dates, tokens, now):
        import re
        """«с 9 утра 12 апреля 1961 года до 11 утра» — диапазон времени, разорванный датой:
        событие на эту дату с началом и концом (конец раньше начала — через полночь)."""
        def word_before(pos):
            prev = [t for t in tokens if t.end <= pos]
            return prev[-1].value.lower() if prev else ""

        def first_word(tok):
            ws = [t for t in tokens if tok.start <= t.start < tok.end]
            return ws[0].value.lower() if ws else ""

        def hm(tok, use_to=False):
            if hasattr(tok, "_deadline_time"):
                return tok._deadline_time
            moment = tok.date_to if use_to else tok.date_from
            if getattr(tok, "_explicit_pod", False) or not hasattr(tok, "_raw_hour"):
                return moment.hour, moment.minute
            h = tok._raw_hour
            if 1 <= h <= 7 and self.config.prefer_nearest_future:
                h += 12
            return h, getattr(tok, "_raw_minute", moment.minute)

        times = [d for d in dates if d.type == DateTimeType.FIXED and d.has_time
                 and d.recurrence is None and not d.is_deadline]
        # «с 10 завтра до 12»: «с 10» без продолжения не распознаётся как время —
        # собираем его из токенов «с/со + число» прямо перед датой
        for k in range(len(tokens) - 1):
            if tokens[k].value.lower() not in ("с", "со"):
                continue
            mnum = re.match(r"^(\d{1,2})(?::(\d{2}))?$", tokens[k + 1].value)
            if not mnum or any(t.start <= tokens[k + 1].start < t.end for t in times):
                continue
            h = int(mnum.group(1))
            if h > 23:
                continue
            if 1 <= h <= 7 and self.config.prefer_nearest_future:
                h += 12
            pseudo = DateTimeToken(type=DateTimeType.FIXED, date_from=now.replace(hour=h, minute=int(mnum.group(2) or 0)),
                                   date_to=now, has_time=True, start=tokens[k].start, end=tokens[k + 1].end)
            pseudo._explicit_pod = True
            times.append(pseudo)
        for t1 in times:
            if "с" != first_word(t1) and word_before(t1.start) not in ("с", "со"):
                continue
            day = next((d for d in dates if d.type == DateTimeType.FIXED and d.all_day and not d.has_time
                        and d.recurrence is None and not d.is_deadline and 0 <= d.start - t1.end <= 2), None)
            if day is None:
                continue
            t2 = next((d for d in dates if d is not t1 and d.type == DateTimeType.FIXED and d.has_time
                       and d.recurrence is None and 0 <= d.start - day.end <= 7
                       and (d.is_deadline or word_before(d.start) in ("до", "по"))), None)
            if t2 is None:
                continue
            h1, m1 = hm(t1)
            h2, m2 = hm(t2, use_to=t2.is_deadline)
            base = day.date_from.date()
            start = datetime.combine(base, datetime.min.time()).replace(hour=h1, minute=m1)
            end = datetime.combine(base, datetime.min.time()).replace(hour=h2, minute=m2)
            if end <= start:
                end += timedelta(days=1)
            s0 = min(t1.start, [t for t in tokens if t.end <= t1.start][-1].start
                     if word_before(t1.start) in ("с", "со") else t1.start)
            rng = DateTimeToken(type=DateTimeType.PERIOD, date_from=start, date_to=end, has_time=True,
                                all_day=False, start=s0, end=t2.end, confidence=1.0,
                                is_past=end < now)
            rng.is_explicit_range = True
            return [d for d in dates if not (s0 <= d.start < t2.end)] + [rng]
        return dates

    def _days_before(self, dates, tokens, now):
        """«за 2 дня до пятницы», «за 3 рабочих дня до 20 июля», «за неделю до отпуска
        [дата]» → дата минус N (рабочих) дней, начало рабочего дня 09:00 (как «за N
        рабочих дней до конца месяца»). Рабочие дни учитывают WorkingCalendar."""
        cal = getattr(self.config, "calendar", None)

        def working(d):
            return cal.is_working_day(d.date()) if cal is not None else d.weekday() < 5

        out = list(dates)
        for k, t in enumerate(tokens):
            if t.value.lower() != "за" or k + 2 >= len(tokens):
                continue
            # уже разобрано отдельным распознавателем («за N рабочих дней до конца месяца»)
            if any(d.start == t.start for d in out):
                continue
            j = k + 1
            v = tokens[j].value.lower()
            if v in ("неделю", "неделя"):
                n, unit_days, business = 1, 7, False
                j += 1
            else:
                n = int(v) if v.isdigit() else Keywords.parse_number_word(v, self.tokenizer.morph)
                if n is None:
                    continue
                j += 1
                business = j < len(tokens) and tokens[j].value.lower() in Keywords.WORKING
                if business:
                    j += 1
                if j >= len(tokens):
                    continue
                u = tokens[j].value.lower()
                if u in ("день", "дня", "дней") or tokens[j].normalized in Keywords.DAY:
                    unit_days = 1
                elif u.startswith("недел"):
                    unit_days, business = 7, False
                else:
                    continue
                j += 1
            if j >= len(tokens) or tokens[j].value.lower() != "до":
                continue
            # дата сразу после «до»: либо дедлайн-токен с «до», либо дата за ним
            target_tok = next(
                (d for d in out if d.recurrence is None and d.start in (tokens[j].start,
                 tokens[j + 1].start if j + 1 < len(tokens) else -1)
                 and not (d.type == DateTimeType.PERIOD and d.fuzzy)),
                None,
            )
            if target_tok is None:
                continue
            base = (target_tok.date_to if target_tok.is_deadline else target_tok.date_from)
            base = base.replace(hour=9, minute=0, second=0, microsecond=0)
            if business:
                stepped = 0
                while stepped < n:
                    base -= timedelta(days=1)
                    if working(base):
                        stepped += 1
            else:
                base -= timedelta(days=n * unit_days)
            new = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=base,
                date_to=base,
                has_time=False,
                all_day=True,
                start=t.start,
                end=target_tok.end,
                confidence=max(target_tok.confidence, 0.9),
                is_past=base.date() < now.date(),
            )
            out = [d for d in out if not (t.start <= d.start < target_tok.end)]
            out.append(new)
        return out

    @staticmethod
    def _attach_time_to_deadline(dates, now):
        """«до конца месяца в 18:00», «до 20 октября в 18:00», «до нового года в 23:50»:
        время рядом с дедлайном задаёт час дедлайна. Повторы и части суток не трогаем."""
        out = list(dates)
        for d in list(out):
            if not (d.type == DateTimeType.FIXED and d.is_deadline and not d.has_time
                    and d.recurrence is None):
                continue
            # «за 2 рабочих дня [до конца месяца] в 10» — дедлайн внутри более длинной
            # фразы; время относится к ней, а не к вложенному «до конца месяца»
            if any(o is not d and o.start <= d.start and o.end >= d.end and (o.end - o.start) > (d.end - d.start)
                   for o in out):
                continue
            for t in out:
                if t is d or t.recurrence is not None or t.is_deadline:
                    continue
                if t.type != DateTimeType.FIXED or not t.has_time or t.all_day:
                    continue
                overlap = not (t.end <= d.start or t.start >= d.end)
                gap = t.start - d.end if t.start >= d.end else d.start - t.end
                if not overlap and (gap < 0 or gap > 3):  # только соседние/вложенные
                    continue
                # «до 20 октября в 18:00»: дата+время уже собраны одним токеном
                if t.date_from.date() == d.date_to.date():
                    dl = t.date_from
                else:
                    dl = datetime.combine(d.date_to.date(), t.date_from.time())
                d.date_to = dl
                d.date_from = min(d.date_from, dl)
                d.has_time = True
                d.start, d.end = min(d.start, t.start), max(d.end, t.end)
                d.is_past = dl < now
                out.remove(t)
                break
        return out

    def _scan_recurrence_modifiers(self, dates, tokens, now):
        """«6 раз» / «до конца года» после любого правила повторения, включая те,
        что выдал не RecurrenceRecognizer («каждую вторую среду месяца … 6 раз»)."""
        rec_rec = next(
            (r for r in self.recognizers if type(r).__name__ == "RecurrenceRecognizer"), None
        )
        if rec_rec is None:
            return
        for d in dates:
            rec = getattr(d, "recurrence", None)
            if rec is None or rec.count is not None or rec.until is not None:
                continue
            for k, t in enumerate(tokens):
                if t.start < d.end:
                    continue
                v = t.value.lower()
                is_count = k + 1 < len(tokens) and tokens[k + 1].value.lower() in ("раз", "раза")
                if v != "до" and not is_count:
                    continue
                eaten = rec_rec._scan_count_until(tokens, k, rec, now)
                if eaten > 0:
                    d.used_spans = [(d.start, d.end), (t.start, tokens[k + eaten - 1].end)]
                    break

    def _attach_time_to_weekend(self, dates, now):
        """«в выходные в 10», «на выходных в 10» → суббота этих выходных в 10:00."""
        out = list(dates)
        for w in list(out):
            if not (w.type == DateTimeType.PERIOD and w.all_day and not w.has_time
                    and w.date_from.weekday() == 5
                    and (w.date_to.date() - w.date_from.date()).days == 1):
                continue
            for t in out:
                if t is w or t.type != DateTimeType.FIXED or not t.has_time or t.is_deadline:
                    continue
                gap = t.start - w.end if t.start >= w.end else w.start - t.end
                if gap < 0 or gap > 3:
                    continue
                h = getattr(t, "_raw_hour", t.date_from.hour)
                m = getattr(t, "_raw_minute", t.date_from.minute)
                if (not getattr(t, "_explicit_pod", False) and 1 <= h <= 7
                        and self.config.prefer_nearest_future):
                    h += 12
                t.date_from = t.date_to = w.date_from.replace(hour=h, minute=m)
                t.start, t.end = min(t.start, w.start), max(t.end, w.end)
                t._explicit_pod = True
                t.is_past = t.date_from < now
                out.remove(w)
                break
        return out

    def _combine_weeks_weekday(self, dates, tokens):
        """«через неделю в пятницу», «через 3 недели в понедельник»: день недели
        в той календарной неделе, куда попадает «через N недель»."""
        def span_words(tok):
            return [x for x in tokens if x.start >= tok.start and x.end <= tok.end]

        out = list(dates)
        for r in list(out):
            if r.type != DateTimeType.SPAN_FORWARD or r.has_time:
                continue
            if not any(w.value.lower() in Keywords.WEEK or w.normalized in Keywords.WEEK
                       for w in span_words(r)):
                continue
            for w in out:
                if w is r or w.type != DateTimeType.FIXED or not w.all_day or w.has_time or w.recurrence:
                    continue
                gap = w.start - r.end if w.start >= r.end else r.start - w.end
                if gap < 0 or gap > 4:
                    continue
                is_wd = any(
                    x.value.lower() in days or x.normalized in days
                    for x in span_words(w) for days in Keywords.days_of_week()
                )
                if not is_wd:
                    continue
                base = r.date_from.replace(hour=0, minute=0, second=0, microsecond=0)
                target = base - timedelta(days=base.weekday()) + timedelta(days=w.date_from.weekday())
                w.date_from = target
                w.date_to = target.replace(hour=23, minute=59)
                w.start, w.end = min(w.start, r.start), max(w.end, r.end)
                w.confidence = max(w.confidence, r.confidence)
                out.remove(r)
                break
        return out

    _ALT_RE = None

    @classmethod
    def _alternative_dates(cls, text):
        import re as _re

        if cls._ALT_RE is None:
            wd_ru = (
                r"понедельник\w*|вторник\w*|сред[ауые]|четверг\w*|пятниц\w*|"
                r"суббот\w*|воскресень\w*"
            )
            wd_en = (
                r"mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|"
                r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
            )
            rel = r"завтра|послезавтра|сегодня|tomorrow|today|tonight"
            num = r"\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?"
            item = r"(?:" + wd_ru + "|" + wd_en + "|" + rel + "|" + num + r")"
            prep = r"(?:(?:в|во|на|on|at)\s+)?"
            not_unit = (
                r"(?!\s*(?:раз|минут|мин\b|час|сек|дн|дней|недел|месяц|лет|год|"
                r"челов|штук|числ|times|minutes?|mins?|hours?|days?|weeks?|months?|years?|people))"
            )
            cls._ALT_RE = _re.compile(
                r"(?<![\w:])(?P<p1>" + prep + r")(?P<i1>" + item + r")\s*,?\s+(?:или|либо|or)\s+"
                + r"(?P<p2>" + prep + r")(?P<i2>" + item + r")(?![\w:])" + not_unit,
                _re.IGNORECASE,
            )
        return bool(cls._ALT_RE.search(text))

    _ENUM_RE = None

    @classmethod
    def _enumerated_days(cls, text):
        """«в пн, ср и пт в 10 созвон», «on monday, wednesday and friday at 10 call» —
        несколько отдельных разовых событий → список фраз, по одной на день. Повторы
        («по пн, ср и пт», «каждый понедельник и среду», «every monday and …») не трогаем."""
        import re as _re

        if cls._ENUM_RE is None:
            wd_ru = (r"понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье|"
                     r"пн|вт|ср|чт|пт|сб|вс")
            wd_en = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun"
            cls._ENUM_RE = (
                _re.compile(r"(?<![\w])во?\s+(" + wd_ru + r")((?:\s*(?:,|и)\s*(?:во?\s+)?(?:" + wd_ru +
                            r"))+)(?![\w])", _re.IGNORECASE),
                _re.compile(r"\b(?:on\s+)?(" + wd_en + r")((?:\s*(?:,|and|&)\s*(?:on\s+)?(?:" + wd_en +
                            r"))+)\b", _re.IGNORECASE),
                wd_ru, wd_en,
            )
        ru_re, en_re, wd_ru, wd_en = cls._ENUM_RE
        for rx, wd, prep in ((ru_re, wd_ru, "ru"), (en_re, wd_en, "en")):
            m = rx.search(text)
            if not m:
                continue
            before = text[:m.start()].lower()
            if _re.search(r"(?:кажд\w+|по|every|each|except|excluding|but\s+not|кроме|"
                          r"исключая|исключением)\s*$", before):
                continue  # повтор или исключение из правила, а не перечисление разовых дней
            days = [m.group(1)] + _re.findall(wd, m.group(2), flags=_re.IGNORECASE)
            if len(days) < 2:
                continue
            out = []
            for d in days:
                if prep == "ru":
                    pre = "во" if d.lower() in ("вторник", "вт") else "в"
                    out.append(text[:m.start()] + pre + " " + d + text[m.end():])
                else:
                    out.append(text[:m.start()] + "on " + d + text[m.end():])
            return [" ".join(o.split()) for o in out]
        return []

    @classmethod
    def _alternative_texts(cls, text):
        """«в понедельник или во вторник созвон» → ["в понедельник созвон", "во вторник созвон"]."""
        if not cls._alternative_dates(text):
            return []
        m = cls._ALT_RE.search(text)
        p1, p2 = m.group("p1"), m.group("p2") or m.group("p1")
        head, tail = text[:m.start()], text[m.end():]
        # «либо в пн либо во вт»: ведущий «либо» не нужен ни в одном варианте
        import re as _re

        head = _re.sub(r"(?:либо|or|или)\s*$", "", head, flags=_re.IGNORECASE)
        return [
            " ".join((head + p1 + m.group("i1") + tail).split()),
            " ".join((head + p2 + m.group("i2") + tail).split()),
        ]

    _SPOKEN_HM_RE = None
    _SPOKEN_HM_STOP = None

    # разговорные формы времени суток → базовые (длина сохраняется пробелами)
    _RU_DAYPART_ALIASES = {
        "вечерком": "вечером",
        "вечерочком": "вечером",
        "утречком": "утром",
        "с утречка": "с утра",
        "поутру": "утром",
        "ночкой": "ночью",
        "пол часа": "полчаса",
        "пол-часа": "полчаса",
        "полчасика": "полчаса",
    }
    _RU_DAYPART_RE = None

    _NORM_CACHE: Dict[str, str] = {}
    _NORM_CACHE_MAX = 512

    @classmethod
    def _normalize_ru(cls, text):
        """Кэшируемая обёртка нормализации (чистая функция строки)."""
        r = cls._NORM_CACHE.get(text)
        if r is None:
            if len(cls._NORM_CACHE) >= cls._NORM_CACHE_MAX:
                cls._NORM_CACHE.clear()
            r = cls._NORM_CACHE[text] = cls._normalize_ru_raw(text)
        return r

    @classmethod
    def _normalize_ru_raw(cls, text):
        """Нормализация RU-текста перед токенизацией."""
        import re as _re

        if cls._RU_DAYPART_RE is None:
            keys = sorted(cls._RU_DAYPART_ALIASES, key=len, reverse=True)
            cls._RU_DAYPART_RE = _re.compile(
                r"(?<![\w])(" + "|".join(_re.escape(k) for k in keys) + r")(?![\w])",
                _re.IGNORECASE,
            )

        def repl(m):
            src = m.group(1)
            dst = cls._RU_DAYPART_ALIASES[_re.sub(r"\s+", " ", src.lower())]
            return dst + " " * (len(src) - len(dst))

        text = cls._RU_DAYPART_RE.sub(repl, text)
        # опечатки во временных словах: «завтро», «понедельнек», «сентебря»
        from .typo import ru_fixer

        text = _re.sub(
            r"(?<![\w])(?:седня|сёдня|сення|сиводня|севодня|сегодн)(?![\w])", "сегодня", text,
            flags=_re.IGNORECASE,
        )
        text = ru_fixer().fix_text(text)
        # «прошлой ночью» = вчера ночью; «рано утром», «поздно вечером» — уточнение, не название
        text = _re.sub(r"(?<![\w])прошл(?:ой|ую)\s+ночь(?:ю)?(?![\w])", "вчера ночью", text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])(?:рано|поздно)\s+(?=(?:утром|вечером|ночью|утра|вечера|ночи)(?![\w]))", "",
                       text, flags=_re.IGNORECASE)
        # «в 1 квартале», «в 2-м квартале», «в IV квартале» → «в первом квартале»
        _Q = {"1": "первом", "2": "втором", "3": "третьем", "4": "четвёртом",
              "i": "первом", "ii": "втором", "iii": "третьем", "iv": "четвёртом"}
        text = _re.sub(
            r"(?<![\w])(в|во)\s+(iv|iii|ii|i|[1-4])(?:-?(?:м|ом|й))?\s+(?=квартал)",
            lambda m: "%s %s " % ("в", _Q[m.group(2).lower()]), text, flags=_re.IGNORECASE,
        )
        # «через сутки», «через двое суток» → календарные дни (как «in a day»)
        text = _re.sub(r"(?<![\w])через\s+сутки(?![\w])", "через 1 день", text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])через\s+(двое|трое|2|3)\s+суток(?![\w])",
                       lambda m: "через %s дня" % {"двое": "2", "трое": "3"}.get(m.group(1).lower(), m.group(1)),
                       text, flags=_re.IGNORECASE)
        # ISO «2026-10-01T09:00» → «2026-10-01 09:00»
        text = _re.sub(r"(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2})", r"\1 \2", text)
        # «весь день», «целый день» — это просто день; «всю неделю» — эта неделя
        text = _re.sub(r"(?<![\w])(?:весь|целый)\s+(?=день(?![\w]))", "", text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])всю\s+следующую\s+неделю(?![\w])", "на следующей неделе", text,
                       flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])всю\s+неделю(?![\w])", "на этой неделе", text, flags=_re.IGNORECASE)
        # «двадцать три» — это 23, а не «20 часов 3 минуты» («в двадцать три ноль ноль»)
        text = _re.sub(
            r"(?<![\w])двадцать\s+(один|одна|одну|два|две|три)(?![\w])",
            lambda m: str(20 + {"один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3}[m.group(1).lower()]),
            text, flags=_re.IGNORECASE,
        )
        # «минут на 20», «часа на 2» (разговорное) → «на 20 минут», «на 2 часа»
        text = _re.sub(r"(?<![\w])минут\s+на\s+(\d{1,3})(?![\w:])", r"на \1 минут", text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])час(?:а|ов)?\s+на\s+(\d{1,2})(?![\w:])", r"на \1 часа", text,
                       flags=_re.IGNORECASE)
        # «длительностью 2 часа» → «на 2 часа»
        text = _re.sub(r"(?<![\w])(?:длительностью|продолжительностью)(?![\w])", "на", text,
                       flags=_re.IGNORECASE)
        # окно «после X, но до Y», «не раньше X и не позже Y» → «с X до Y»
        _T = r"(\d{1,2}(?::\d{2})?)"
        text = _re.sub(
            r"(?<![\w])(?:после|не\s+раньше)\s+" + _T +
            r"\s*,?\s+(?:но\s+|и\s+)?(?:до|не\s+позже|не\s+позднее)\s+" + _T + r"(?![\w:])",
            r"с \1 до \2", text, flags=_re.IGNORECASE,
        )
        # «в районе 5» → «около 5»
        text = _re.sub(r"(?<![\w])в\s+районе\s+(?=\d)", "около ", text, flags=_re.IGNORECASE)
        # «в ближайшие 2 часа», «в течение ближайших 2 часов» → «в течение 2 часов»
        text = _re.sub(r"(?<![\w])(?:в\s+ближайшие|в\s+течение\s+ближайших)\s+(?=\d|\w+\s+(?:час|минут|дн))",
                       "в течение ", text, flags=_re.IGNORECASE)
        # «не раньше 10» → открытое начало, как «после 10»
        text = _re.sub(r"(?<![\w])не\s+раньше\s+(?=\d)", "после ", text, flags=_re.IGNORECASE)
        # полдень/полночь как граница диапазона: «с 10 до полудня», «с полудня до 15»,
        # «с 22 до полуночи» → окно, а не дедлайн
        text = _re.sub(r"(?<![\w])(с\s+\d{1,2}(?::\d{2})?\s+)до\s+полудня(?![\w])", r"\g<1>до 12:00", text,
                       flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])(с\s+\d{1,2}(?::\d{2})?\s+)до\s+полуночи(?![\w])", r"\g<1>до 00:00", text,
                       flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])с\s+полудня\s+(?=до\s+\d)", "с 12:00 ", text, flags=_re.IGNORECASE)
        # «с утра до полудня», «с утра до 12:00» → «с 9:00 до …» (окно, а не дедлайн)
        text = _re.sub(r"(?<![\w])с\s+утра\s+до\s+полудня(?![\w])", "с 9:00 до 12:00", text,
                       flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])с\s+утра\s+до\s+(?=\d)", "с 9:00 до ", text, flags=_re.IGNORECASE)
        # «с этого момента до пятницы» → «до пятницы»
        text = _re.sub(r"(?<![\w])(?:с\s+этого\s+момента|отныне)\s+до\s+", "до ", text,
                       flags=_re.IGNORECASE)
        # «каждый час», «ежечасно» → «каждые 1 час»
        text = _re.sub(r"(?<![\w])(?:каждый\s+час|ежечасно)(?![\w])", "каждые 1 час", text,
                       flags=_re.IGNORECASE)
        # «каждые выходные», «в каждые выходные» → по субботам и воскресеньям
        text = _re.sub(r"(?<![\w])(?:в\s+)?каждые\s+выходные(?![\w])", "по субботам и воскресеньям",
                       text, flags=_re.IGNORECASE)
        # ── повторы с интервалом (разговорные формы) → «каждые N <единиц>» ──
        _ORD = {"вторую": "2", "второй": "2", "второе": "2", "третью": "3", "третий": "3",
                "третье": "3", "четвёртую": "4", "четвертую": "4", "четвёртый": "4",
                "четвертый": "4"}
        # «каждую вторую неделю», «каждый второй месяц», «каждый третий день»
        text = _re.sub(
            r"(?<![\w])кажд\w+\s+(вторую|второй|второе|третью|третий|третье|четвёртую|четвертую|"
            r"четвёртый|четвертый)\s+(недел\w*|месяц\w*|день|дня|год\w*)(?![\w])",
            lambda m: "каждые %s %s" % (
                _ORD[m.group(1).lower()],
                {"н": "недели", "м": "месяца", "д": "дня", "г": "года"}[m.group(2).lower()[0]],
            ),
            text, flags=_re.IGNORECASE,
        )
        # «раз в 2 недели», «раз в три месяца» → «каждые …» (в т.ч. с «по понедельникам»)
        text = _re.sub(r"(?<![\w])раз\s+в\s+(?=(?:\d+|два|две|три|четыре|пять|шесть)\s+(?:недел|месяц|дн|год))",
                       "каждые ", text, flags=_re.IGNORECASE)
        # «раз в квартал», «каждый квартал», «ежеквартально»
        text = _re.sub(r"(?<![\w])(?:раз\s+в\s+квартал|каждый\s+квартал|ежеквартально)(?![\w])",
                       "каждые 3 месяца", text, flags=_re.IGNORECASE)
        # «раз в полгода», «каждые полгода», «раз в пол года»
        text = _re.sub(r"(?<![\w])(?:раз\s+в|каждые)\s+пол\s*-?\s*года(?![\w])",
                       "каждые 6 месяцев", text, flags=_re.IGNORECASE)
        # «раз в год / месяц / неделю / день» без числа
        # «раз в год», «каждый год» (без даты сразу за ним) → «ежегодно»
        text = _re.sub(r"(?<![\w])(?:раз\s+в\s+год|каждый\s+год)(?![\w])(?!\s+\d)", "ежегодно", text,
                       flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])раз\s+в\s+день(?![\w])", "каждый день", text, flags=_re.IGNORECASE)
        # «по понедельникам через неделю», «через неделю по средам» — это «через раз»
        _DAYS_PL = r"по\s+(?:понедельникам|вторникам|средам|четвергам|пятницам|субботам|воскресеньям)" \
                   r"(?:\s*(?:,|и)\s*(?:понедельникам|вторникам|средам|четвергам|пятницам|субботам|воскресеньям))*"
        text = _re.sub(r"(?<![\w])(" + _DAYS_PL + r")\s+через\s+неделю(?![\w])", r"каждые 2 недели \1",
                       text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])через\s+неделю\s+(" + _DAYS_PL + r")", r"каждые 2 недели \1",
                       text, flags=_re.IGNORECASE)
        # «(в) последний/первый рабочий день каждого месяца» → рабочая форма повтора
        text = _re.sub(r"(?<![\w])(?:в\s+)?(первый|последний)\s+рабочий\s+день\s+каждого\s+месяца(?![\w])",
                       r"каждый \1 рабочий день месяца", text, flags=_re.IGNORECASE)
        # «каждый год 1 сентября» → «ежегодно 1 сентября» (форма ежегодного повтора)
        text = _re.sub(r"(?<![\w])кажд\w+\s+год\s+(?=\d{1,2}\s+[а-яё])", "ежегодно ", text,
                       flags=_re.IGNORECASE)
        # «к концу дня/недели/месяца» = «до конца …» (дедлайн)
        text = _re.sub(r"(?<![\w])к\s+концу(?![\w])", "до конца", text, flags=_re.IGNORECASE)
        # «в первых числах октября» → «в начале октября»
        text = _re.sub(r"(?<![\w])в\s+первых\s+числах(?![\w])", "в начале", text, flags=_re.IGNORECASE)
        # «в следующий рабочий день» → «через 1 рабочий день»
        text = _re.sub(r"(?<![\w])(?:в\s+)?следующий\s+рабочий\s+день(?![\w])", "через 1 рабочий день",
                       text, flags=_re.IGNORECASE)
        # «через пару часов/дней» → «через 2 …»
        text = _re.sub(r"(?<![\w])через\s+пар[уы](?![\w])", "через 2", text, flags=_re.IGNORECASE)
        # «полторы недели», «полтора дня» → десятичная запись, которую понимает парсер
        # (запятая, а не точка: «1.5» токенизатор понял бы как дату 1 мая)
        text = _re.sub(r"(?<![\w])полторы\s+недел", "1,5 недел", text, flags=_re.IGNORECASE)
        text = _re.sub(r"(?<![\w])полтора\s+дн", "1,5 дн", text, flags=_re.IGNORECASE)
        # «в 10-00», «в 9-05» — минуты через дефис (не диапазон «10-11»)
        text = _re.sub(r"(?<![\d:.\-])([01]?\d|2[0-3])[-\u2013](0\d)(?![\d:.\-])", r"\1:\2", text)
        # «10ч30», «10 ч 30» → «10:30»
        text = _re.sub(r"(?<![\d:])([01]?\d|2[0-3])\s*ч\s*([0-5]\d)(?![\d:])", r"\1:\2", text,
                       flags=_re.IGNORECASE)
        # «без 15 десять», «без пятнадцати 10» → «без пятнадцати десять» (форма, которую
        # понимает распознаватель времени); для 13–23 — сразу «H:MM»
        _MIN_GEN = {5: "пяти", 10: "десяти", 15: "пятнадцати", 20: "двадцати", 25: "двадцати пяти"}
        _MIN_GEN_R = {v: k for k, v in _MIN_GEN.items()}
        _MIN_GEN_R["четверти"] = 15
        _HOUR_NOM = {1: "час", 2: "два", 3: "три", 4: "четыре", 5: "пять", 6: "шесть", 7: "семь",
                     8: "восемь", 9: "девять", 10: "десять", 11: "одиннадцать", 12: "двенадцать"}
        _HOUR_NOM_R = {v: k for k, v in _HOUR_NOM.items()}

        def _bez(m):
            mv, hv = m.group(1).lower(), m.group(2).lower()
            mins = int(mv) if mv.isdigit() else _MIN_GEN_R.get(_re.sub(r"\s+", " ", mv))
            hour = int(hv) if hv.isdigit() else _HOUR_NOM_R.get(hv)
            if mins is None or hour is None or not (1 <= mins <= 30) or not (1 <= hour <= 23):
                return m.group(0)
            if hour > 12:
                return "%d:%02d" % (hour - 1, 60 - mins)
            if mins not in _MIN_GEN:
                return m.group(0)
            return "без %s %s" % (_MIN_GEN[mins], _HOUR_NOM[hour])

        text = _re.sub(
            r"(?<![\w])без\s+(\d{1,2}|двадцати\s+пяти|пятнадцати|двадцати|четверти|десяти|пяти)"
            r"(?:\s+минут\w*)?\s+(\d{1,2}|" + "|".join(sorted(_HOUR_NOM_R, key=len, reverse=True))
            + r")(?![\w:])",
            _bez, text, flags=_re.IGNORECASE,
        )
        # «каждое утро», «по вечерам» → ежедневно + часть суток; «по выходным» → сб+вс
        for src, dst in (
            (r"каждое\s+утро", "каждый день утром"),
            (r"каждый\s+вечер", "каждый день вечером"),
            (r"каждую\s+ночь", "каждый день ночью"),
            (r"по\s+утрам", "каждый день утром"),
            (r"по\s+вечерам", "каждый день вечером"),
            (r"по\s+ночам", "каждый день ночью"),
            (r"по\s+выходным", "по субботам и воскресеньям"),
        ):
            text = _re.sub(r"(?<![\w])" + src + r"(?![\w])", dst, text, flags=_re.IGNORECASE)
        # «через час пятнадцать», «через 2 часа 30» → «через N минут»
        _MIN_WORDS = {
            "пять": 5, "десять": 10, "пятнадцать": 15, "двадцать": 20, "двадцать пять": 25,
            "тридцать": 30, "сорок": 40, "сорок пять": 45, "пятьдесят": 50,
        }

        def _hm(m):
            hours = int(m.group(1)) if m.group(1) else 1
            mv = m.group(3).lower()
            mins = int(mv) if mv.isdigit() else _MIN_WORDS[_re.sub(r"\s+", " ", mv)]
            if mins > 59:
                return m.group(0)
            return "через %d минут" % (hours * 60 + mins)

        text = _re.sub(
            r"(?<![\w])через\s+(?:(\d{1,2})\s+)?(час|часа|часов)\s+"
            r"(\d{1,2}|двадцать\s+пять|сорок\s+пять|пятнадцать|двадцать|тридцать|сорок|пятьдесят|десять|пять)"
            r"(?:\s+минут\w*)?(?![\w:.])",
            _hm, text, flags=_re.IGNORECASE,
        )
        # «пн-пт» → «с пн по пт» (диапазон дней, как «с понедельника по пятницу»)
        text = _re.sub(
            r"(?<![\w])(пн|вт|ср|чт|пт|сб|вс)\s*[-\u2013\u2014]\s*(пн|вт|ср|чт|пт|сб|вс)(?![\w])",
            r"с \1 по \2", text, flags=_re.IGNORECASE,
        )
        # «в 1930» / «к 0830» → «в 19:30» (длина меняется на 1 — позиции берутся
        # из токенов этой же строки, исходный text в разметку не попадает)
        text = _re.sub(
            # годы не трогаем: 20xx всегда, любой — если дальше «году/года/г.» («в 1945 году»)
            r"(?<![\w:.])((?:в|во|к|до|с|со|на)\s+)(?!20\d\d)([01]\d|2[0-3])([0-5]\d)(?![\w:.])"
            r"(?!\s*(?:году|года|год|гг?\.?)(?![\w]))",
            lambda m: m.group(1) + m.group(2) + ":" + m.group(3),
            text,
            flags=_re.IGNORECASE,
        )
        return cls._join_spoken_minutes(text)

    @classmethod
    def _join_spoken_minutes(cls, text):
        """«в 11 30» → «в 11:30» (разговорная/голосовая запись времени).

        Только после временного предлога (в/во/с/со/до/к/на/по/около), минуты —
        ровно две цифры 00–59, и следом не идёт единица/месяц/«числа»
        («с 10 30 сентября», «в 10 15 минут» не трогаем). Длина строки
        сохраняется (пробел → двоеточие), позиции токенов не сдвигаются.
        """
        import re as _re

        if cls._SPOKEN_HM_RE is None:
            cls._SPOKEN_HM_RE = _re.compile(
                r"(?<![\w:.])((?:в|во|с|со|до|к|на|по|около)\s+)"
                r"([01]?\d|2[0-3]) ([0-5]\d)(?![\w:.,/-])(\s+([а-яёa-z]+))?",
                _re.IGNORECASE,
            )
            stop = set()
            for lst in (
                Keywords.SECOND, Keywords.MINUTE, Keywords.HOUR, Keywords.DAY,
                Keywords.WEEK, Keywords.MONTH, Keywords.YEAR,
            ):
                stop.update(lst)
            for mw in Keywords.months():
                stop.update(mw)
            stop.update({"число", "числа", "числу", "раз", "раза", "человек", "штук"})
            cls._SPOKEN_HM_STOP = stop

        def repl(m):
            nxt = (m.group(5) or "").lower()
            if nxt and (nxt in cls._SPOKEN_HM_STOP or nxt.startswith(("минут", "час", "сек"))):
                return m.group(0)
            return m.group(1) + m.group(2) + ":" + m.group(3) + (m.group(4) or "")

        return cls._SPOKEN_HM_RE.sub(repl, text)

    _TZ_TOKENS = {"мск", "msk", "utc", "gmt"}
    _TZ_CITIES = {"москве", "москвы", "алматы", "лондону", "лондона", "киеву", "минску"}

    _RRULE_IDX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

    def _ambiguous_past_period(self, text):
        """True для «на прошлой неделе в 14:30» (только время, без дня),
        «в прошлом месяце/квартале/году в 14:30», «в прошлом квартале/году в четверг»
        и т.п. — прошлый ПЕРИОД + время/день, где конкретный момент не определяется.
        Не срабатывает на: «на прошлой неделе в четверг [время]» (день недели задан),
        «в прошлом месяце 15 числа» (месяц+число продуктивны), чистый период без времени."""
        import re as _re
        vals = text.lower().replace(",", " ").split()
        week = set(Keywords.WEEK)
        month = set(Keywords.MONTH)
        quarter = set(Keywords.QUARTER)
        year = set(Keywords.YEAR)
        prev = set(Keywords.PREVIOUS_MOD)
        days = set()
        for d in Keywords.days_of_week():
            days.update(d)
        unit = None
        for i in range(len(vals) - 1):
            if vals[i] in prev:
                nx = vals[i + 1]
                if nx in week or nx in month or nx in quarter or nx in year:
                    unit = nx
                    break
        if unit is None:
            return False
        has_wd = any(v in days for v in vals)
        has_daynum = any(_re.match(r"^\d{1,2}$", v) for v in vals)
        has_time = any(_re.match(r"^\d{1,2}:\d{2}$", v) for v in vals)
        if unit in week:
            # неделя: неоднозначно только если время без дня недели и без числа
            return has_time and not has_wd and not has_daynum
        # месяц/квартал/год
        if unit in month and has_daynum and not has_time and not has_wd:
            return False  # «в прошлом месяце 15 числа» — продуктивно (обработает распознаватель)
        # во всех прочих комбинациях прошлого месяца/квартала/года момент неоднозначен
        return has_time or has_wd or has_daynum

    def _conflicting_day_markers(self, text):
        """True, если во фразе ≥2 РАЗНЫХ взаимоисключающих относительных дня
        (вчера/сегодня/завтра/послезавтра/позавчера + yesterday/today/tomorrow/
        day after tomorrow), либо относительный день вместе с маркером года
        (в прошлом/следующем году, last/next year). Такой ввод неоднозначен → None.
        Вызывается на ОДИНОЧНОМ сегменте: parse_multi уже раздробил фразу."""
        import re as _re
        low = text.lower()
        # Составные EN-формы содержат подстроки tomorrow/yesterday — маскируем их
        # ДО подсчёта одиночных, иначе «day after tomorrow» ложно = at+tomorrow.
        masked = _re.sub(r"\bday after tomorrow\b", " __AT__ ", low)
        masked = _re.sub(r"\bday before yesterday\b", " __BY__ ", masked)
        days = set()
        if "__AT__" in masked or _re.search(r"\bпослезавтра\b", low): days.add("at")
        if "__BY__" in masked or _re.search(r"\bпозавчера\b", low): days.add("by")
        if _re.search(r"\bзавтра\b", low) or _re.search(r"\btomorrow\b", masked): days.add("tom")
        if _re.search(r"\bвчера\b", low) or _re.search(r"\byesterday\b", masked): days.add("yes")
        if _re.search(r"\bсегодня\b", low) or _re.search(r"\btoday\b", masked): days.add("tod")
        year_marker = bool(
            _re.search(r"\b(?:прошл\w*|следующ\w*|будущ\w*)\s+год\w*", low)
            or _re.search(r"\b(?:last|next)\s+year\b", low)
        )
        if len(days) >= 2:
            return True
        if year_marker and days:
            return True
        return False

    def _invalid_explicit_date(self, tokens):
        """True, если во фразе есть явная невозможная календарная дата
        (день+месяц[+год]): «31 февраля», «31 апреля», «29 февраля 2025»."""
        from calendar import monthrange
        from ..dict.keywords import Keywords

        lookup = {}
        for idx, variants in enumerate(Keywords.months()):
            for v in variants:
                lookup[v] = idx + 1
        for i, tok in enumerate(tokens):
            month = lookup.get(tok.value.lower()) or lookup.get(tok.normalized)
            if not month:
                continue
            day = self._day_before_month(tokens, i)
            if day is not None:
                if not (1 <= day <= 31):
                    continue
                year = None
                if (
                    i + 1 < len(tokens)
                    and tokens[i + 1].value.isdigit()
                    and len(tokens[i + 1].value) == 4
                ):
                    year = int(tokens[i + 1].value)
                if year is not None:
                    maxd = monthrange(year, month)[1]
                else:
                    maxd = 29 if month == 2 else monthrange(2001, month)[1]
                if day > maxd:
                    return True
        return False

    def _day_before_month(self, tokens, idx):
        """День непосредственно перед tokens[idx]=месяц: цифра, «N-го»,
        одиночное порядковое слово или составное («тридцать первого»).
        → int | None."""
        import re as _re
        from ..dict.keywords import Keywords

        if idx == 0:
            return None
        prev = tokens[idx - 1].value.lower()
        if prev.isdigit():
            return int(prev)
        mm = _re.match(r"^(\d+)-?(?:го|е)?$", prev)
        if mm:
            return int(mm.group(1))
        single = Keywords.parse_ordinal_day(prev)
        if single is not None:
            if idx - 2 >= 0:
                comp = Keywords.parse_ordinal_day_2(tokens[idx - 2].value, prev)
                if comp is not None:
                    return comp
            return single
        return None

    def _snap_setpos(self, dt, rec, now):
        from calendar import monthrange as _mr

        if rec.frequency != "MONTHLY" or not rec.by_day:
            return
        if any(d not in self._RRULE_IDX for d in rec.by_day):
            return
        wds = {self._RRULE_IDX[d] for d in rec.by_day}
        pos = rec.by_set_pos if isinstance(rec.by_set_pos, int) else rec.by_set_pos[0]
        t = dt.date_from
        y, m = now.year, now.month
        for _ in range(26):
            days = [d for d in range(1, _mr(y, m)[1] + 1) if t.replace(year=y, month=m, day=1).replace(day=d).weekday() in wds]
            if days and -len(days) <= pos <= len(days) and pos != 0:
                day = days[pos - 1] if pos > 0 else days[pos]
                cand = t.replace(year=y, month=m, day=day)
                ok = cand.date() >= now.date() if not dt.has_time else cand >= now
                if ok:
                    dt.date_from = cand
                    if dt.date_to is not None and dt.date_to.date() == t.date():
                        dt.date_to = dt.date_to.replace(year=y, month=m, day=day)
                    return
            m += 1
            if m > 12:
                m, y = 1, y + 1

    def _snap_recurrence_start(self, dt, now):
        """Инвариант: при BYDAY/BYMONTHDAY стартовая дата обязана удовлетворять
        правилу. Снапим DTSTART на первое валидное вхождение ≥ now."""
        if dt is None:
            return
        rec = getattr(dt, "recurrence", None)
        if rec is None:
            return
        if rec.by_month:  # годовые с датой — старт уже выставлен распознавателем
            return
        if rec.frequency in ("MINUTELY", "HOURLY"):
            # частый повтор: с окном часов первый слот уже посчитан с учётом дней;
            # без окна — стартуем сейчас, если сегодня разрешённый день
            codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
            if getattr(rec, "by_hour", None) or not rec.by_day or codes[now.weekday()] in rec.by_day:
                return
            # сегодня не разрешённый день: серия начинается с полуночи ближайшего разрешённого
            k = next(i for i in range(1, 8) if codes[(now.weekday() + i) % 7] in rec.by_day)
            dt.date_from = dt.date_to = (now + timedelta(days=k)).replace(hour=0, minute=0, second=0, microsecond=0)
            return
        if rec.by_set_pos is not None:
            # BYSETPOS («первый выходной месяца»): с календарём праздников старт уже
            # учитывает праздники (RRULE их не выражает) — не трогаем; без календаря
            # снапим на первое вхождение правила ≥ now
            if getattr(self.config, "calendar", None) is None:
                self._snap_setpos(dt, rec, now)
            return
        t = dt.date_from
        new = None
        if rec.by_day:
            # позиционные коды (например «-1SA» — последняя суббота) не снапим
            if any(d not in self._RRULE_IDX for d in rec.by_day):
                return
            idx = sorted(self._RRULE_IDX[d] for d in rec.by_day)
            best = None
            for wd in idx:
                delta = (wd - now.weekday()) % 7
                base_day = now + timedelta(days=delta)
                cand = t.replace(year=base_day.year, month=base_day.month, day=base_day.day)
                if dt.has_time and delta == 0 and cand <= now:
                    cand += timedelta(days=7)
                if best is None or cand < best:
                    best = cand
            new = best
        elif rec.by_month_day and len(rec.by_month_day) > 1:
            # несколько чисел месяца («по чётным числам») — ближайшее подходящее ≥ now
            valid = {x for x in rec.by_month_day if x > 0}
            cand = t.replace(year=now.year, month=now.month, day=now.day)
            if dt.has_time and cand <= now:
                cand += timedelta(days=1)
            for _ in range(62):
                if cand.day in valid:
                    new = cand
                    break
                cand += timedelta(days=1)
        elif rec.by_month_day:
            md = rec.by_month_day[0]
            if md < 1:  # -1 = последний день месяца: старт уже выставлен распознавателем
                return
            y, mo = now.year, now.month
            cand = self._safe_month_day(y, mo, md, t)
            need_next = (
                cand is None
                or cand.date() < now.date()
                or (cand.date() == now.date() and dt.has_time and cand <= now)
            )
            if need_next:
                # Ищем первый месяц, в котором день md существует (февраль/30-дневные
                # месяцы пропускаем: «каждый месяц 31 числа» от 31.01 → 31.03).
                cand = None
                y2, mo2 = y, mo
                for _ in range(12):
                    mo2 += 1
                    if mo2 > 12:
                        mo2 = 1
                        y2 += 1
                    cand = self._safe_month_day(y2, mo2, md, t)
                    if cand is not None:
                        break
            new = cand
        elif dt.has_time and rec.frequency in ("DAILY", "WEEKLY"):
            # чистый DAILY/WEEKLY без by_day/by_month_day с точным временем:
            # если сегодняшнее вхождение уже прошло — сдвигаем anchor на
            # ближайшее будущее срабатывание (reminder-семантика). RRULE не меняем.
            if t <= now:
                step_days = rec.interval * (7 if rec.frequency == "WEEKLY" else 1)
                step = timedelta(days=step_days)
                cand = t
                while cand <= now:
                    cand += step
                new = cand
        if new is not None:
            span = dt.date_to - dt.date_from
            if not dt.has_time:
                new = new.replace(hour=0, minute=0, second=0, microsecond=0)
            dt.date_from = new
            dt.date_to = new + span
            # после снапа anchor пересчитываем is_past: сдвинутое в будущее
            # вхождение серии не должно оставаться помеченным прошлым
            if dt.has_time:
                dt.is_past = dt.date_from < now

    @staticmethod
    def _safe_month_day(y, mo, md, t):
        from calendar import monthrange

        if md < 1 or md > monthrange(y, mo)[1]:
            return None
        return t.replace(year=y, month=mo, day=md)

    def _has_timezone(self, tokens):
        import re as _re

        for idx, t in enumerate(tokens):
            v = t.value.lower()
            if v in self._TZ_TOKENS:
                return True
            if _re.match(r"^(gmt|utc)[+\-]\d{1,2}$", v):
                return True
            # «по Москве/Алматы»
            if v in self._TZ_CITIES and idx > 0 and tokens[idx - 1].value.lower() == "по":
                return True
        return False

    def _apply_weekday_exclusions(self, dates):
        """«каждый день кроме <дни>» → FREQ=WEEKLY;BYDAY=<остальные дни>.

        Срабатывает только когда recurrence=DAILY и ВСЕ исключения — это дни
        недели/выходные (несут _excl_weekdays). Одноразовые даты-исключения
        остаются в .exclusions без переписывания правила.
        """
        from ..dict.keywords import Keywords as _KW

        for d in dates:
            rec = getattr(d, "recurrence", None)
            if not rec or not d.exclusions:
                continue
            if rec.frequency == "WEEKLY" and rec.by_day:
                # «каждый будний день кроме пятницы» → убрать день из BYDAY
                excl = set()
                for ex in d.exclusions:
                    excl.update(getattr(ex, "_excl_weekdays", None) or ())
                codes = [_KW.RRULE_DAYS[k] for k in excl]
                kept = [c for c in rec.by_day if c not in codes]
                if excl and kept:
                    rec.by_day = kept
                continue
            if rec.frequency != "DAILY":
                continue
            excl_wds = set()
            all_weekday = True
            for ex in d.exclusions:
                wds = getattr(ex, "_excl_weekdays", None)
                if wds:
                    excl_wds.update(wds)
                else:
                    all_weekday = False
            if excl_wds and all_weekday:
                keep = [i for i in range(7) if i not in excl_wds]
                if keep:
                    rec.frequency = "WEEKLY"
                    rec.by_day = [_KW.RRULE_DAYS[i] for i in keep]

    def _merge_date_and_time(self, dates, now):
        if len(dates) < 2:
            return dates
        sorted_dates = sorted(dates, key=lambda d: d.start)
        merged = set()
        new_tokens = []
        md = getattr(self.config, "merge_distance", 50)
        for i in range(len(sorted_dates)):
            if i in merged:
                continue
            date_tok = sorted_dates[i]
            is_date_tok = (
                date_tok.type in (DateTimeType.SPAN_FORWARD, DateTimeType.SPAN_BACKWARD)
                and not date_tok.has_time
            ) or (
                date_tok.type == DateTimeType.FIXED and date_tok.all_day and not date_tok.has_time
            ) or (
                # однодневный точный период («последний рабочий день месяца») + время
                date_tok.type == DateTimeType.PERIOD and date_tok.all_day and not date_tok.has_time
                and not date_tok.fuzzy and date_tok.date_to is not None
                and date_tok.date_from.date() == date_tok.date_to.date()
            )
            if not is_date_tok:
                continue
            for j in range(len(sorted_dates)):
                if j == i or j in merged:
                    continue
                time_tok = sorted_dates[j]
                if not time_tok.has_time:
                    continue
                # время может стоять и ДО, и ПОСЛЕ даты («завтра в 10» и «в 10 завтра»)
                if time_tok.start >= date_tok.end:
                    gap = time_tok.start - date_tok.end
                elif date_tok.start >= time_tok.end:
                    gap = date_tok.start - time_tok.end
                else:
                    continue  # перекрытие спанов — пропускаем
                if gap > md:
                    continue
                span_start = min(date_tok.start, time_tok.start)
                span_end = max(date_tok.end, time_tok.end)
                used = [(date_tok.start, date_tok.end), (time_tok.start, time_tok.end)]
                if time_tok.type == DateTimeType.PERIOD and time_tok.is_explicit_range:
                    target_date = date_tok.date_from.date()
                    new_from = datetime.combine(target_date, time_tok.date_from.time())
                    new_to = datetime.combine(target_date, time_tok.date_to.time())
                    if new_to <= new_from:
                        new_to += timedelta(days=1)
                    new_dt = DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=new_from,
                        date_to=new_to,
                        has_time=True,
                        start=span_start,
                        end=span_end,
                        confidence=max(date_tok.confidence, time_tok.confidence),
                        recurrence=date_tok.recurrence or time_tok.recurrence,
                        is_past=new_from < now,
                    )
                    new_dt.is_explicit_range = True
                    new_dt.used_spans = used
                    new_tokens.append(new_dt)
                    merged.add(i)
                    merged.add(j)
                    break
                elif time_tok.type == DateTimeType.FIXED and time_tok.is_deadline:
                    # «завтра до 18», «сегодня до полуночи», «в пятницу до 18:00»:
                    # дедлайн на названный день, флаг дедлайна сохраняется.
                    target_date = date_tok.date_from.date()
                    dl_time = time_tok.date_to.time()
                    dl = datetime.combine(target_date, dl_time)
                    if dl_time == datetime.min.time():
                        dl += timedelta(days=1)  # «до полуночи» = конец дня
                    new_dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=min(now, dl),
                        date_to=dl,
                        has_time=True,
                        is_deadline=True,
                        start=span_start,
                        end=span_end,
                        confidence=max(date_tok.confidence, time_tok.confidence),
                        recurrence=date_tok.recurrence or time_tok.recurrence,
                        is_past=dl < now,
                    )
                    new_dt.used_spans = used
                    new_tokens.append(new_dt)
                    merged.add(i)
                    merged.add(j)
                    break
                elif time_tok.type == DateTimeType.FIXED and time_tok.has_time:
                    target_date = date_tok.date_from.date()
                    merge_time = time_tok.date_from.time()
                    # Время привязывается к ЯВНОЙ дате — пересчитываем час по
                    # фиксированному маппингу (1-7→+12), без nearest-future-флипа
                    # сегодняшнего дня (иначе «завтра в 10»/«в 10 завтра» уезжало в 22:00).
                    # ИСКЛЮЧЕНИЕ: явное уточнение «утра/дня/вечера/ночи» уже разрешило
                    # час в распознавателе — его не трогаем («завтра в 7 утра» = 07:00).
                    if hasattr(time_tok, "_raw_hour") and not getattr(
                        time_tok, "_explicit_pod", False
                    ):
                        raw_h = time_tok._raw_hour
                        fixed_h = raw_h + 12 if (1 <= raw_h <= 7 and self.config.prefer_nearest_future) else raw_h
                        raw_m = getattr(time_tok, "_raw_minute", 0)
                        merge_time = datetime(2000, 1, 1, fixed_h, raw_m).time()
                    new_from = datetime.combine(target_date, merge_time)
                    # «сегодня/завтра/в пятницу в полночь» = конец названного дня
                    if getattr(time_tok, "_midnight", False):
                        new_from += timedelta(days=1)
                    new_dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=new_from,
                        date_to=new_from,
                        has_time=True,
                        start=span_start,
                        end=span_end,
                        confidence=max(date_tok.confidence, time_tok.confidence),
                        recurrence=date_tok.recurrence or time_tok.recurrence,
                        is_past=new_from < now,
                    )
                    new_dt.used_spans = used
                    new_tokens.append(new_dt)
                    merged.add(i)
                    merged.add(j)
                    break
                elif (
                    time_tok.type == DateTimeType.PERIOD
                    and time_tok.fuzzy
                    and not time_tok.is_explicit_range
                ):
                    target_date = date_tok.date_from.date()
                    new_from = datetime.combine(target_date, time_tok.date_from.time())
                    new_to = datetime.combine(target_date, time_tok.date_to.time())
                    if new_to <= new_from:
                        new_to += timedelta(days=1)
                    new_dt = DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=new_from,
                        date_to=new_to,
                        has_time=True,
                        fuzzy=True,
                        start=span_start,
                        end=span_end,
                        confidence=max(date_tok.confidence, time_tok.confidence),
                        recurrence=date_tok.recurrence or time_tok.recurrence,
                        # окно части суток целиком прошло («сегодня утром» в 14:00)
                        is_past=date_tok.is_past or new_to < now,
                    )
                    new_dt.used_spans = used
                    new_tokens.append(new_dt)
                    merged.add(i)
                    merged.add(j)
                    break
        result = [d for i, d in enumerate(sorted_dates) if i not in merged]
        result.extend(new_tokens)
        return result

    def _deduplicate(self, dates):
        if len(dates) <= 1:
            return dates

        def dedup_score(d):
            s = d.confidence * 5 + (d.end - d.start) * 0.1
            if d.recurrence:
                s += 3
            if hasattr(d, "is_explicit_range") and d.is_explicit_range:
                s += 2
            if d.has_time:
                s += 1
            return s

        dates.sort(key=lambda d: -dedup_score(d))
        result = []
        used_ranges = []
        for d in dates:
            overlap = any(d.start < e and d.end > s for s, e in used_ranges)
            if not overlap:
                result.append(d)
                used_ranges.append((d.start, d.end))
        return result

    def _select_best(self, dates):
        if not dates:
            return None

        def score(d):
            s = d.confidence * 10
            if d.has_time:
                s += 5
            if hasattr(d, "is_explicit_range") and d.is_explicit_range:
                s += 3
            if d.recurrence:
                s += 2
            if d.type == DateTimeType.PERIOD:
                s += 1
            return s

        return max(dates, key=score)

    def _classify(self, dt, title, source, location=None, duration=None):
        if dt is None:
            return None
        rec = dt.recurrence
        kw = dict(
            source=source,
            confidence=dt.confidence,
            is_past=dt.is_past,
            location=location,
            recurrence=rec,
            exclusions=dt.exclusions if dt.exclusions else None,
        )
        if duration:
            kw["duration_minutes"] = duration
        if hasattr(dt, "_open_start") and dt._open_start:
            return TaskResult(
                title=title, task_type=TaskType.OPEN_START, start_at=dt.date_from, **kw
            )
        if dt.is_deadline:
            return TaskResult(
                title=title,
                task_type=TaskType.DEADLINE,
                deadline=dt.date_to,
                start_at=dt.date_from,
                **kw,
            )
        if dt.fuzzy and not dt.has_time:
            return TaskResult(
                title=title,
                task_type=TaskType.FUZZY,
                start_at=dt.date_from,
                end_at=dt.date_to,
                fuzzy=True,
                **kw,
            )
        if hasattr(dt, "is_explicit_range") and dt.is_explicit_range and dt.has_time:
            return CalendarResult(title=title, start_at=dt.date_from, end_at=dt.date_to, **kw)
        # FIX: fuzzy PERIOD (e.g. "ближе к вечеру") → Task/FUZZY, NOT Calendar
        if dt.type == DateTimeType.PERIOD and dt.fuzzy:
            return TaskResult(
                title=title,
                task_type=TaskType.FUZZY,
                start_at=dt.date_from,
                end_at=dt.date_to,
                fuzzy=True,
                **kw,
            )
        if dt.type == DateTimeType.PERIOD and dt.has_time:
            return CalendarResult(title=title, start_at=dt.date_from, end_at=dt.date_to, **kw)
        if dt.type == DateTimeType.PERIOD and dt.all_day:
            return TaskResult(
                title=title,
                task_type=TaskType.PERIOD,
                start_at=dt.date_from,
                end_at=dt.date_to,
                **kw,
            )
        # Явное время + длительность → событие календаря (start..start+duration)
        if duration and dt.has_time and dt.type != DateTimeType.PERIOD:
            return CalendarResult(
                title=title,
                start_at=dt.date_from,
                end_at=dt.date_from + timedelta(minutes=duration),
                **kw,
            )
        if dt.has_time:
            return ReminderResult(title=title, datetime_at=dt.date_from, **kw)
        if dt.all_day:
            return TaskResult(
                title=title,
                task_type=TaskType.PERIOD,
                start_at=dt.date_from,
                end_at=dt.date_to,
                **kw,
            )
        return TaskResult(
            title=title, task_type=TaskType.PERIOD, start_at=dt.date_from, end_at=dt.date_to, **kw
        )

    def _extract_event_title(self, text, tokens, date_tokens):
        used = set()
        for dt in date_tokens:
            spans = getattr(dt, "used_spans", None) or [(dt.start, dt.end)]
            for a, b in spans:
                for pos in range(a, b):
                    used.add(pos)
        title_parts = []
        # Предлоги-связки НЕ вырезаем из середины title (вариант А:
        # «созвониться с дизайнером», «разобрать … по проекту Atlas»).
        # Они срезаются только в ВЕДУЩЕЙ позиции (leading_preps ниже).
        stop_words = {
            ",",
            "через",
            "после",
            "назад",
            "каждый",
            "каждую",
            "каждое",
            "каждые",
            "каждого",
            "каждой",
            "раз",
            "не",
            "позднее",
            "позже",
            "кроме",
            "исключением",
            "помимо",
            "был",
            "была",
            "было",
            "были",
            # филлеры и команды-обёртки
            "ну",
            "потом",
            "затем",
            "далее",
            "включительно",
            "начиная",
            "ближе",
            "слушай",
            "эээ",
            "ээ",
            "эх",
            "так",
            "типа",
            "поставь",
            "предпоследний",
            "предпоследнюю",
            "предпоследняя",
            "предпоследнее",
            "предпоследнего",
            "запланируй",
            "создай",
            "добавь",
            "напоминание",
            "напоминанием",
            "напомни",
            "напомните",
            "напомнить",
            "напоминалку",
            "пораньше",
            "попозже",
            "раньше",
            # наречия-паразиты и вводные (не влияют на дату, мусор в title)
            "ровно",
            "примерно",
            "где-то",
            "надо",
            "бы",
            "хочу",
            "может",
            "можно",
            "давай",
            "давайте",
            "закинь",
            "строго",
            "желательно",
            "максимум",
            "короче",
            "плз",
            "пожалуйста",
        }
        stop_words |= set(Keywords.START_OF) | set(Keywords.END_OF) | set(Keywords.MIDDLE_OF)
        # числительные словами (два/две/три/сорок/пятьдесят, порядковые) не должны
        # утекать в title: «каждые две недели … синк» → title «синк», не «две синк»
        stop_words |= (
            set(Keywords._NORMALIZED_TO_NUMBER) | set(Keywords._UNITS) | set(Keywords._TENS)
        )
        loc_preps = {"в", "во", "на", "у", "около"}
        for ti, t in enumerate(tokens):
            if any(pos in used for pos in range(t.start, t.end)):
                continue
            v = t.value.lower()
            n = t.normalized
            # «напомнить про договор» — «напомнить» здесь часть смысла, оставляем
            nxt_v = tokens[ti + 1].value.lower() if ti + 1 < len(tokens) else ""
            if v.startswith("напомн") and nxt_v in ("про", "о", "об"):
                title_parts.append((ti, t.value))
                continue
            if v in stop_words:
                continue
            # модификаторы периода в любой падежной форме (следующего/прошлой/…):
            # это часть временного выражения, не должны оставаться в title.
            _PERIOD_MOD_PREFIXES = (
                "следующ", "прошл", "будущ", "ближайш", "предыдущ", "нынешн", "текущ",
            )
            if any(v.startswith(pref) for pref in _PERIOD_MOD_PREFIXES):
                continue
            # «день рождения» — устойчивая фраза, «день» не вырезаем
            nxt_n = tokens[ti + 1].normalized if ti + 1 < len(tokens) else ""
            keep_den = (v in Keywords.DAY or n == "день") and nxt_n.startswith("рожден")
            all_units = (
                Keywords.MINUTE
                + Keywords.HOUR
                + Keywords.DAY
                + Keywords.WEEK
                + Keywords.MONTH
                + Keywords.YEAR
                + Keywords.QUARTER
                + Keywords.HALF_YEAR
            )
            if not keep_den and (v in all_units or n in all_units):
                continue
            skip = False
            for days in Keywords.days_of_week():
                if v in days or n in days:
                    skip = True
                    break
            if skip:
                continue
            for days in Keywords.days_of_week_dative():
                if v in days or n in days:
                    skip = True
                    break
            if skip:
                continue
            for mw in Keywords.months():
                if v in mw or n in mw:
                    skip = True
                    break
            if skip:
                continue
            # Маркер локации считаем локацией (и убираем из title) только если
            # ему предшествует предлог локации (в/во/на/у/около). Иначе это
            # содержательное слово названия ("в 19 кино" → title "кино").
            # предлог локации перед маркером локации («в офисе»): предлог тоже
            # уходит вместе с локацией, чтобы не повисал хвост «встреча в».
            if v in loc_preps:
                nxt_v = tokens[ti + 1].value.lower() if ti + 1 < len(tokens) else None
                if nxt_v in Keywords.LOCATION_MARKERS:
                    continue
            if v in Keywords.LOCATION_MARKERS:
                prev = tokens[ti - 1].value.lower() if ti > 0 else None
                if prev in loc_preps:
                    continue
            if v in _ORDINALS:
                continue
            if t.value.isdigit():
                continue
            title_parts.append((ti, t.value))
        # Срезаем ВЕДУЩИЙ участник/локацию: «с Иваном встреча» → «встреча»,
        # «у клиента встреча» → «встреча». Суффиксы («встреча с командой») не трогаем.
        leading_preps = {"с", "со", "у", "в", "во", "на", "около",
                         "до", "по", "к", "за", "от"}
        # (ведущие предлоги снимаются ниже — только висящие, см. _dangling)
        # «напомни мне …» — «мне» после команды-обёртки не часть названия
        if title_parts and title_parts[0][1].lower() in ("мне", "нам"):
            fti = title_parts[0][0]
            prev_v = tokens[fti - 1].value.lower() if fti > 0 else ""
            if prev_v.startswith("напомн") or fti == 0:
                title_parts = title_parts[1:]
        # Ведущий участник/локация: «с Иваном встреча» → «встреча», «у клиента встреча»
        # → «встреча». Срезаем только если после группы есть ещё слова: «с командой»
        # или «к врачу» — это само название и остаётся целиком.
        if len(title_parts) >= 2:
            fti = title_parts[0][0]
            prev = tokens[fti - 1].value.lower() if fti > 0 else None
            if prev in ("с", "со", "у"):
                title_parts = title_parts[1:]
        if (
            len(title_parts) >= 3
            and title_parts[0][1].lower() in ("с", "со", "у")
            and title_parts[1][0] == title_parts[0][0] + 1  # предлог и его слово рядом
        ):
            title_parts = title_parts[2:]
        # На краях снимаем только ВИСЯЩИЕ предлоги — те, чьё слово съела дата/время
        # («встреча на [2 часа]», «[в следующем месяце] 5 числа»). Предлог со своим
        # словом остаётся частью названия: «к врачу», «на тренировку», «с командой».
        edge_preps = leading_preps | {"около", "от", "у"}
        edge_conj = {"и", "или", "либо", "а", "но"}

        def _dangling(ti):
            """Предлог висит, если следующее слово не попало в название: его забрала
            дата/время («встреча на [2 часа]») или это служебное слово
            («до [следующего] понедельника»). При своём слове предлог остаётся."""
            if ti + 1 >= len(tokens):
                return True  # предлог в конце фразы — указывать не на что
            return (ti + 1) not in {idx for idx, _ in title_parts}

        while title_parts:
            ti, v = title_parts[0]
            v = v.lower()
            if v in edge_conj or (v in edge_preps and _dangling(ti)):
                title_parts = title_parts[1:]
                continue
            break
        while title_parts:
            ti, v = title_parts[-1]
            v = v.lower()
            if v in edge_conj or (v in edge_preps and _dangling(ti)):
                title_parts = title_parts[:-1]
                continue
            break
        title = " ".join(v for _, v in title_parts).strip().strip("- ,;:")
        return title if title else ""


_ORDINALS = set()
for _lst in [
    Keywords.ORDINAL_FIRST,
    Keywords.ORDINAL_SECOND,
    Keywords.ORDINAL_THIRD,
    Keywords.ORDINAL_FOURTH,
    Keywords.ORDINAL_LAST,
]:
    _ORDINALS.update(_lst)

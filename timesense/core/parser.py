"""Основной парсер"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from .config import TimeConfig
from .tokenizer import Tokenizer
from .language import resolve_language
from ..models.datetime_token import DateTimeToken, DateTimeType
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
from ..recognizers.working_context import WorkingContextRecognizer
from ..recognizers.working_days import WorkingDaysRecognizer
from ..recognizers.custom_time import CustomTimeRecognizer
from ..recognizers.ordinal_day import OrdinalDayRecognizer
from ..recognizers.exclusion import ExclusionParser
from ..recognizers.location import LocationExtractor
from ..recognizers.time_of_day import TimeOfDayRecognizer
from ..dict.keywords import Keywords
from typing import List, Optional, Union

ParseResult = Union[ReminderResult, CalendarResult, TaskResult]

logger = logging.getLogger("timesense")


class TimeSenseParser:
    def __init__(self, config: Optional[TimeConfig] = None) -> None:
        self.config = config or TimeConfig()
        self.tokenizer = Tokenizer()
        self._init_recognizers()
        from ..locales.en import EnglishLocaleParser

        self._en = EnglishLocaleParser(self.config)

    def _init_recognizers(self):
        c = self.config
        self.recognizers = [
            DateFormatRecognizer(c),
            CombinedRecognizer(c),
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
        self, text: str, now: Optional[datetime] = None, language: Optional[str] = None
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
        now = now or datetime.now()
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
            parsed = [self.parse(s, now=now, language=language) for s in seg_list]
            if all(r is not None for r in parsed):
                self._chain_multi_dates(seg_list, parsed, now, language)
                return [r for r in parsed if r is not None]
        single = self.parse(text, now=now, language=language)
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
        from datetime import datetime as _dt

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
            cur.datetime_at = _dt.combine(anchor.date(), cur_dt.time())
            if cur.datetime_at >= now:
                cur.is_past = False

    def parse(
        self, text: str, now: Optional[datetime] = None, language: Optional[str] = None
    ) -> Optional[ParseResult]:
        if language is not None and language not in ("auto", "ru", "en"):
            raise ValueError("language must be 'auto', 'ru', 'en' or None, got %r" % (language,))
        if not text or not text.strip():
            return None
        now = now or datetime.now()
        lang = resolve_language(text, language, self.config.default_language)
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
            self._snap_recurrence_start(dt, now)
            result = self._classify(dt, title, text, location, duration)
            if result is not None:
                result.detected_language = "en"
            return result
        tokens = self.tokenizer.tokenize(text)
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
        # Локали, кроме ru, пока не реализованы: en-текст честно не парсим.
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
        self._snap_recurrence_start(best, now)
        result = self._classify(best, title, text, location, duration)
        if result is not None:
            result.detected_language = lang
        return result

    _LOCALES = {"ru", "en"}

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
        if rec.by_set_pos is not None:  # BYSETPOS (рабочий день/выходные) — старт уже верный
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
            if not rec or rec.frequency != "DAILY" or not d.exclusions:
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
                        fixed_h = raw_h + 12 if 1 <= raw_h <= 7 else raw_h
                        raw_m = getattr(time_tok, "_raw_minute", 0)
                        merge_time = datetime(2000, 1, 1, fixed_h, raw_m).time()
                    new_from = datetime.combine(target_date, merge_time)
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
                        is_past=date_tok.is_past,
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
            "и",
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
        while len(title_parts) >= 2 and title_parts[0][1].lower() in leading_preps:
            title_parts = title_parts[1:]
        if len(title_parts) >= 2:
            fti = title_parts[0][0]
            prev = tokens[fti - 1].value.lower() if fti > 0 else None
            if prev in ("с", "со", "у"):
                title_parts = title_parts[1:]
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

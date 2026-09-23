"""Распознавание времени"""

from datetime import timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords
from ..dict.morph_adapter import get_morph


class TimeRecognizer(Recognizer):
    MORNING_WORDS = {"утро", "утром", "утра"}
    DAY_WORDS = {"день", "днём", "днем", "дня"}
    EVENING_WORDS = {"вечер", "вечером", "вечера", "вечеру"}
    NIGHT_WORDS = {"ночь", "ночью", "ночи"}

    def __init__(self, config):
        super().__init__(config)
        self.morph = get_morph(getattr(config, "use_morph", None))

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_parse_time(tokens, i, now)
            if r:
                results.append(r)
                tu = 1
                for j in range(i, min(i + 5, len(tokens))):
                    if tokens[j].end >= r.end:
                        tu = j - i + 1
                        break
                i += max(1, tu)
            else:
                i += 1
        return results

    def _is_time_range_start(self, tokens, start):
        """«с/со N до/по <ЧИСЛО>» — начало числового диапазона времени.
        Такой случай обрабатывает RangeRecognizer; TimeRecognizer не должен
        выдавать одиночное время из первой половины (иначе битый диапазон
        «с 10 до 99» даёт ложные 22:00). Дедлайн «с 10 до пятницы» не трогаем."""
        if tokens[start].value.lower() not in ("с", "со"):
            return False
        for j in range(start + 1, min(start + 4, len(tokens))):
            if tokens[j].normalized in Keywords.TIME_TO:
                if j + 1 < len(tokens) and re.match(
                    r"^\d{1,2}(:\d{2})?$", tokens[j + 1].value
                ):
                    return True
                return False
        return False

    def _is_by_date(self, tokens, start):
        """«к/до <число|порядковое> <месяц>» — это дата-дедлайн (к 1 сентября),
        а не время. TimeRecognizer не должен брать число как час (иначе
        «к 1 сентября» → 01:00). Дату-дедлайн обработает DateRecognizer."""
        if tokens[start].normalized not in (Keywords.TIME_BY + Keywords.TIME_TO):
            return False
        if start + 2 >= len(tokens):
            return False
        mon_tok = tokens[start + 2]
        for mw in Keywords.months():
            if mon_tok.normalized in mw or mon_tok.value.lower() in mw:
                return True
        return False

    def _try_parse_time(self, tokens, start, now):
        if start >= len(tokens):
            return None
        if self._is_time_range_start(tokens, start):
            return None  # числовой диапазон — обработает RangeRecognizer
        if self._is_by_date(tokens, start):
            return None  # «к 1 сентября» — дата-дедлайн, обработает DateRecognizer
        tv = tokens[start].value.lower()
        tn = tokens[start].normalized
        # fuzzy time: около/примерно
        if tv in ["около", "примерно", "где-то"]:
            ni = start + 1
            if ni < len(tokens) and tokens[ni].normalized in Keywords.TIME_FROM:
                ni += 1
            if ni < len(tokens):
                h = (
                    int(tokens[ni].value)
                    if tokens[ni].value.isdigit()
                    else Keywords.parse_number_word(tokens[ni].value, self.morph)
                )
                if h is not None and 0 <= h <= 23:
                    ei = ni
                    pod = self._find_pod(tokens, ni + 1)
                    if pod:
                        ei = ni + 1
                    h = self._resolve_hour(h, pod)
                    dt = self._mk(now, h, 0)
                    return DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=dt,
                        date_to=dt,
                        has_time=True,
                        start=tokens[start].start,
                        end=tokens[ei].end,
                        fuzzy=True,
                        confidence=0.7,
                    )
            return None
        # ближе к вечеру
        if tv == "ближе" and start + 2 < len(tokens):
            if tokens[start + 1].normalized == "к":
                tod = tokens[start + 2].value.lower()
                if tod in self.EVENING_WORDS or tokens[start + 2].normalized in Keywords.EVENING:
                    s = now.replace(hour=17, minute=0, second=0, microsecond=0)
                    e = now.replace(hour=21, minute=0, second=0, microsecond=0)
                    if self.config.prefer_nearest_future and s < now:
                        s += timedelta(days=1)
                        e += timedelta(days=1)
                    # FIX: добавлен fuzzy=True чтобы "ближе к вечеру" стал TaskResult(FUZZY)
                    return DateTimeToken(
                        type=DateTimeType.PERIOD,
                        date_from=s,
                        date_to=e,
                        has_time=True,
                        fuzzy=True,
                        start=tokens[start].start,
                        end=tokens[start + 2].end,
                        confidence=0.7,
                    )

        # verbose: «в десять часов пятнадцать минут», «час пятнадцать»
        rv = self._try_verbose(tokens, start, now)
        if rv:
            return rv

        # Голое время HH:MM без предлога (например "встреча 15:00")
        mstd = re.fullmatch(r"(\d{1,2}):(\d{2})", tokens[start].value)
        if mstd:
            h, mi = int(mstd.group(1)), int(mstd.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                dt = self._mk(now, h, mi)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start].end,
                )

        ipv = tn in Keywords.TIME_FROM
        ipk = tn in Keywords.TIME_BY

        hp = ipv or ipk

        # до/после полуночи|полудня
        r = self._try_midnight_noon_prep(tokens, start, now)
        if r:
            return r

        # half hour (пол-)
        if tv in ["в", "к", "пол", "половина"] or tv.startswith("пол"):
            r = self._try_half(tokens, start, now)
            if r:
                return r
        # четверть
        if tv == "в" and start + 2 < len(tokens):
            r = self._try_quarter(tokens, start, now)
            if r:
                return r
        # без
        if tv == "без":
            r = self._try_without(tokens, start, now)
            if r:
                return r
        # к вечеру/утру/полудню
        if hp and start + 1 < len(tokens):
            sp = self._try_special(tokens, start + 1, now)
            if sp:
                sp.start = tokens[start].start
                return sp
        if ipk and start + 1 < len(tokens):
            nv = tokens[start + 1].value.lower()
            nn = tokens[start + 1].normalized
            if nn in Keywords.NOON or nn == "полудню":
                dt = self._mk(now, 12, 0)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + 1].end,
                )
            if nv in ["полночь", "полуночи"]:
                dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                tok = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + 1].end,
                )
                tok._midnight = True
                return tok
            if nv in ["утро", "утру", "утра"]:
                dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if dt < now:
                    dt += timedelta(days=1)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + 1].end,
                )
            if nv in self.EVENING_WORDS:
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=self._mk(now, 19, 0),
                    date_to=self._mk(now, 19, 0),
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + 1].end,
                )
            if nv in self.NIGHT_WORDS:
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=self._mk(now, 23, 0),
                    date_to=self._mk(now, 23, 0),
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + 1].end,
                )

        if not hp or start + 1 >= len(tokens):
            return None
        nt = tokens[start + 1]
        # HH:MM
        m = re.match(r"(\d{1,2})[:.-](\d{2})", nt.value)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                dt = self._mk(now, h, mi)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=nt.end,
                )
        # text hour
        h = self._parse_h(nt)
        if h is not None:
            mi, tah, hm = 0, 0, False
            if start + 2 < len(tokens):
                mr, mu = Keywords.parse_compound_minutes(tokens, start + 2, self.morph)
                if mr is not None and 0 <= mr <= 59:
                    mi = mr
                    tah = mu
                    hm = True
            eti = start + 1 + tah
            pod = self._find_pod(tokens, eti + 1)
            raw_h = h  # save raw hour before adjustment
            is_bare = pod is None and not hm and not ipk
            if pod is not None:
                # С уточнением (утра/вечера/дня/ночи) — уточнение побеждает
                h = self._resolve_hour(h, pod)
            elif is_bare:
                # Голое время без уточнения и без минут.
                if self.config.prefer_nearest_future:
                    h = self._resolve_hour_nearest(h, now)
                else:
                    # без nearest-future — фиксированный маппинг (1-7→+12), без флипа на завтра
                    h = self._resolve_hour(h, None)
            elif ipk and not hm:
                # FIX: "к 10" — предлог "к" с голым числом без минут → nearest-future
                h = self._resolve_hour_nearest(h, now)
            else:
                # Есть явные минуты без уточнения — фиксированный маппинг
                h = self._resolve_hour(h, None)
            fi = eti + (1 if pod else 0)
            fi = min(fi, len(tokens) - 1)
            dt = self._mk(now, h, mi)
            result = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=dt,
                date_to=dt,
                has_time=True,
                start=tokens[start].start,
                end=tokens[fi].end,
            )
            result._raw_hour = raw_h
            result._raw_minute = mi
            result._is_bare_time = is_bare
            # Явное уточнение (утра/дня/вечера/ночи) уже применено в _resolve_hour;
            # флаг запрещает parser._merge_date_and_time пересчитывать час заново.
            result._explicit_pod = pod is not None
            return result
        return None

    def _try_verbose(self, tokens, start, now):
        """«[в] N час(а/ов) [M минут]» → N:M; «час M [минут]» → 1:M.
        При явных минутах — фиксированный маппинг часа (без smart-flip)."""
        hp = tokens[start].value.lower() in ("в", "во")
        hi = start + 1 if hp else start
        if hi >= len(tokens):
            return None

        def _minutes_after(idx, require_word=True):
            mval, mc = Keywords.parse_cardinal(tokens, idx, self.morph)
            if mval is None or not (0 <= mval <= 59):
                return None, idx - 1
            munit = idx + mc
            if munit < len(tokens) and (
                tokens[munit].normalized in Keywords.MINUTE
                or tokens[munit].value.lower() in ("минут", "минуты", "минуту", "мин")
            ):
                return mval, munit
            if not require_word:
                return mval, idx + mc - 1
            return None, idx - 1

        # Case B: «час M [минут]» — «час» = 1 и одновременно единица
        # (минуты допускаются и без слова «минут»: «час пятнадцать» → 13:15)
        if tokens[hi].value.lower() in ("час", "часу"):
            mi, mend = _minutes_after(hi + 1, require_word=False)
            if mi is None:
                return None
            h = self._resolve_hour(1, None)
            dt = self._mk(now, h, mi)
            res = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=dt,
                date_to=dt,
                has_time=True,
                start=tokens[start].start,
                end=tokens[mend].end,
            )
            res._raw_hour = 1
            res._raw_minute = mi
            return res

        # Case A: «в N час(а/ов) [M минут]» — только с предлогом «в/во»,
        # чтобы не путать с длительностью «на N часов».
        if not hp:
            return None
        hval, hcons = Keywords.parse_cardinal(tokens, hi, self.morph)
        if hval is None or not (0 <= hval <= 23):
            return None
        uidx = hi + hcons
        if uidx >= len(tokens):
            return None
        uw = tokens[uidx].value.lower()
        un = tokens[uidx].normalized
        if not (un in Keywords.HOUR or uw in ("час", "часа", "часов")):
            return None
        mi, mend = _minutes_after(uidx + 1)
        if mi is None:
            mi = 0
            end = uidx
        else:
            end = mend
        h = self._resolve_hour(hval, None)
        dt = self._mk(now, h, mi)
        res = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=dt,
            date_to=dt,
            has_time=True,
            start=tokens[start].start,
            end=tokens[end].end,
        )
        res._raw_hour = hval
        res._raw_minute = mi
        return res

    def _resolve_hour(self, h, pod=None):
        """
        Фиксированный маппинг часов (для случаев с уточнением или привязкой к дате):
          8-12 → как есть
          1-7  → +12 (PM)
          0, 13-23 → как есть
        С уточнением (утра/дня/вечера/ночи) → уточнение побеждает.
        """
        if pod:
            return self._apply_pod(h, pod)
        if 1 <= h <= 7 and self.config.prefer_nearest_future:
            return h + 12
        return h

    def _resolve_hour_nearest(self, h, now):
        """
        Nearest-future для голого времени без уточнения и без даты.
        Для h=1-11: два кандидата (h и h+12), берём ближайший будущий.
        Для h=0 или h>=12: один кандидат, _mk обеспечит +1 день.
        """
        if h == 0 or h >= 12:
            return h
        c1 = h  # AM вариант
        c2 = h + 12  # PM вариант
        now_total = now.hour * 60 + now.minute
        # c1 ещё впереди сегодня?
        if c1 * 60 >= now_total:
            return c1
        # c2 ещё впереди сегодня?
        if c2 * 60 > now_total:
            return c2
        # оба прошли — вернуть c1, _mk добавит +1 день
        return c1

    def _apply_pod(self, h, pod):
        if pod == "morning":
            return h
        if pod == "day":
            return h + 12 if h < 12 else h
        if pod == "evening":
            return h + 12 if h <= 11 else h
        if pod == "night":
            return 0 if h == 12 else h
        return h

    def _parse_h(self, t):
        if t.normalized == "час":
            return self.config.default_hour_for_one
        if t.value.isdigit():
            h = int(t.value)
            return h if 0 <= h <= 23 else None
        h = Keywords.parse_number_word(t.value, self.morph)
        return h if h is not None and 0 <= h <= 23 else None

    def _find_pod(self, tokens, start):
        if start >= len(tokens):
            return None
        v = tokens[start].value.lower()
        if v in self.MORNING_WORDS:
            return "morning"
        if v in self.EVENING_WORDS:
            return "evening"
        if v in self.NIGHT_WORDS:
            return "night"
        if v in self.DAY_WORDS:
            return "day"
        return None

    def _mk(self, base, h, m, pf=True):
        dt = base.replace(hour=h, minute=m, second=0, microsecond=0)
        if pf and self.config.prefer_nearest_future and dt < base:
            dt += timedelta(days=1)
        return dt

    def _try_midnight_noon_prep(self, tokens, start, now):
        """до полуночи / после полуночи / до полудня."""
        tn = tokens[start].normalized
        tv = tokens[start].value.lower()
        if start + 1 >= len(tokens):
            return None
        nv = tokens[start + 1].value.lower()
        nn = tokens[start + 1].normalized
        is_midnight = nv in ["полночь", "полуночи"] or nn in ["полночь"]
        is_noon = nv in ["полдень", "полудню", "полудня"] or nn in ["полдень"]
        if not (is_midnight or is_noon):
            return None
        if is_midnight:
            target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            target = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if target < now:
                target += timedelta(days=1)
        end_i = start + 1
        if tn in Keywords.TIME_TO:  # «до полуночи/полудня» → дедлайн
            return DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=target,
                has_time=True,
                is_deadline=True,
                start=tokens[start].start,
                end=tokens[end_i].end,
                confidence=0.9,
            )
        if tv in Keywords.AFTER_PREP:  # «после полуночи» → open-start
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=target,
                date_to=target,
                has_time=True,
                start=tokens[start].start,
                end=tokens[end_i].end,
                confidence=0.85,
            )
            dt._open_start = True
            return dt
        return None

    def _try_half(self, tokens, start, now):
        off = 0
        if start < len(tokens) and (
            tokens[start].normalized in Keywords.TIME_FROM
            or tokens[start].normalized in Keywords.TIME_BY
        ):
            off = 1
        if start + off >= len(tokens):
            return None
        tv = tokens[start + off].value.lower()
        if tv.startswith("пол") and len(tv) > 3:
            wm = {
                "первого": 0,
                "второго": 1,
                "третьего": 2,
                "четвёртого": 3,
                "четвертого": 3,
                "пятого": 4,
                "шестого": 5,
                "седьмого": 6,
                "восьмого": 7,
                "девятого": 8,
                "десятого": 9,
                "одиннадцатого": 10,
                "двенадцатого": 11,
            }
            h = None
            m = re.search(r"(\d+)$", tv)
            if m:
                hv = int(m.group(1))
                if 1 <= hv <= 12:
                    h = hv - 1
            if h is None:
                for s, v in wm.items():
                    if s in tv:
                        h = v
                        break
            if h is not None:
                h = self._resolve_hour(h, None)
                dt = self._mk(now, h, 30)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + off].end,
                )
        if tokens[start + off].normalized in ["пол", "половина", "половине", "половину"]:
            if start + off + 1 >= len(tokens):
                return None
            nt = tokens[start + off + 1]
            hv = (
                int(nt.value)
                if nt.value.isdigit()
                else Keywords.parse_number_word(nt.value, self.morph)
            )
            if hv and 1 <= hv <= 12:
                h = self._resolve_hour(hv - 1, None)
                dt = self._mk(now, h, 30)
                return DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=dt,
                    date_to=dt,
                    has_time=True,
                    start=tokens[start].start,
                    end=tokens[start + off + 1].end,
                )
        return None

    def _try_quarter(self, tokens, s, now):
        if s + 2 >= len(tokens):
            return None
        if tokens[s].normalized not in Keywords.TIME_FROM:
            return None
        if tokens[s + 1].value.lower() not in ["четверть", "четверти"]:
            return None
        hm = {
            "первого": 0,
            "второго": 1,
            "третьего": 2,
            "четвёртого": 3,
            "четвертого": 3,
            "пятого": 4,
            "шестого": 5,
            "седьмого": 6,
            "восьмого": 7,
            "девятого": 8,
            "десятого": 9,
            "одиннадцатого": 10,
            "двенадцатого": 11,
        }
        h = hm.get(tokens[s + 2].value.lower())
        if h is None:
            return None
        h = self._resolve_hour(h, None)
        dt = self._mk(now, h, 15)
        return DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=dt,
            date_to=dt,
            has_time=True,
            start=tokens[s].start,
            end=tokens[s + 2].end,
        )

    def _try_without(self, tokens, s, now):
        if s >= len(tokens) or tokens[s].value.lower() != "без":
            return None
        if s + 2 >= len(tokens):
            return None
        mv = tokens[s + 1].value.lower()
        if mv in ["четверть", "четверти"]:
            mins = 15
        else:
            mins = Keywords._cardinal_value(mv, self.morph)
        if mins is None or not (1 <= mins <= 59):
            return None
        h = Keywords._cardinal_value(tokens[s + 2].value, self.morph)
        if h is None or not (1 <= h <= 12):
            return None
        h = self._resolve_hour(h, None)
        dt = now.replace(hour=h, minute=0, second=0, microsecond=0) - timedelta(minutes=mins)
        if self.config.prefer_nearest_future and dt < now:
            dt += timedelta(days=1)
        return DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=dt,
            date_to=dt,
            has_time=True,
            start=tokens[s].start,
            end=tokens[s + 2].end,
        )

    def _try_special(self, tokens, s, now):
        if s >= len(tokens):
            return None
        v = tokens[s].value.lower()
        if tokens[s].normalized == "полночь" or v == "полночь":
            h = 0
        elif tokens[s].normalized == "полдень" or v == "полдень":
            h = 12
        elif v in ("обед", "обеда", "обеду"):
            h = 13
        else:
            return None
        dt = self._mk(now, h, 0)
        tok = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=dt,
            date_to=dt,
            has_time=True,
            start=tokens[s].start,
            end=tokens[s].end,
        )
        if h == 0:
            tok._midnight = True
        return tok

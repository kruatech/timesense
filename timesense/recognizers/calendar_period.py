"""Календарные периоды без конкретного дня.

«в октябре», «в декабре 2026», «в 2027 году», «в следующем месяце»,
«в этом году», «в начале следующего месяца», «в конце этого года»,
«в середине следующей недели», «на следующих выходных», «в эти выходные».

Результат — нечёткий период (fuzzy, all-day): задача «когда-то в этот период».
Ближайшее будущее: «в марте» в сентябре → март следующего года.
"""

from calendar import monthrange
from datetime import datetime, timedelta

from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords

_WEEKEND = ("выходные", "выходных", "выходным", "выходными")
_MOD_OFFSET = (
    (Keywords.NEXT, 1),
    (Keywords.PREVIOUS2_MOD, -2),
    (Keywords.PREVIOUS_MOD, -1),
    (Keywords.CURRENT, 0),
    (Keywords.CURRENT_NEXT, 0),
)
_EXTRA_MODS = {
    # родительный падеж («в начале прошлого месяца») и множественное число (выходные)
    "следующего": 1, "будущего": 1, "прошлого": -1, "прошедшего": -1, "этого": 0,
    "текущего": 0, "позапрошлого": -2, "ближайшего": 0,
    "следующие": 1, "следующих": 1, "будущие": 1, "будущих": 1,
    "прошлые": -1, "прошлых": -1, "прошедшие": -1, "прошедших": -1,
    "эти": 0, "этих": 0, "ближайшие": 0, "ближайших": 0, "текущие": 0,
}
# окно части периода, дней (как в EN-локали: неделя 1, месяц 4, год 9)
_PART_PAD = {"week": 1, "month": 4, "quarter": 9, "year": 9}
# «в первую/вторую/последнюю неделю <месяца>»: 1–7, 8–14, 15–21, 22–28, последние 7 дней
_WEEK_ORD = {
    "первую": 1, "первой": 1, "вторую": 2, "второй": 2, "третью": 3, "третьей": 3,
    "четвёртую": 4, "четвертую": 4, "четвёртой": 4, "четвертой": 4,
    "последнюю": -1, "последней": -1,
}
# «в первом квартале» (после нормализации «в 1 квартале», «в IV квартале», «в 2-м квартале»)
_QUARTER_ORD = {"первом": 1, "втором": 2, "третьем": 3, "четвёртом": 4, "четвертом": 4}


class CalendarPeriodRecognizer(Recognizer):
    def _mod(self, tok):
        v, n = tok.value.lower(), tok.normalized
        if v in _EXTRA_MODS:
            return _EXTRA_MODS[v]
        for lst, off in _MOD_OFFSET:
            if v in lst or n in lst:
                return off
        return None

    @staticmethod
    def _month_of(tok):
        v, n = tok.value.lower(), tok.normalized
        for idx, forms in enumerate(Keywords.months()):
            if v in forms or n in forms:
                return idx + 1
        return None

    @staticmethod
    def _unit_of(tok):
        v, n = tok.value.lower(), tok.normalized
        if v in Keywords.WEEK or n in Keywords.WEEK:
            return "week"
        if v in Keywords.MONTH or n in Keywords.MONTH:
            return "month"
        if v in Keywords.YEAR or n in Keywords.YEAR:
            return "year"
        if v.startswith("квартал"):
            return "quarter"
        return None

    @staticmethod
    def _bounds(unit, ref):
        if unit == "week":
            mon = (ref - timedelta(days=ref.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return mon, (mon + timedelta(days=6)).replace(hour=23, minute=59)
        if unit == "quarter":
            q0 = (ref.month - 1) // 3 * 3 + 1
            last = monthrange(ref.year, q0 + 2)[1]
            return datetime(ref.year, q0, 1), datetime(ref.year, q0 + 2, last, 23, 59)
        if unit == "month":
            last = monthrange(ref.year, ref.month)[1]
            return datetime(ref.year, ref.month, 1), datetime(ref.year, ref.month, last, 23, 59)
        return datetime(ref.year, 1, 1), datetime(ref.year, 12, 31, 23, 59)

    @staticmethod
    def _shift(unit, now, off):
        if unit == "week":
            return now + timedelta(weeks=off)
        if unit in ("month", "quarter"):
            m = now.month - 1 + off * (3 if unit == "quarter" else 1)
            y = now.year + m // 12
            return now.replace(year=y, month=m % 12 + 1, day=1)
        return now.replace(year=now.year + off, month=1, day=1)

    @staticmethod
    def _part(unit, part, s, e):
        pad = _PART_PAD[unit]
        if part == "start":
            return s, (s + timedelta(days=pad)).replace(hour=23, minute=59)
        if part == "end":
            return (e - timedelta(days=pad)).replace(hour=0, minute=0), e
        mid = s + (e - s) / 2
        half = pad // 2 + 1  # как в PeriodRecognizer и EN-локали
        return (
            (mid - timedelta(days=half)).replace(hour=0, minute=0, second=0, microsecond=0),
            (mid + timedelta(days=half)).replace(hour=23, minute=59, second=0, microsecond=0),
        )

    @staticmethod
    def _part_of(tok):
        v, n = tok.value.lower(), tok.normalized
        if v in Keywords.START_OF or n in Keywords.START_OF:
            return "start"
        if v in Keywords.MIDDLE_OF or n in Keywords.MIDDLE_OF:
            return "middle"
        if v in Keywords.END_OF or n in Keywords.END_OF:
            return "end"
        return None

    def _mk(self, s, e, tokens, si, ei, now):
        return DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=False,
            all_day=True,
            fuzzy=True,
            start=tokens[si].start,
            end=tokens[ei].end,
            confidence=0.9,
            is_past=e < now,
        )

    def _year_after(self, tokens, j):
        """YYYY [года|году|г] сразу после позиции j → (year, index_last) | None."""
        if j < len(tokens) and tokens[j].value.isdigit() and len(tokens[j].value) == 4:
            y = int(tokens[j].value)
            last = j
            if j + 1 < len(tokens) and tokens[j + 1].value.lower() in ("года", "году", "год", "г"):
                last = j + 1
            return y, last
        return None

    def _try(self, tokens, i, now):
        t = tokens[i].value.lower()
        if t not in ("в", "во", "на"):
            return None
        if i + 1 >= len(tokens):
            return None
        a = tokens[i + 1]

        # «в первую/вторую/последнюю неделю октября», «на второй неделе октября»
        wn = _WEEK_ORD.get(a.value.lower())
        if (wn is not None and i + 3 < len(tokens)
                and tokens[i + 2].value.lower() in ("неделю", "неделе", "недели")):
            mon = self._month_of(tokens[i + 3])
            if mon is not None:
                ya = self._year_after(tokens, i + 4)
                year, ei = (ya if ya is not None else (now.year, i + 3))
                last = monthrange(year, mon)[1]
                if ya is None and self.config.prefer_nearest_future and \
                        datetime(year, mon, last, 23, 59) < now:
                    year += 1
                    last = monthrange(year, mon)[1]
                if wn == -1:
                    s, e = datetime(year, mon, last - 6), datetime(year, mon, last, 23, 59)
                else:
                    s = datetime(year, mon, (wn - 1) * 7 + 1)
                    e = datetime(year, mon, min(wn * 7, last), 23, 59)
                tok = self._mk(s, e, tokens, i, ei, now)
                tok.fuzzy = False
                tok.confidence = 0.97
                tok.is_explicit_range = True  # явно названная неделя месяца
                return tok, ei

        # в <месяц> [YYYY]
        if t in ("в", "во"):
            mon = self._month_of(a)
            if mon is not None:
                ya = self._year_after(tokens, i + 2)
                if ya is not None:
                    year, ei = ya
                else:
                    year, ei = now.year, i + 1
                    if mon < now.month and self.config.prefer_nearest_future:
                        year += 1
                last = monthrange(year, mon)[1]
                return self._mk(
                    datetime(year, mon, 1), datetime(year, mon, last, 23, 59), tokens, i, ei, now
                ), ei

            # в YYYY году
            if a.value.isdigit() and len(a.value) == 4 and i + 2 < len(tokens):
                if tokens[i + 2].value.lower() in ("году", "г"):
                    y = int(a.value)
                    return self._mk(
                        datetime(y, 1, 1), datetime(y, 12, 31, 23, 59), tokens, i, i + 2, now
                    ), i + 2

            # в начале/середине/конце <мод> <недели|месяца|года>
            part = self._part_of(a)
            if part is not None and i + 3 < len(tokens):
                off = self._mod(tokens[i + 2])
                unit = self._unit_of(tokens[i + 3])
                if off is not None and unit is not None:
                    ref = self._shift(unit, now, off)
                    s, e = self._part(unit, part, *self._bounds(unit, ref))
                    return self._mk(s, e, tokens, i, i + 3, now), i + 3

            # в <N-м> квартале [YYYY]  («в первом квартале», «во втором квартале 2027»)
            qn = _QUARTER_ORD.get(a.value.lower())
            if qn is not None and i + 2 < len(tokens) and tokens[i + 2].value.lower().startswith("квартал"):
                ya = self._year_after(tokens, i + 3)
                if ya is not None:
                    year, ei = ya
                else:
                    year, ei = now.year, i + 2
                    q_end = datetime(year, qn * 3, monthrange(year, qn * 3)[1], 23, 59)
                    if q_end < now and self.config.prefer_nearest_future:
                        year += 1
                s = datetime(year, qn * 3 - 2, 1)
                e = datetime(year, qn * 3, monthrange(year, qn * 3)[1], 23, 59)
                return self._mk(s, e, tokens, i, ei, now), ei

            # в <мод> <месяце|году>  («в следующем месяце», «в этом году»)
            if i + 2 < len(tokens):
                off = self._mod(a)
                unit = self._unit_of(tokens[i + 2])
                # «в следующем месяце 5 числа» — конкретный день, его разбирает другой
                # распознаватель; период месяца здесь не выдаём
                nxt = [t.value.lower() for t in tokens[i + 3:i + 5]]
                has_day = any(x.isdigit() or x in ("числа", "число") for x in nxt) or any(
                    Keywords.parse_ordinal_day(x) is not None for x in nxt[:1]
                )
                if off is not None and unit in ("month", "year", "quarter") and not has_day:
                    ref = self._shift(unit, now, off)
                    s, e = self._bounds(unit, ref)
                    return self._mk(s, e, tokens, i, i + 2, now), i + 2

        # на/в <мод> выходных
        if i + 2 < len(tokens) and tokens[i + 2].value.lower() in _WEEKEND:
            off = self._mod(a)
            if off is not None:
                wd = now.weekday()
                sat = (now + timedelta(days=(5 - wd) % 7 if wd <= 5 else -1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                sat += timedelta(weeks=off)
                sun = (sat + timedelta(days=1)).replace(hour=23, minute=59)
                tok = self._mk(sat, sun, tokens, i, i + 2, now)
                tok.fuzzy = False  # выходные — конкретные дни, а не «примерно»
                return tok, i + 2
        return None

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try(tokens, i, now)
            if r is not None:
                results.append(r[0])
                i = r[1] + 1
            else:
                i += 1
        return results

"""Распознавание сезонов и кварталов"""

from datetime import datetime, timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class SeasonRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_season(tokens, i, now) or self._try_quarter(tokens, i, now)
            if r:
                tok = r[0]
                prev = tokens[i - 1].value.lower() if i > 0 else ""
                if prev in ("прошлой", "прошлым", "прошлого", "прошлую", "прошедшей", "прошедшим"):
                    # «прошлой зимой» — сезон годом раньше ближайшего (текущего или будущего)
                    tok.date_from = tok.date_from.replace(year=tok.date_from.year - 1)
                    last_day = tok.date_to.day
                    if tok.date_to.month == 2:
                        from calendar import monthrange as _mr

                        last_day = _mr(tok.date_to.year - 1, 2)[1]
                    tok.date_to = tok.date_to.replace(year=tok.date_to.year - 1, day=last_day)
                    tok.is_past = tok.date_to < now
                    tok.start = tokens[i - 1].start
                elif prev in ("следующей", "следующим", "будущей", "будущим") and tok.date_from <= now:
                    # «следующей зимой» во время зимы — следующая, а не текущая
                    tok.date_from = tok.date_from.replace(year=tok.date_from.year + 1)
                    tok.date_to = tok.date_to.replace(year=tok.date_to.year + 1)
                    tok.start = tokens[i - 1].start
                elif prev in ("этой", "этим", "этого", "следующей", "следующим", "будущей", "будущим"):
                    tok.start = tokens[i - 1].start
                results.append(tok)
                i += r[1]
            else:
                i += 1
        return results

    def _try_season(self, tokens, i, now):
        v = tokens[i].value.lower()
        n = tokens[i].normalized
        y = now.year
        season = None
        if v in Keywords.SPRING or n in ["весна"]:
            season = (3, 1, 5, 31)
        elif v in Keywords.SUMMER or n in ["лето"]:
            season = (6, 1, 8, 31)
        elif v in Keywords.AUTUMN or n in ["осень"]:
            season = (9, 1, 11, 30)
        elif v in Keywords.WINTER or n in ["зима"]:
            season = (12, 1, 2, 28)  # зима пересекает год
        if season is None:
            return None
        sm, sd, em, ed = season
        winter = sm == 12
        if winter and now.month <= 2:
            y -= 1  # в январе–феврале «зимой» — текущая зима (началась в декабре)
        ey = y + 1 if winter else y
        if winter:
            from calendar import monthrange as _mr

            ed = _mr(ey, 2)[1]  # 29 февраля в високосный год
        if self.config.prefer_nearest_future and datetime(ey, em, ed, 23, 59) < now:
            # сезон уже прошёл в этом году → ближайший будущий (паритет с EN)
            y, ey = y + 1, ey + 1
            if winter:
                from calendar import monthrange as _mr

                ed = _mr(ey, 2)[1]
        # модификатор начало/конец/середина перед сезоном (+ опциональный предлог)
        part = None
        start_i = i
        if i > 0:
            pv = tokens[i - 1].value.lower()
            pn = tokens[i - 1].normalized
            if pv in Keywords.START_OF or pn in Keywords.START_OF:
                part = "start"
            elif pv in Keywords.END_OF or pn in Keywords.END_OF:
                part = "end"
            elif pv in Keywords.MIDDLE_OF or pn in Keywords.MIDDLE_OF:
                part = "middle"
            if part is not None:
                start_i = i - 1
                if i - 2 >= 0 and tokens[i - 2].value.lower() in ("в", "во"):
                    start_i = i - 2
        if part is None:
            return (self._mk_period(y, sm, sd, ey, em, ed, tokens[i], 0.7), 1)
        s_full = datetime(y, sm, sd, 0, 0, 0)
        e_full = datetime(ey, em, ed, 23, 59, 0)
        if part == "start":
            s, e = s_full, s_full + timedelta(days=9)
        elif part == "end":
            s, e = e_full - timedelta(days=9), e_full
        else:
            mid = s_full + (e_full - s_full) / 2
            s = (mid - timedelta(days=5)).replace(hour=0, minute=0, second=0, microsecond=0)
            e = (mid + timedelta(days=5)).replace(hour=23, minute=59, second=0, microsecond=0)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=False,
            all_day=True,
            fuzzy=True,
            start=tokens[start_i].start,
            end=tokens[i].end,
            confidence=0.7,
        )
        return (dt, 1)

    def _try_quarter(self, tokens, i, now):
        if i + 1 >= len(tokens):
            return None
        t = tokens[i]
        nt = tokens[i + 1]
        num = None
        if t.value.isdigit():
            num = int(t.value)
        elif nt.value.isdigit():
            num = int(nt.value)
        if num is None or not (1 <= num <= 4):
            return None
        qw = (
            t.normalized in Keywords.QUARTER
            or t.value.lower() in Keywords.QUARTER
            or nt.normalized in Keywords.QUARTER
            or nt.value.lower() in Keywords.QUARTER
        )
        if not qw:
            return None
        y = now.year
        starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
        ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        sm, sd = starts[num]
        em, ed = ends[num]
        if self.config.prefer_nearest_future and datetime(y, em, ed, 23, 59) < now:
            y += 1  # квартал уже прошёл → в следующем году
        return (self._mk_period(y, sm, sd, y, em, ed, t, 0.85, tokens[i + 1].end), 2)

    def _mk_period(self, y1, m1, d1, y2, m2, d2, t, conf, end_pos=None):
        s = datetime(y1, m1, d1, 0, 0, 0)
        e = datetime(y2, m2, d2, 23, 59, 0)
        return DateTimeToken(
            type=DateTimeType.PERIOD,
            date_from=s,
            date_to=e,
            has_time=False,
            all_day=True,
            fuzzy=True,
            start=t.start,
            end=end_pos or t.end,
            confidence=conf,
        )

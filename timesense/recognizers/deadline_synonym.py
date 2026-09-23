"""не позднее пятницы, крайний срок - пятница"""

from datetime import datetime, timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class DeadlineSynonymRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_no_later(tokens, i, now)
                or self._try_term(tokens, i, now)
                or self._try_during(tokens, i, now)
                or self._try_until_time(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    # «до полудня / до обеда / до вечера» → час дедлайна
    _UNTIL_WORDS = {
        "полудня": 12, "полдня": 12, "обеда": 13, "вечера": 18,
    }
    _UNTIL_STOP = None

    def _until_stop(self):
        if self._UNTIL_STOP is None:
            stop = set()
            for lst in (
                Keywords.SECOND, Keywords.MINUTE, Keywords.HOUR, Keywords.DAY,
                Keywords.WEEK, Keywords.MONTH, Keywords.YEAR,
            ):
                stop.update(lst)
            for mw in Keywords.months():
                stop.update(mw)
            stop.update({"число", "числа", "раз", "раза", "человек", "штук", "лет", "градусов"})
            stop.discard("часов")
            stop.discard("ч")
            type(self)._UNTIL_STOP = stop
        return self._UNTIL_STOP

    def _try_until_time(self, tokens, i, now):
        """до 18 / до 18:00 / до 6 вечера / до полудня / до обеда → дедлайн по времени.

        Не срабатывает на «до 20 марта», «до 5 минут», «до 18 лет», «до 20-го»
        (обрабатываются другими распознавателями или не являются временем).
        Диапазон «с 10 до 18» выигрывает в дедупликации (explicit range).
        """
        if i + 1 < len(tokens) and tokens[i].value.lower() == "перед":
            # «перед обедом» ≈ до обеда
            if tokens[i + 1].value.lower() in ("обедом",):
                hour = 13
                target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if target <= now and self.config.prefer_nearest_future:
                    target += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.FIXED, date_from=now, date_to=target, has_time=True,
                    is_deadline=True, start=tokens[i].start, end=tokens[i + 1].end,
                    confidence=1.0,
                )
                return (dt, 2)
            return None
        if tokens[i].value.lower() != "до" or i + 1 >= len(tokens):
            return None
        t = tokens[i + 1]
        v = t.value.lower()
        ei = i + 1
        minute = 0
        explicit = False
        if v in self._UNTIL_WORDS:
            hour = self._UNTIL_WORDS[v]
            explicit = True
        else:
            m = re.match(r"^(\d{1,2})[:.](\d{2})$", v)
            if m:
                hour, minute = int(m.group(1)), int(m.group(2))
                explicit = True
            elif v.isdigit():
                hour = int(v)
            else:
                return None
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            if ei + 1 < len(tokens):
                nv = tokens[ei + 1].value.lower()
                if nv in self._until_stop():
                    return None
                if nv in ("часов", "ч"):
                    ei += 1
                    if ei + 1 < len(tokens):
                        nv = tokens[ei + 1].value.lower()
                # «до 6 вечера / утра» — явная часть суток
                if nv in ("вечера", "дня"):
                    if hour < 12:
                        hour += 12
                    explicit = True
                    ei += 1
                elif nv in ("утра", "ночи"):
                    if hour == 12:
                        hour = 0
                    explicit = True
                    ei += 1
            if not explicit and 1 <= hour <= 7 and self.config.prefer_nearest_future:
                hour += 12  # «до 6» днём — это 18:00 (как и в остальном парсере)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now and self.config.prefer_nearest_future:
            target += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=1.0,
        )
        dt._deadline_time = (hour, minute)
        return (dt, ei - i + 1)

    def _try_during(self, tokens, i, now):
        """в течение часа / в течение 2 дней — дедлайн = now + Δ"""
        if tokens[i].value.lower() not in Keywords.DURING:
            return None
        start_i = i
        if i > 0 and tokens[i - 1].value.lower() == "в":
            start_i = i - 1
        j = i + 1
        if j >= len(tokens):
            return None
        num = 1
        explicit_num = tokens[j].value.isdigit() or (
            Keywords.parse_number_word(tokens[j].value, self.morph) is not None
        )
        if tokens[j].value.isdigit():
            num = int(tokens[j].value)
            j += 1
        elif Keywords.parse_number_word(tokens[j].value, self.morph) is not None:
            num = Keywords.parse_number_word(tokens[j].value, self.morph)
            j += 1
        if j >= len(tokens):
            return None
        uv = tokens[j].value.lower()
        un = tokens[j].normalized
        if un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
            delta = timedelta(minutes=num)
        elif un in Keywords.HOUR or uv in ["час", "часа", "часов", "часу"]:
            delta = timedelta(hours=num)
        elif un in Keywords.DAY or uv in ["день", "дня", "дней"]:
            delta = timedelta(days=num)
        elif un in Keywords.WEEK or uv in ["неделю", "недели", "недель", "неделя"]:
            delta = timedelta(weeks=num)
        else:
            return None
        target = now + delta
        # «в течение дня / недели» без числа — до конца текущего дня / недели
        if not explicit_num and delta == timedelta(days=1):
            target = now.replace(hour=23, minute=59, second=0, microsecond=0)
        elif not explicit_num and delta == timedelta(weeks=1):
            target = (now + timedelta(days=6 - now.weekday())).replace(
                hour=23, minute=59, second=0, microsecond=0
            )
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[start_i].start,
            end=tokens[j].end,
            confidence=0.85,
        )
        return (dt, j - i + 1)

    def _try_no_later(self, tokens, i, now):
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in Keywords.NOT_WORD:
            return None
        if tokens[i + 1].value.lower() not in Keywords.DEADLINE_NO_LATER:
            return None
        target, ei = self._find_date(tokens, i + 2, now)
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.9,
        )
        return (dt, ei - i + 1)

    def _try_term(self, tokens, i, now):
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in Keywords.DEADLINE_LATEST:
            return None
        if tokens[i + 1].value.lower() not in Keywords.DEADLINE_TERM:
            return None
        ni = i + 2
        if ni < len(tokens) and tokens[ni].value in ["-", "\u2014", "\u2013"]:
            ni += 1
        if ni >= len(tokens):
            return None
        target, ei = self._find_date(tokens, ni, now)
        if target is None:
            return None
        dt = DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=now,
            date_to=target,
            has_time=True,
            is_deadline=True,
            start=tokens[i].start,
            end=tokens[ei].end,
            confidence=0.9,
        )
        return (dt, ei - i + 1)

    def _find_date(self, tokens, start, now):
        if start >= len(tokens):
            return (None, start)
        t = tokens[start]
        for wi, days in enumerate(Keywords.days_of_week()):
            if t.normalized in days or t.value.lower() in days:
                da = (wi - now.weekday()) % 7
                if da <= 0:
                    da += 7
                target = (now + timedelta(days=da)).replace(
                    hour=23, minute=59, second=0, microsecond=0
                )
                return (target, start)
        if t.normalized in Keywords.TOMORROW:
            return (
                (now + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0),
                start,
            )
        m = re.match(r"^(\d+)-?(?:го)?$", t.value)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                month = now.month
                year = now.year
                target = datetime(year, month, day, 23, 59, 0)
                if target < now:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                    target = datetime(year, month, day, 23, 59, 0)
                return (target, start)
        return (None, start)

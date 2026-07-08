"""Распознавание относительных дат: через 2 часа, 5 дней назад, через неделю, через полгода"""

from datetime import timedelta
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class RelativeRecognizer(Recognizer):
    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = (
                self._try_offset_word(tokens, i, now)
                or self._try_forward_compound(tokens, i, now)
                or self._try_forward_no_number(tokens, i, now)
                or self._try_forward(tokens, i, now)
                or self._try_backward(tokens, i, now)
                or self._try_backward_no_number(tokens, i, now)
            )
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_offset_word(self, tokens, i, now):
        """Слова из config.relative_offsets: 'потом'->'+20', 'позже'->'+2h'."""
        offsets = getattr(self.config, "relative_offsets", None) or {}
        if not offsets:
            return None
        t = tokens[i]
        spec = offsets.get(t.value.lower())
        if spec is None:
            spec = offsets.get(t.normalized)
        if spec is None:
            return None
        minutes = self._parse_offset(spec)
        if minutes is None:
            return None
        target = now + timedelta(minutes=minutes)
        is_past = minutes < 0
        dt = DateTimeToken(
            type=(DateTimeType.SPAN_BACKWARD if is_past else DateTimeType.SPAN_FORWARD),
            date_from=target,
            date_to=target,
            has_time=True,
            start=t.start,
            end=t.end,
            confidence=0.7,
            is_past=is_past,
        )
        return (dt, 1)

    @staticmethod
    def _parse_offset(spec):
        """'+20'/'20'/-10 -> минуты; '+2h'/'2ч' -> часы (в минутах). Принимает int."""
        if isinstance(spec, (int, float)):
            return int(spec)
        if not isinstance(spec, str):
            return None
        import re as _re

        m = _re.match(r"^\s*([+-]?\d+)\s*([a-zа-я]*)\s*$", spec.strip().lower())
        if not m:
            return None
        value = int(m.group(1))
        unit = m.group(2)
        if unit in ("", "m", "min", "мин", "минут", "минуты", "минуту"):
            return value
        if unit in ("h", "ч", "час", "часа", "часов"):
            return value * 60
        return value

    def _try_forward_compound(self, tokens, i, now):
        """через 2 часа 30 минут — составной офсет (часы + минуты)"""
        if tokens[i].value.lower() not in Keywords.AFTER:
            return None
        if i + 4 >= len(tokens):
            return None
        nt = tokens[i + 1]
        num1 = (
            int(nt.value)
            if nt.value.isdigit()
            else Keywords.parse_number_word(nt.value, self.morph)
        )
        if num1 is None:
            return None
        ut1 = tokens[i + 2]
        uv1 = ut1.value.lower()
        un1 = ut1.normalized
        # Первая единица должна быть часами
        if un1 not in Keywords.HOUR and uv1 not in ["час", "часа", "часов"]:
            return None
        # Ищем вторую часть: N минут
        nt2 = tokens[i + 3]
        num2 = (
            int(nt2.value)
            if nt2.value.isdigit()
            else Keywords.parse_number_word(nt2.value, self.morph)
        )
        if num2 is None:
            return None
        if i + 4 >= len(tokens):
            return None
        ut2 = tokens[i + 4]
        uv2 = ut2.value.lower()
        un2 = ut2.normalized
        if un2 not in Keywords.MINUTE and uv2 not in ["минут", "минуты", "минуту", "мин"]:
            return None
        delta = timedelta(hours=num1, minutes=num2)
        target = now + delta
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=True,
            start=tokens[i].start,
            end=ut2.end,
            confidence=0.95,
        )
        return (dt, 5)

    def _try_forward_no_number(self, tokens, i, now):
        """через неделю, через месяц, через полгода, через квартал, через год"""
        if tokens[i].value.lower() not in Keywords.AFTER:
            return None
        if i + 1 >= len(tokens):
            return None
        nt = tokens[i + 1]
        nv = nt.value.lower()
        nn = nt.normalized
        delta = None
        target = None
        # через полчаса
        if nv in ("полчаса", "пол-часа"):
            dt = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=now + timedelta(minutes=30),
                date_to=now + timedelta(minutes=30),
                has_time=True,
                start=tokens[i].start,
                end=nt.end,
                confidence=0.9,
            )
            return (dt, 2)
        # через полтора часа
        if nv == "полтора" and i + 2 < len(tokens):
            ut2 = tokens[i + 2]
            uv2 = ut2.value.lower()
            un2 = ut2.normalized
            if un2 in Keywords.HOUR or uv2 in ["час", "часа", "часов"]:
                tgt = now + timedelta(minutes=90)
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=tgt,
                    date_to=tgt,
                    has_time=True,
                    start=tokens[i].start,
                    end=ut2.end,
                    confidence=0.9,
                )
                return (dt, 3)
        # через день / через сутки
        if nn in Keywords.DAY or nv in ["день", "дня", "дней"]:
            delta = timedelta(days=1)
        # через час / через минуту (без числа)
        elif nn in Keywords.HOUR or nv in ["час", "часок"]:
            dt = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=now + timedelta(hours=1),
                date_to=now + timedelta(hours=1),
                has_time=True,
                start=tokens[i].start,
                end=nt.end,
                confidence=0.9,
            )
            return (dt, 2)
        elif nn in Keywords.MINUTE or nv in ["минуту", "минутку"]:
            dt = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=now + timedelta(minutes=1),
                date_to=now + timedelta(minutes=1),
                has_time=True,
                start=tokens[i].start,
                end=nt.end,
                confidence=0.9,
            )
            return (dt, 2)
        # через неделю
        elif nn in Keywords.WEEK or nv in ["неделю", "недели", "недель", "неделя"]:
            delta = timedelta(weeks=1)
        # через месяц
        elif nn in Keywords.MONTH or nv in ["месяц", "месяца", "месяцев"]:
            target = self._add_months(now, 1)
        # через год
        elif nn in Keywords.YEAR or nv in ["год", "года", "лет"]:
            target = self._add_months(now, 12)
        # через полгода
        elif nv in Keywords.HALF_YEAR or nv in ["полгода", "полугодие", "полугодия"]:
            target = self._add_months(now, 6)
        # через квартал
        elif nn in Keywords.QUARTER or nv in ["квартал", "квартала"]:
            target = self._add_months(now, 3)
        # через полтора + единица
        elif nv == "полтора" and i + 2 < len(tokens):
            ut = tokens[i + 2]
            uv = ut.value.lower()
            un = ut.normalized
            if un in Keywords.YEAR or uv in ["год", "года", "лет"]:
                target = self._add_months(now, 18)
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=False,
                    start=tokens[i].start,
                    end=ut.end,
                    confidence=0.9,
                )
                return (dt, 3)
            elif un in Keywords.MONTH or uv in ["месяц", "месяца", "месяцев"]:
                target = self._add_months(now, 1) + timedelta(days=15)
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=False,
                    start=tokens[i].start,
                    end=ut.end,
                    confidence=0.9,
                )
                return (dt, 3)
            return None
        if target is None and delta is None:
            return None
        if target is None:
            target = now + delta
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=False,
            start=tokens[i].start,
            end=nt.end,
            confidence=0.9,
        )
        return (dt, 2)

    @staticmethod
    def _add_months(dt, months):
        """Календарный сдвиг на N месяцев с зажимом дня под длину месяца."""
        from calendar import monthrange

        m = dt.month - 1 + months
        y = dt.year + m // 12
        m = m % 12 + 1
        d = min(dt.day, monthrange(y, m)[1])
        return dt.replace(year=y, month=m, day=d)

    def _try_backward_no_number(self, tokens, i, now):
        """неделю/месяц/полгода/квартал/год/день назад (единица без числа = 1)."""
        nt = tokens[i]
        nv = nt.value.lower()
        nn = nt.normalized
        # следом должно идти слово из PREVIOUS («назад»)
        if i + 1 >= len(tokens) or tokens[i + 1].value.lower() not in Keywords.PREVIOUS:
            return None
        target = None
        delta = None
        if nn in Keywords.DAY or nv in ["день", "дня", "дней"]:
            delta = timedelta(days=1)
        elif nn in Keywords.WEEK or nv in ["неделю", "недели", "недель", "неделя"]:
            delta = timedelta(weeks=1)
        elif nn in Keywords.MONTH or nv in ["месяц", "месяца", "месяцев"]:
            target = self._add_months(now, -1)
        elif nn in Keywords.YEAR or nv in ["год", "года", "лет"]:
            target = self._add_months(now, -12)
        elif nv in Keywords.HALF_YEAR or nv in ["полгода", "полугодие", "полугодия"]:
            target = self._add_months(now, -6)
        elif nn in Keywords.QUARTER or nv in ["квартал", "квартала"]:
            target = self._add_months(now, -3)
        if target is None and delta is None:
            return None
        if target is None:
            target = now - delta
        dt = DateTimeToken(
            type=DateTimeType.SPAN_BACKWARD,
            date_from=target,
            date_to=target,
            has_time=False,
            start=tokens[i].start,
            end=tokens[i + 1].end,
            confidence=0.9,
            is_past=True,
        )
        return (dt, 2)

    def _try_forward(self, tokens, i, now):
        """через N единиц (в т.ч. дробное «через 1.5 часа»)"""
        if tokens[i].value.lower() not in Keywords.AFTER:
            return None
        if i + 2 >= len(tokens):
            return None
        import re as _re

        # дробное: «через 1.5 часа» (точка — один токен)
        mdec = _re.match(r"^(\d+)[.,](\d+)$", tokens[i + 1].value)
        if mdec:
            fnum = float(mdec.group(1) + "." + mdec.group(2))
            ut = tokens[i + 2]
            uv = ut.value.lower()
            un = ut.normalized
            delta = None
            if un in Keywords.HOUR or uv in ["час", "часа", "часов"]:
                delta = timedelta(hours=fnum)
            elif un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
                delta = timedelta(minutes=fnum)
            elif un in Keywords.DAY or uv in ["день", "дня", "дней"]:
                delta = timedelta(days=fnum)
            if delta is not None:
                target = now + delta
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=(delta < timedelta(days=1)),
                    start=tokens[i].start,
                    end=ut.end,
                    confidence=0.97,
                )
                return (dt, 3)
        num, consumed = Keywords.parse_cardinal(tokens, i + 1, self.morph)
        if num is None:
            return None
        ui = i + 1 + consumed
        # «N с половиной <единица>»: «через два с половиной часа» → 2.5
        if (
            ui + 1 < len(tokens)
            and tokens[ui].value.lower() in ("с", "со")
            and (
                tokens[ui + 1].normalized in Keywords.HALF
                or tokens[ui + 1].value.lower() in ("половиной", "половиною")
            )
        ):
            num = num + 0.5
            ui += 2
        if ui >= len(tokens):
            return None
        ut = tokens[ui]
        uv = ut.value.lower()
        un = ut.normalized
        delta = None
        target = None
        has_time = False
        if un in Keywords.MINUTE or uv in ["минут", "минуты", "минуту", "мин"]:
            delta = timedelta(minutes=num)
            has_time = True
        elif un in Keywords.HOUR or uv in ["час", "часа", "часов"]:
            delta = timedelta(hours=num)
            has_time = True
        elif un in Keywords.DAY or uv in ["день", "дня", "дней"]:
            delta = timedelta(days=num)
        elif un in Keywords.WEEK or uv in ["неделю", "недели", "недель"]:
            delta = timedelta(weeks=num)
        elif un in Keywords.MONTH or uv in ["месяц", "месяца", "месяцев"]:
            # дробные месяцы: целая часть календарно, половина ≈ 15 дней
            # (как «через полтора месяца» = +1 мес + 15 дней)
            target = self._add_months(now, int(num))
            if num != int(num):
                target += timedelta(days=15)
        elif un in Keywords.YEAR or uv in ["год", "года", "лет"]:
            target = self._add_months(now, int(num * 12))
        if target is None and delta is None:
            return None
        if target is None:
            target = now + delta
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=has_time,
            start=tokens[i].start,
            end=ut.end,
            confidence=0.95,
        )
        return (dt, ui - i + 1)

    def _try_backward(self, tokens, i, now):
        """N единиц назад (цифрой или словами)"""
        num, consumed = Keywords.parse_cardinal(tokens, i, self.morph)
        if num is None:
            return None
        ui = i + consumed
        if ui + 1 >= len(tokens) + 0 or ui >= len(tokens):
            return None
        ut = tokens[ui]
        uv = ut.value.lower()
        un = ut.normalized
        if ui + 1 >= len(tokens) or tokens[ui + 1].value.lower() not in Keywords.PREVIOUS:
            return None
        delta = None
        has_time = False
        if un in Keywords.MINUTE or uv in ["минут", "минуты", "мин"]:
            delta = timedelta(minutes=num)
            has_time = True
        elif un in Keywords.HOUR or uv in ["час", "часа", "часов"]:
            delta = timedelta(hours=num)
            has_time = True
        elif un in Keywords.DAY or uv in ["день", "дня", "дней"]:
            delta = timedelta(days=num)
        elif un in Keywords.WEEK or uv in ["неделю", "недели", "недель"]:
            delta = timedelta(weeks=num)
        if delta is None:
            return None
        target = now - delta
        dt = DateTimeToken(
            type=DateTimeType.SPAN_BACKWARD,
            date_from=target,
            date_to=target,
            has_time=has_time,
            start=tokens[i].start,
            end=tokens[ui + 1].end,
            confidence=0.95,
            is_past=True,
        )
        return (dt, ui - i + 2)

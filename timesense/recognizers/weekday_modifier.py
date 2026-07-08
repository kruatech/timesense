"""в следующую/прошлую/ближайшую <день>"""

from datetime import timedelta
import re
from .base import Recognizer
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class WeekdayModifierRecognizer(Recognizer):
    def _range_after_day(self, tokens, si):
        """Ищет диапазон времени «с H[:MM] до H[:MM]» начиная сразу после дня
        недели (индекс si — сам день). → (h1,m1,h2,m2,end_index) или None."""
        import re as _re
        j = si + 1
        if j >= len(tokens) or tokens[j].value.lower() not in ("с", "со"):
            return None

        def _tv(idx):
            if idx >= len(tokens):
                return None, None, idx
            mm = _re.match(r"^(\d{1,2}):(\d{2})$", tokens[idx].value)
            if mm:
                return int(mm.group(1)), int(mm.group(2)), idx
            if tokens[idx].value.isdigit():
                h = int(tokens[idx].value)
                if 0 <= h <= 23:
                    return h, 0, idx
            return None, None, idx

        h1, m1, i1 = _tv(j + 1)
        if h1 is None:
            return None
        di = i1 + 1
        if di >= len(tokens) or tokens[di].normalized not in Keywords.TIME_TO:
            return None
        h2, m2, i2 = _tv(di + 1)
        if h2 is None:
            return None
        return (h1, m1, h2, m2, i2)

    def recognize(self, tokens, now):
        results = []
        i = 0
        while i < len(tokens):
            r = self._try_parse(tokens, i, now)
            if r:
                results.append(r[0])
                i += r[1]
            else:
                i += 1
        return results

    def _try_parse(self, tokens, i, now):
        if i + 2 >= len(tokens):
            return None
        if tokens[i].value.lower() not in ["в", "на", "во"]:
            return None
        mod = tokens[i + 1].value.lower()
        mn = tokens[i + 1].normalized
        is_next = mn in Keywords.NEXT or mod in Keywords.NEXT
        is_prev2 = mn in Keywords.PREVIOUS2_MOD or mod in Keywords.PREVIOUS2_MOD
        is_prev = mn in Keywords.PREVIOUS_MOD or mod in Keywords.PREVIOUS_MOD
        is_near = mn in Keywords.CURRENT_NEXT or mod in Keywords.CURRENT_NEXT
        # «эту/ту/этот» (CURRENT) — указатель на текущую неделю: ближайший такой день.
        is_curr = mn in Keywords.CURRENT or mod in Keywords.CURRENT
        if not (is_next or is_prev or is_prev2 or is_near or is_curr):
            return None
        weekday = None
        for wi, days in enumerate(Keywords.days_of_week()):
            if tokens[i + 2].normalized in days or tokens[i + 2].value.lower() in days:
                weekday = wi
                break
        if weekday is None:
            return None
        cwd = now.weekday()
        if is_next:
            da = (weekday - cwd) % 7
            if da == 0:
                da = 7
            da += 7
            if (weekday - cwd) % 7 > 0:
                da = (weekday - cwd) % 7 + 7
            else:
                da = 7
        elif is_prev2:
            db = (cwd - weekday) % 7
            if db == 0:
                db = 7
            da = -db - 7  # на неделю раньше «прошлого»
        elif is_prev:
            db = (cwd - weekday) % 7
            if db == 0:
                db = 7
            da = -db
        else:  # is_near / is_curr — ближайший день (этой недели)
            da = (weekday - cwd) % 7
            if da == 0:
                da = 7
        target = now + timedelta(days=da)
        target = target.replace(hour=0, minute=0, second=0, microsecond=0)
        ei = i + 2
        # Диапазон времени после дня: «в прошлую пятницу с 08:30 до 09:15» →
        # PERIOD на дату модификатора (дата уже учитывает prev/next/near).
        rng = self._range_after_day(tokens, i + 2)
        if rng is not None:
            h1, m1, h2, m2, rend = rng
            dfrom = target.replace(hour=h1, minute=m1)
            dto = target.replace(hour=h2, minute=m2)
            if dto <= dfrom:
                dto += timedelta(days=1)
            tok = DateTimeToken(
                type=DateTimeType.PERIOD,
                date_from=dfrom,
                date_to=dto,
                has_time=True,
                start=tokens[i].start,
                end=tokens[rend].end,
                confidence=0.95,
                is_past=dfrom < now,
            )
            tok.is_explicit_range = True
            return (tok, rend - i + 1)
        ht = False
        for j in range(i + 3, min(i + 6, len(tokens))):
            if tokens[j].normalized in Keywords.TIME_FROM and j + 1 < len(tokens):
                tt = tokens[j + 1]
                m = re.match(r"(\d{1,2})[:.-](\d{2})", tt.value)
                if m:
                    target = target.replace(hour=int(m.group(1)), minute=int(m.group(2)))
                    ht = True
                    ei = j + 1
                    break
                if tt.value.isdigit():
                    h = int(tt.value)
                    if 0 <= h <= 23:
                        if 1 <= h <= 7:
                            h += 12
                        target = target.replace(hour=h)
                        ht = True
                        ei = j + 1
                        break
        ip = target < now
        return (
            DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=target,
                date_to=target if ht else target.replace(hour=23, minute=59),
                has_time=ht,
                all_day=not ht,
                start=tokens[i].start,
                end=tokens[ei].end,
                confidence=0.95,
                is_past=ip,
            ),
            ei - i + 1,
        )

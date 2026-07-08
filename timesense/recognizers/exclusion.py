"""Парсинг исключений: кроме среды, за исключением выходных"""

from datetime import timedelta
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class ExclusionParser:
    @staticmethod
    def find_exclusions(tokens, date_tokens, now):
        for i, t in enumerate(tokens):
            tv = t.value.lower()
            tn = t.normalized
            if tv in Keywords.EXCEPT or tn in Keywords.EXCEPT:
                excl = ExclusionParser._parse_target(tokens, i + 1, now)
                if excl:
                    ExclusionParser._attach(date_tokens, excl)
            elif tv in Keywords.EXCEPT_PREP and i + 1 < len(tokens):
                if tokens[i + 1].value.lower() in Keywords.EXCEPT:
                    excl = ExclusionParser._parse_target(tokens, i + 2, now)
                    if excl:
                        ExclusionParser._attach(date_tokens, excl)

    @staticmethod
    def _parse_target(tokens, start, now):
        if start >= len(tokens):
            return None
        excluded = []
        j = start
        while j < len(tokens):
            t = tokens[j]
            for wi, days in enumerate(Keywords.days_of_week()):
                if t.normalized in days or t.value.lower() in days:
                    da = (wi - now.weekday()) % 7
                    if da == 0:
                        da = 7
                    ed = now + timedelta(days=da)
                    ed = ed.replace(hour=0, minute=0, second=0, microsecond=0)
                    ex = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=ed,
                        date_to=ed.replace(hour=23, minute=59),
                        has_time=False,
                        all_day=True,
                        start=t.start,
                        end=t.end,
                    )
                    ex._excl_weekdays = [wi]
                    excluded.append(ex)
                    break
            if t.value.lower() in Keywords.WEEKEND:
                wd = now.weekday()
                sat = now + timedelta(days=(5 - wd) % 7 or 7)
                sat = sat.replace(hour=0, minute=0, second=0, microsecond=0)
                sun = sat + timedelta(days=1)
                ex = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=sat,
                    date_to=sun.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    start=t.start,
                    end=t.end,
                )
                ex._excl_weekdays = [5, 6]
                excluded.append(ex)
            if t.value.lower() in ["и", ","]:
                j += 1
                continue
            j += 1
            if j < len(tokens):
                found = False
                for days in Keywords.days_of_week():
                    if tokens[j].normalized in days or tokens[j].value.lower() in days:
                        found = True
                        break
                if not found and tokens[j].value.lower() not in ["и", ","]:
                    break
        return excluded if excluded else None

    @staticmethod
    def _attach(date_tokens, exclusions):
        if date_tokens:
            date_tokens[0].exclusions.extend(exclusions)

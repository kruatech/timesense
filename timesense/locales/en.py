"""English locale for TimeSense — regex-driven date/time/recurrence parser.

Produces a single best DateTimeToken (with flags the shared classifier understands)
plus a cleaned title. English grammar is positional/regular, so this locale parses
the raw (lowercased) text with ordered regex handlers rather than morphology.

Covered: today/tomorrow/tonight/yesterday/day after tomorrow; [next|this|last]
weekday; month-name dates (Feb 17 / 17 Feb / March 3rd [, YYYY]); MM/DD[/YYYY] and
ISO; times (at 5pm, 5:30pm, at 17:00, noon, midnight, day-parts); in N units;
ranges (from 9 to 5, 9am-11am, between 10 and 12); recurrence (every day/week/
month/year, daily/weekly, every Monday, every weekday/on weekdays, every N units,
every other week, every month on the Nth); deadlines (by/before/due <date|time>,
by end of week/month/year); duration (for N hours/minutes).
"""

import re
from datetime import datetime, timedelta
from calendar import monthrange
from ..models.datetime_token import DateTimeToken, DateTimeType, RecurrenceRule

WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_WD = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
    "half": 0.5,
}
DAYPARTS = {
    "morning": (9, 12),
    "afternoon": (12, 15),
    "evening": (18, 22),
    "night": (22, 30),
    "tonight": (18, 22),
    # «towards evening» = RU «ближе к вечеру» — чуть раньше вечера
    "towardsevening": (17, 21),
}
# Служебные слова, которые нужны ВНУТРИ названия («sign in to the portal»,
# «turn off the stove»), но не на его краях (паритет с RU-локалью).
_EDGE_FILLER = {
    "a", "an", "the", "at", "on", "in", "by", "of", "to", "from", "and", "for",
    "before", "after", "with", "or",
}

_FILLER = {
    "a",
    "an",
    "the",
    "at",
    "on",
    "in",
    "by",
    "of",
    "to",
    "from",
    "and",
    "please",
    "remind",
    "me",
    "reminder",
    "for",
    "this",
    "next",
    "last",
    "every",
    "each",
    "before",
    "after",
    "due",
    "um",
    "uh",
    "like",
    "so",
    "with",
    "except",
    "excluding",
    "through",
    "around",
    "about",
    "exactly",
    "sharp",
    "roughly",
    "approximately",
    "maybe",
    "perhaps",
    "pls",
    "gotta",
    "wanna",
    "either",
    "or",
}


class EnglishLocaleParser:
    _EN_NUM = {
        "zero": 0,
        "oh": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fourty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
        "hundred": 100,
    }

    def __init__(self, config):
        self.config = config
        self.nf = config.prefer_nearest_future

    def _invalid_date(self, low):
        """True для невозможной явной даты: 'Feb 31', '31 Feb', '2/31'."""
        from calendar import monthrange

        def bad(mon, day, year=None):
            if not (1 <= day <= 31):
                return False
            maxd = (
                monthrange(year, mon)[1] if year else (29 if mon == 2 else monthrange(2001, mon)[1])
            )
            return day > maxd

        m = re.search(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", low)
        if m and bad(MONTHS[m.group(1)], int(m.group(2)), int(m.group(3)) if m.group(3) else None):
            return True
        m = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MON + r")\.?(?:,?\s+(\d{4}))?\b", low
        )
        if m and bad(MONTHS[m.group(2)], int(m.group(1)), int(m.group(3)) if m.group(3) else None):
            return True
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
        if m:
            mo = int(m.group(1))
            day = int(m.group(2))
            yr = m.group(3)
            if mo > 12 and 1 <= day <= 12:  # 25/09 → DD/MM
                mo, day = day, mo
            if not (1 <= mo <= 12):
                return True  # 13/13 — ни MM/DD, ни DD/MM
            y = int(yr) if yr else None
            if y is not None and y < 100:
                y += 2000
            if bad(mo, day, y):
                return True
        return False

    # ── number-word preprocessing (voice / spelled-out) ──────────────────
    def _num_run(self, toks, i):
        cur = 0
        cnt = 0
        got = False
        while i + cnt < len(toks):
            v = self._EN_NUM.get(toks[i + cnt])
            if v is None:
                break
            if v >= 100:
                cur = (cur or 1) * v
            else:
                cur += v
            got = True
            cnt += 1
            if v < 20:  # unit/teen ends the run
                break
        return (cur, cnt) if got else (0, 0)

    def _digitize(self, s):
        toks = s.split(" ")
        out = []
        i = 0
        while i < len(toks):
            val, cnt = self._num_run(toks, i)
            if cnt > 0:
                out.append(str(val))
                i += cnt
            else:
                out.append(toks[i])
                i += 1
        return " ".join(out)

    _ORD_ONES = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
        "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
        "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
        "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
    }
    _ORD_TENS = {"twenty": 20, "thirty": 30}
    _ORD_UNIT = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
    }

    def _fold_ordinals(self, s):
        """Порядковые слова дня месяца → цифра+th, чтобы _month_date их поймал.
        Составные: 'twenty eighth' → '28th'; одиночные: 'fifteenth' → '15th'.
        Делается ДО _digitize, иначе 'twenty' уедет в 20, а 'eighth' потеряется."""
        def _comp(m):
            return str(self._ORD_TENS[m.group(1)] + self._ORD_UNIT[m.group(2)]) + "th"

        _kind = (
            r"(?:business\s+day|weekday|weekend|week|last|to|" + _WD + r")"
        )
        s = re.sub(
            r"\b(twenty|thirty)\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)"
            r"\b(?![-\s]" + _kind + r")",
            _comp,
            s,
        )

        def _single(m):
            return str(self._ORD_ONES[m.group(1)]) + "th"

        s = re.sub(
            r"\b(" + "|".join(self._ORD_ONES) + r")\b(?![-\s]" + _kind + r")", _single, s
        )
        return s

    _PRE_CACHE_MAX = 512

    def _preprocess(self, s):
        """Кэшируемая обёртка: за один parse() предобработка нужна 4–7 раз
        (within, основной разбор, локация, пост-проверки), а она чистая."""
        cache = self.__dict__.setdefault("_pre_cache", {})
        r = cache.get(s)
        if r is None:
            if len(cache) >= self._PRE_CACHE_MAX:
                cache.clear()
            r = cache[s] = self._preprocess_raw(s)
        return r

    def _preprocess_raw(self, s):
        # окно «после X, но до Y»: «after 10 but before 12», «no earlier than 10 and no later
        # than 12», «not before 10 but before 12» → «from X to Y» (паритет с RU «после 10 но до 12»)
        _T = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon)"
        s = re.sub(
            r"\b(?:after|no\s+earlier\s+than|not\s+before)\s+" + _T +
            r"\s*,?\s+(?:but\s+|and\s+)?(?:before|no\s+later\s+than|not\s+later\s+than|by)\s+" + _T,
            r"from \1 to \2", s,
        )
        # «no earlier than 10am» → открытое начало, как «after 10am» (паритет с RU «не раньше 10»)
        s = re.sub(r"\b(?:no\s+earlier\s+than|not\s+before)\s+(?=\d|noon)", "after ", s)
        # «from now until friday» → «by friday» (как RU «до пятницы»)
        s = re.sub(r"\bfrom\s+now\s+(?:on\s+)?(?:until|till|to)\s+", "by ", s)
        # окна по частям суток: «from morning to noon», «from lunch to evening»
        _DP = {"morning": "9am", "noon": "12pm", "midday": "12pm", "lunch": "1pm",
               "lunchtime": "1pm", "afternoon": "3pm", "evening": "7pm", "night": "10pm"}
        s = re.sub(
            r"\bfrom\s+(?:the\s+)?(morning|noon|midday|lunchtime|lunch|afternoon|evening)\s+"
            r"(?:to|till|until)\s+(?:the\s+)?(noon|midday|lunchtime|lunch|afternoon|evening|night)\b",
            lambda m: "from %s to %s" % (_DP[m.group(1)], _DP[m.group(2)]), s,
        )
        # «through tuesday», «until tuesday inclusive» → «by tuesday» (дедлайн, как RU
        # «до вторника включительно») — только в разовой фразе и не внутри диапазона
        # («every friday until end of march» — это UNTIL; «monday through friday» — диапазон)
        if not re.search(r"\b(?:every|each|daily|weekly|monthly|yearly|from|between)\b", s):
            s = re.sub(
                r"(?<!\w)(?:^|(?<=\s))(?:through|thru|until|till)\s+"
                r"(?=(?:the\s+)?(?:" + _WD + r"|" + _MON + r"|end\s+of)\b)",
                lambda m: m.group(0) if re.search(r"(?:" + _WD + r")\s*$", s[:m.start()]) else "by ",
                s,
            )
        s = re.sub(r"\b(?:inclusive|inclusively)\b", " ", s)
        # «in the next 2 hours» → «within 2 hours»
        s = re.sub(r"\bin\s+the\s+next\s+", "within ", s)
        # «from 9am on april 12 1961 to 11am» → «on april 12 1961 from 9am to 11am»
        # (диапазон, разорванный датой — паритет с RU «с 9 утра 12 апреля до 11 утра»)
        _TM = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"
        _DT = (r"(?:(?:" + _MON + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?"
               r"\s+(?:of\s+)?(?:" + _MON + r")(?:,?\s+\d{4})?|" + _WD + r"|tomorrow|today)")
        s = re.sub(r"\bfrom\s+(" + _TM + r")\s+(?:on\s+)?(" + _DT + r")\s+(to|till|until)\s+(" + _TM + r")\b",
                   lambda m: "%s%s from %s to %s" % (
                       "" if m.group(2) in ("tomorrow", "today") else "on ", m.group(2), m.group(1), m.group(4)),
                   s)
        # «from 10am to noon», «from 10pm to midnight» — полдень/полночь как граница диапазона
        s = re.sub(r"\b(from\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s+(?:to|till|until)\s+)noon\b", r"\g<1>12pm", s)
        s = re.sub(r"\b(from\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s+(?:to|till|until)\s+)midnight\b", r"\g<1>12am", s)
        s = re.sub(r"\bfrom\s+noon\s+(?=(?:to|till|until)\s+\d)", "from 12pm ", s)

        # «every hour», «hourly» → «every 1 hours» (паритет с RU «каждый час»)
        s = re.sub(r"\b(?:every\s+hour|hourly)\b", "every 1 hours", s)
        # «no later than» / «not later than» → «by» (дедлайн-синоним) -> by
        s = re.sub(r"\bno(?:t)?\s+later\s+than\b", "by", s)
        # опечатки во временных словах: «wensday», «thurday», «tomorow», «febuary»
        from ..core.typo import en_fixer

        s = re.sub(r"\b(?:wensday|wendsday|wedensday|wednsday)\b", "wednesday", s)
        s = en_fixer().fix_text(s)
        # «a couple of hours» → «2 hours»
        s = re.sub(r"\b(?:a\s+)?couple(?:\s+of)?\b(?=\s+(?:minutes?|hours?|days?|weeks?|months?))", "2", s)
        # чат-сленг и частые опечатки
        s = re.sub(
            r"\b(?:tmrw|tmrrw|tmr|tmw|tomorow|tommorow|tommorrow|2moro|2morrow|2mrw)\b",
            "tomorrow", s,
        )
        s = re.sub(r"\btonite\b", "tonight", s)
        # «eod report» без «by» — тоже дедлайн (паритет с RU «до конца дня»)
        s = re.sub(
            r"\b(?:by\s+)?(?:the\s+)?(?:eod|cob|close of business|end of (?:the )?business day)\b",
            "by end of day", s,
        )
        s = re.sub(r"(?<!of )\b(?:by\s+)?(?:the\s+)?end of (?:the )?day\b", "by end of day", s)
        s = re.sub(r"\beow\b", "end of week", s)
        s = re.sub(r"\beom\b", "end of month", s)
        s = re.sub(r"\blater today\b", "today", s)
        # смешанный ввод: русские относительные дни в английской фразе («завтра at 10»)
        for ru, en in (("послезавтра", "day after tomorrow"), ("завтра", "tomorrow"),
                       ("сегодня", "today"), ("вчера", "yesterday")):
            s = re.sub(r"(?<![\w])" + ru + r"(?![\w])", en, s)
        s = re.sub(r"(\d{4}-\d{2}-\d{2})t(\d{2}:\d{2})", r"\1 \2", s)  # ISO 2026-10-01T09:00
        # «all day», «the whole day» — просто день; «the whole week», «all week» — эта неделя
        s = re.sub(r"\b(?:all|the\s+whole|whole)\s+day\b", " ", s)
        s = re.sub(r"\b(?:all|the\s+whole|whole)\s+week\b", "this week", s)
        # «once a month on the 5th» → «every month on the 5th»
        s = re.sub(r"\bonce\s+(?:a|per|every)\s+(day|week|month|year)\b", r"every \1", s)
        # «lasting 2 hours» → «for 2 hours»
        s = re.sub(r"\b(?:lasting|that\s+lasts|which\s+lasts)\b", "for", s)
        # «from morning till evening» → 09:00–19:00 (паритет с RU «с утра до вечера»)
        s = re.sub(r"\bfrom\s+(?:the\s+)?morning\s+(?:till|until|to)\s+(?:the\s+)?evening\b",
                   "from 9am to 7pm", s)
        # «this morning» — сегодняшнее утро (даже если прошло); «last night» — вчерашняя ночь
        s = re.sub(r"\bthis\s+(morning|afternoon|evening)\b", r"today in the \1", s)
        # «towards / closer to (the) evening» → окно 17–21 (как RU «ближе к вечеру»)
        s = re.sub(r"\b(?:towards|toward|closer\s+to|nearer\s+to)\s+(?:the\s+)?evening\b", "towardsevening", s)
        s = re.sub(r"\blast\s+night\b", "yesterday night", s)
        # «early morning», «late evening» — уточнение внутри части суток, не название
        s = re.sub(r"\b(?:early|late)\s+(?=(?:in\s+the\s+)?(?:morning|afternoon|evening|night)\b)", "", s)
        # «around 5», «about 5pm», «at around 5», «5ish», «at 5 sharp»
        s = re.sub(r"\b(?:at\s+)?(?:around|about|approximately|approx\.?|roughly)\s+(?=\d)", "at ", s)
        s = re.sub(r"\b(?:at\s+)?(\d{1,2})ish\b", r"at \1", s)
        s = re.sub(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+sharp\b", r"\1", s)
        # «weekdays at 9am» → «every weekday at 9am» (паритет с RU «по будням»)
        s = re.sub(r"^\s*weekdays\b", "every weekday", s)
        # «every last day of the month» → «every month on the 31st» не подходит (февраль);
        # помечаем маркером и доводим до BYMONTHDAY=-1 в parse()
        s = re.sub(r"\bevery\s+last\s+day\s+of\s+(?:the|each|every)\s+month\b|"
                   r"\bon\s+the\s+last\s+day\s+of\s+(?:every|each)\s+month\b",
                   "every month lastdaymarker", s)
        s = re.sub(r"\bthe\s+(first|last)\s+day\s+of\b", r"\1 day of", s)
        # «a week from monday» = понедельник после ближайшего (= next monday)
        s = re.sub(r"\b(?:a|one|1)\s+week\s+from\s+(" + _WD + r")\b", r"next \1", s)
        # «every last friday» / «every first monday» без «of the month» → ежемесячно
        s = re.sub(
            r"\bevery\s+(first|second|third|fourth|last|1st|2nd|3rd|4th)\s+(" + _WD + r")\b"
            r"(?!\s+(?:of|in)\b)",
            r"every \1 \2 of the month", s,
        )
        # интервальные повторы: «biweekly», «fortnightly», «every second/third week»,
        # «every other week», «once every two weeks», «every quarter», «every half year»
        s = re.sub(r"\b(?:bi-?weekly|fortnightly|every\s+fortnight)\b", "every 2 weeks", s)
        s = re.sub(r"\bonce\s+(?=every\b)", "", s)
        s = re.sub(r"\bevery\s+other\s+(week|month|day|year)\b", r"every 2 \1s", s)
        s = re.sub(
            r"\bevery\s+(second|2nd|2th|third|3rd|3th|fourth|4th)\s+(week|month|day|year)\b",
            lambda m: "every %s %ss" % ({"s": "2", "2": "2", "t": "3", "3": "3", "f": "4", "4": "4"}[m.group(1)[0]],
                                        m.group(2)),
            s,
        )
        s = re.sub(r"\b(?:every\s+quarter|quarterly|once\s+a\s+quarter)\b", "every 3 months", s)
        s = re.sub(r"\b(?:every\s+half\s+(?:a\s+)?year|semi-?annually|every\s+six\s+months)\b",
                   "every 6 months", s)
        # «every other wednesday» → «every 2 weeks on wednesday»
        s = re.sub(r"\bevery\s+other\s+(" + _WD + r")\b", r"every 2 weeks on \1", s)
        # «(on) the last business day of every month» → «every last business day of the month»
        s = re.sub(
            r"\b(?:on\s+)?(?:the\s+)?(last|first)\s+business\s+day\s+of\s+(?:every|each)\s+month\b",
            r"every \1 business day of the month", s,
        )
        s = re.sub(
            r"\bevery\s+month\s+on\s+(?:the\s+)?(last|first)\s+business\s+day\b",
            r"every \1 business day of the month", s,
        )
        # «first monday of every month» → «every first monday of the month»
        s = re.sub(
            r"\b(?:the\s+)?(first|second|third|fourth|last|1st|2nd|3rd|4th)\s+(" + _WD + r")\s+of\s+"
            r"(?:every|each)\s+month\b",
            r"every \1 \2 of the month", s,
        )
        # «on 15th» → «on the 15th»
        s = re.sub(r"\bon\s+(\d{1,2})(st|nd|rd|th)\b", r"on the \1\2", s)
        # «3 days from now», «a week from today» → «in 3 days»
        s = re.sub(
            r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(minutes?|hours?|days?|weeks?|months?|years?)\s+from\s+(?:now|today)\b",
            r"in \1 \2", s,
        )
        # обед (паритет с RU «до обеда / после обеда / в обед» = 13:00)
        s = re.sub(r"\bbefore\s+lunch(?:time)?\b", "by 13:00", s)
        s = re.sub(r"\bafter\s+lunch(?:time)?\b", "after 13:00", s)
        s = re.sub(r"\bat\s+lunch(?:time)?\b", "at 13:00", s)
        # «at 1930» → «at 19:30» (не годы); «7.30pm» → «7:30pm»
        s = re.sub(r"\bat\s+(?!20\d\d)([01]\d|2[0-3])([0-5]\d)\b", r"at \1:\2", s)
        s = re.sub(r"\b(\d{1,2})\.([0-5]\d)\s*(am|pm)\b", r"\1:\2\3", s)
        # «on even days», «every odd day» → маркер, доводится до BYMONTHDAY в parse()
        s = re.sub(r"\b(?:on\s+|every\s+)?(even|odd)(?:-numbered)?\s+days?\b", r"every month \1daysmarker", s)
        # «every 15th», «every 1st of the month» → «every month on the 15th»
        s = re.sub(
            r"\bevery\s+(\d{1,2})(st|nd|rd|th)(?:\s+(?:day\s+)?of\s+(?:the|each|every)\s+month)?\b"
            r"(?!\s+(?:mon|tue|wed|thu|fri|sat|sun|week|business|weekday|weekend|day))",
            r"every month on the \1\2", s,
        )
        # «until 6pm» вне повторения — дедлайн, как «by 6pm»
        if not re.search(r"\b(?:every|each|daily|weekly|monthly|yearly)\b", s):
            s = re.sub(r"\buntil\s+(?=\d|noon\b|midnight\b|(?:the\s+)?end\s+of\b|the\s+\d)", "by ", s)
        # forty-five → forty five (не трогаем границы с цифрами, чтобы не сломать 9am-11am)
        s = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", s)
        s = self._fold_ordinals(s)
        s = self._digitize(s)
        # «in an hour fifteen», «in 2 hours 30 (minutes)» → «in N minutes»
        s = re.sub(
            r"\bin\s+(?:(\d{1,2})|an?|one)\s+hours?\s+(?:and\s+)?(\d{1,2})(?:\s+(?:minutes?|mins?))?\b"
            r"(?!\s*(?:am|pm|:|st|nd|rd|th))",
            lambda m: ("in %d minutes" % ((int(m.group(1)) if m.group(1) else 1) * 60 + int(m.group(2))))
            if int(m.group(2)) <= 59 else m.group(0),
            s,
        )
        # британское «at half 10» = 10:30 («half past» обрабатывается выше)
        s = re.sub(r"\b(at\s+)?half\s+(\d{1,2})\b(?!\s*(?:an?\s+hour|hours?|past))",
                   lambda m: "%s%s:30" % (m.group(1) or "at ", m.group(2)), s)
        # «every morning/evening» → ежедневно + часть суток (паритет с RU «каждое утро»)
        s = re.sub(r"\bevery\s+(morning|afternoon|evening|night)\b", r"every day in the \1", s)
        # «every march 5» → «every year on march 5»
        s = re.sub(r"\bevery\s+(" + _MON + r")\.?\s+(\d{1,2})(st|nd|rd|th)?\b", r"every year on \1 \2", s)
        # clock idioms → "at H:MM". Час — как в RU-форме той же фразы: «half past four» =
        # «половина пятого» → 16:30, «quarter to eight» = «без четверти восемь» → 07:45
        # (итоговый час 1–6 → после полудня; «o'clock» 1–7 → после полудня).
        nf = self.nf

        def _pm(h, hi=6):
            return h + 12 if nf and 1 <= h <= hi else h

        # «half past six pm» — am/pm задаёт половину суток явно
        def _ap_idiom(m, minutes, delta=0):
            h = (int(m.group(1)) + delta) % 24
            ap = (m.group(2) or "").replace(".", "")
            if ap == "pm" and h < 12:
                h += 12
            elif ap == "am" and h == 12:
                h = 0
            elif not ap:
                h = _pm(h)
            return "at %d:%02d" % (h, minutes)

        s = re.sub(r"\bhalf past (\d{1,2})(?:\s*(am|pm|a\.m\.|p\.m\.))?\b", lambda m: _ap_idiom(m, 30), s)
        s = re.sub(r"\bquarter past (\d{1,2})\b", lambda m: "at %d:15" % _pm(int(m.group(1))), s)
        s = re.sub(
            r"\bquarter to (\d{1,2})\b", lambda m: "at %d:45" % _pm((int(m.group(1)) - 1) % 24), s
        )
        s = re.sub(r"\b(\d{1,2})\s*o'?clock\b", lambda m: "at %d:00" % _pm(int(m.group(1)), 7), s)
        # "at 10 30" / "ten thirty" (после digitize → "10 30") → 10:30
        s = re.sub(
            r"\bat (\d{1,2}) (\d{2})\b", lambda m: "at %d:%s" % (int(m.group(1)), m.group(2)), s
        )
        # "at 9-30" / "at 9.30" → "at 9:30" (дефис/точка = разделитель минут, минуты 0..59)
        s = re.sub(
            r"\bat (\d{1,2})[.\-](\d{2})\b",
            lambda m: ("at %d:%02d" % (int(m.group(1)), int(m.group(2)))) if int(m.group(2)) <= 59 else m.group(0),
            s,
        )
        s = re.sub(
            r"\b(\d{1,2}) (00|05|10|15|20|25|30|35|40|45|50|55)\b(?!\s*(?:to|-|:|am|pm|and))",
            lambda m: (
                ("%d:%s" % (int(m.group(1)), m.group(2)))
                if 0 <= int(m.group(1)) <= 23
                else m.group(0)
            ),
            s,
        )
        return s

    # ── public ──────────────────────────────────────────────────────────
    # Существительные-места для извлечения локации (зеркало RU LOCATION_MARKERS)
    _LOC_NOUNS = frozenset(
        [
            "office",
            "home",
            "cafe",
            "restaurant",
            "park",
            "gym",
            "school",
            "university",
            "college",
            "hospital",
            "clinic",
            "bank",
            "airport",
            "station",
            "club",
            "studio",
            "cinema",
            "theater",
            "theatre",
            "museum",
            "library",
            "pool",
            "stadium",
            "mall",
            "shop",
            "store",
            "work",
            "downtown",
            "bar",
            "hotel",
            "beach",
            "rooftop",
            "zoom",
        ]
    )
    # Двусловные места («at the client site», «in the meeting room»).
    _LOC_PHRASES = (
        "meeting room",
        "conference room",
        "client site",
        "video call",
        "war room",
        "server room",
    )

    def _location(self, low):
        """«at/in [the] <место>» → (фраза локации, существительное) | None.

        Как и в RU: маркер места считается локацией только с предлогом,
        иначе слово остаётся частью названия события.
        """
        # сначала двусловные («in the meeting room», «at the client site»)
        for ph in self._LOC_PHRASES:
            mm = re.search(r"\b(at|in)\s+(?:the\s+)?" + ph + r"\b", low)
            if mm:
                return mm.group(0), ph.split()
        for m in re.finditer(r"\b(at|in)\s+(?:the\s+)?([a-z]+)\b", low):
            if m.group(2) in self._LOC_NOUNS:
                return m.group(0), [m.group(2)]
        return None

    def parse(self, text, now):
        """→ (DateTimeToken | None, title, duration_minutes, location | None)."""
        wr = self._within(text, now)
        if wr is not None:
            dt, title, dur = wr
        else:
            dt, title, dur = self._parse_impl(text, now)
        if dt is not None and "lastdaymarker" in self._preprocess(text.lower()):
            rec = dt.recurrence
            if rec is not None and rec.frequency == "MONTHLY":
                rec.by_month_day = [-1]
                last = now.replace(day=monthrange(now.year, now.month)[1], hour=0, minute=0,
                                   second=0, microsecond=0)
                if dt.has_time:
                    last = last.replace(hour=dt.date_from.hour, minute=dt.date_from.minute)
                dt.date_from = dt.date_to = last
            if title:
                title = " ".join(w for w in title.split() if w != "lastdaymarker")
        # «on even / odd days» → BYMONTHDAY=2,4,…,30 / 1,3,…,31 (паритет с RU «по чётным числам»)
        low_eo = self._preprocess(text.lower())
        meo = re.search(r"(even|odd)daysmarker", low_eo)
        if meo and dt is not None and dt.recurrence is not None and dt.recurrence.frequency == "MONTHLY":
            dt.recurrence.by_month_day = list(range(2, 31, 2)) if meo.group(1) == "even" else list(range(1, 32, 2))
            if title:
                title = " ".join(w for w in title.split() if "daysmarker" not in w)
        # «from june 22 1941 to may 9 1945» — диапазон явных дат через годы (паритет с RU)
        if dt is not None and dt.recurrence is None:
            low_r = self._preprocess(text.lower())
            _MD = r"(?:(?:" + _MON + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:" + _MON + r")(?:,?\s+\d{4})?)"
            mr = re.search(r"\bfrom\s+(" + _MD + r")\s+(?:to|till|until|through)\s+(" + _MD + r")\b", low_r)
            if mr:
                a1, a2 = self._month_date(mr.group(1), now), self._month_date(mr.group(2), now)
                if a1 is not None and a2 is not None:
                    s1 = a1[0].replace(hour=0, minute=0, second=0, microsecond=0)
                    e2 = a2[0].replace(hour=23, minute=59, second=0, microsecond=0)
                    if e2 > s1 and (dt.date_to is None or dt.date_to < e2):
                        dt = DateTimeToken(type=DateTimeType.PERIOD, date_from=s1, date_to=e2, has_time=False,
                                           all_day=True, confidence=0.98, is_past=e2 < now)
                        dt.is_explicit_range = True
        # границы серии: «every monday from october 1 to december 1» (старт + UNTIL),
        # «starting october 1 every monday» (старт) — паритет с RU «с 1 октября по …»
        rec = getattr(dt, "recurrence", None) if dt is not None else None
        if rec is not None:
            low_s = self._preprocess(text.lower())
            series_from = None
            dr = self._date_range(low_s, now)  # (start, span, fuzzy, is_period, end)
            if dr is not None and dr[4] is not None:
                series_from = dr[0].replace(hour=0, minute=0, second=0, microsecond=0)
                if rec.until is None and rec.count is None:
                    rec.until = dr[4].replace(hour=23, minute=59, second=0, microsecond=0)
            else:
                ms = re.search(r"\b(?:starting|beginning|effective|from)(?:\s+(?:on|from))?\s+", low_s)
                if ms:
                    # только отрезок сразу после «starting» — иначе «monday» из правила перебьёт дату
                    seg = re.split(r"\b(?:every|each|at|until|till|through|to)\b", low_s[ms.end():], maxsplit=1)[0]
                    dres = self._date(seg, now)
                    if dres is not None and not dres[3]:
                        series_from = dres[0].replace(hour=0, minute=0, second=0, microsecond=0)
            if series_from is not None and series_from > now:
                rec._series_from = series_from  # общий снап парсера учтёт дату начала
                first = self._first_occurrence(rec, series_from)
                if first is not None:
                    if dt.has_time:
                        dt.date_from = first.replace(hour=dt.date_from.hour, minute=dt.date_from.minute)
                    else:
                        dt.date_from = first
                    dt.date_to = dt.date_from
            if title:
                title = re.sub(r"^(?:starting|beginning|effective)\s+", "", title, flags=re.IGNORECASE)
        # «every year on the last friday of october» → YEARLY;BYMONTH=10;BYDAY=-1FR (паритет с RU)
        low_y = self._preprocess(text.lower())
        if dt is not None and re.search(r"\b(?:every\s+year|each\s+year|yearly|annually)\b", low_y):
            my = re.search(r"\b(?:the\s+)?(first|second|third|fourth|last|1st|2nd|3rd|4th|1th|2th|3th|4th)\s+("
                           + _WD + r")\s+(?:of|in)\s+(" + _MON + r")\b", low_y)
            if my:
                w = my.group(1)
                n = -1 if w == "last" else (int(w[0]) if w[0].isdigit()
                                            else {"first": 1, "second": 2, "third": 3, "fourth": 4}[w])
                rec_y = dt.recurrence or RecurrenceRule(frequency="YEARLY")
                rec_y.frequency = "YEARLY"
                rec_y.by_month = [MONTHS[my.group(3)]]
                rec_y.by_day = ["%d%s" % (n, RRULE_DAYS[WEEKDAYS[my.group(2)]])]
                dt.recurrence = rec_y
                if title:
                    title = " ".join(x for x in title.split() if x.lower() not in ("every", "year", "yearly", "annually"))
        # «every 30 minutes from 9 to 6», «every hour from 9 to 5»: частый повтор в окне часов
        if (dt is not None and dt.recurrence is not None
                and dt.recurrence.frequency in ("MINUTELY", "HOURLY") and dt.has_time
                and dt.date_to is not None and dt.date_to > dt.date_from):
            from ..core.parser import TimeSenseParser as _P

            first = _P.apply_hour_window(dt.recurrence, dt.date_from, dt.date_to, now)
            if first is not None:
                dt.type = DateTimeType.FIXED
                dt.date_from = dt.date_to = first
                dt.is_explicit_range = False  # окно ушло в BYHOUR — это напоминание, не событие
        # исключённые даты: «every day except december 31», «excluding jan 1 and jan 8»
        # (дни недели — «except friday» — обрабатываются в правиле повтора)
        if dt is not None:
            low_x = self._preprocess(text.lower())
            mx = re.search(r"\b(?:except|excluding|apart\s+from|but\s+not)\s+(?:on\s+)?", low_x)
            if mx:
                seg = re.split(r"\b(?:at|every|each|from|until|till)\b|,(?!\s*(?:and\s+)?(?:" + _MON
                               + r"))", low_x[mx.end():], maxsplit=1)[0]
                ex_dates = []
                for part in re.split(r"\s*(?:,|\band\b)\s*", seg):
                    if not re.search(_MON, part):
                        continue  # только конкретные даты с месяцем
                    md = self._month_date(part.strip(), now)
                    if md is not None:
                        ex_dates.append(md[0].date())
                if ex_dates:
                    if dt.recurrence is not None:
                        dt.recurrence._exdate_dates = ex_dates
                    elif dt.date_from.date() in ex_dates:
                        dt = None  # «except december 31» без серии — исключать не из чего
        # ежегодное с датой: «every year on march 5» → BYMONTH/BYMONTHDAY (паритет с RU)
        rec = getattr(dt, "recurrence", None) if dt is not None else None
        if rec is not None and rec.frequency == "YEARLY" and not rec.by_month:
            md = self._month_date(self._preprocess(text.lower()), now)
            if md is not None:
                d = md[0]
                rec.by_month, rec.by_month_day = [d.month], [d.day]
                start = dt.date_from.replace(month=d.month, day=d.day) if dt.has_time else d
                if start < now:
                    start = start.replace(year=start.year + 1)
                dt.date_from = dt.date_to = start
        # команда боту («remind me [to]», «please remind us», «set a reminder to»)
        # — не часть названия (паритет с RU «напомни мне»)
        if title:
            title = re.sub(
                r"^(?:please\s+)?remind\s+(?:me|us)(?:\s+to)?\b\s*", "", title, flags=re.IGNORECASE
            ).strip()
            # «reminder» / «set a reminder to» вырезаем, только если дальше есть суть
            title = re.sub(
                r"^(?:set\s+(?:a\s+)?)?reminder(?:\s+to)?\s+(?=\S)", "", title, flags=re.IGNORECASE
            ).strip()
            if re.search(r"\bset\s+(?:a\s+)?reminder\b", text, re.IGNORECASE):
                title = re.sub(r"^set\s+(?:a|an|the)?\s*(?=\S)", "", title, flags=re.IGNORECASE).strip()
            # «remind me … to call mom» → «call mom» (ведущее «to» от команды)
            if re.search(r"\b(?:remind\s+(?:me|us)|reminder)\b", text, re.IGNORECASE):
                title = re.sub(r"^to\s+(?=\S)", "", title, flags=re.IGNORECASE).strip()

        # «after 5pm call» — открытое начало (паритет с RU «после 17 созвон» → OPEN_START)
        if (
            dt is not None and dt.has_time and dt.recurrence is None
            and dt.type == DateTimeType.FIXED and not dt.is_deadline
            and re.search(r"\bafter\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b",
                          self._preprocess(text.lower()))
        ):
            dt._open_start = True
        loc = None
        if dt is not None:
            found = self._location(self._preprocess(text.lower()))
            if found:
                loc, nouns = found
                # слова места не должны оставаться в названии события:
                # сначала вся фраза локации («in the office»), затем сами существительные
                if title:
                    title = re.sub(
                        r"(?<![\w'])" + re.escape(loc) + r"(?![\w'])", " ", title, flags=re.IGNORECASE
                    )
                    title = " ".join(title.split())
                    drop = {w.lower() for w in nouns}
                    title = " ".join(
                        w for w in title.split() if w.lower() not in drop
                    )
        # дедлайн с днём И временем: «by 5pm on friday», «by friday 5pm» → пятница 17:00
        if dt is not None and dt.is_deadline and dt.recurrence is None:
            low_d = self._preprocess(text.lower())
            dr, tr = self._date(low_d, now), self._time(low_d, now)
            if dr is not None and not dr[3] and tr is not None and not isinstance(tr[3], tuple):
                dt.date_to = dr[0].replace(hour=tr[0], minute=tr[1], second=0, microsecond=0)
        # «by the 20th» — дедлайн до конца этого дня (паритет с RU «до 20-го»)
        if (
            dt is not None and not dt.is_deadline and dt.recurrence is None and not dt.has_time
            and re.search(r"\bby\s+the\s+\d{1,2}(?:st|nd|rd|th)\b", self._preprocess(text.lower()))
        ):
            dt.is_deadline = True
            dt.date_to = dt.date_from.replace(hour=23, minute=59)
            dt.date_from = now
        # дедлайн «by the 20th» без времени = конец дня (паритет с RU «до 20-го» → 23:59)
        if (
            dt is not None and dt.is_deadline and dt.date_to is not None
            and (dt.date_to.hour, dt.date_to.minute) == (0, 0)
            and not re.search(r"\bmidnight\b|\b(?:0?0|12)(?::00)?\s*(?:am)?\b", text.lower())
        ):
            dt.date_to = dt.date_to.replace(hour=23, minute=59)
        if title:
            # висящие на краях служебные слова («on», «the», «in the» после локации);
            # «on»/«in» в конце — часть фразового глагола («turn the lights on»)
            words = title.split()
            lead = {"the", "a", "an", "and", "or", "until", "every", "each", "over", "during",
                    "starting", "beginning", "towards", "toward"}
            trail = {"the", "a", "an", "and", "or", "until", "every", "each", "of", "with", "for"}
            while words and words[0].lower() in lead:
                words = words[1:]
            while len(words) > 1 and words[-1].lower() in trail:
                words = words[:-1]
            if len(words) == 1 and words[0].lower() in lead:
                words = []
            # регистр как в исходной фразе («lunch with Anna», «sync with ACME»)
            orig = {}
            for w in re.findall(r"[A-Za-z][A-Za-z']*", text):
                orig.setdefault(w.lower(), w)
            title = " ".join(orig.get(w.lower(), w) for w in words)
        return dt, title, dur, loc

    @staticmethod
    def _first_occurrence(rec, start):
        """Первая дата ≥ start, удовлетворяющая BYDAY/BYMONTHDAY правила (или сам start)."""
        plain = [d for d in (rec.by_day or []) if d in RRULE_DAYS]
        if rec.by_day and len(plain) != len(rec.by_day):
            return start  # позиционные коды («2FR») — не снапим
        d = start
        for _ in range(400):
            ok = True
            if plain:
                ok = RRULE_DAYS[d.weekday()] in plain
            if ok and rec.by_month_day:
                ok = d.day in [x for x in rec.by_month_day if x > 0]
            if ok:
                return d
            d += timedelta(days=1)
        return start

    _WITHIN_RE = re.compile(
        r"\bwithin\s+(?:the\s+)?(?:next\s+)?(?:(\d+|an?|one)\s+)?"
        r"(minutes?|mins?|hours?|hrs?|days?|day|weeks?|today)\b"
    )

    def _within(self, text, now):
        """«within 2 hours», «within an hour», «within the day/week» → дедлайн
        (паритет с RU «в течение 2 часов / дня / недели»)."""
        low = self._preprocess(text.lower())
        m = self._WITHIN_RE.search(low)
        if not m:
            return None
        raw, unit = m.group(1), m.group(2)
        n = 1 if raw in (None, "a", "an", "one") else int(raw)
        if unit == "today" or (unit.startswith("day") and raw is None):
            target = now.replace(hour=23, minute=59, second=0, microsecond=0)
        elif unit.startswith("week") and raw is None:
            target = (now + timedelta(days=6 - now.weekday())).replace(
                hour=23, minute=59, second=0, microsecond=0)
        elif unit.startswith("min"):
            target = now + timedelta(minutes=n)
        elif unit.startswith(("hour", "hr")):
            target = now + timedelta(hours=n)
        elif unit.startswith("day"):
            target = now + timedelta(days=n)
        else:
            target = now + timedelta(weeks=n)
        dt = DateTimeToken(type=DateTimeType.FIXED, date_from=now, date_to=target,
                           has_time=True, is_deadline=True, confidence=0.85)
        return dt, self._title(low, [m.span()]), None

    def _parse_impl(self, text, now):
        """→ (DateTimeToken | None, title, duration_minutes)."""
        low = self._preprocess(text.lower())
        if self._invalid_date(low):
            return (None, "", None)
        # Часовые пояса не поддерживаются — не парсим молча как локальное время.
        _TZ_ABBR = r"\b(utc|gmt|est|edt|cst|cdt|mst|mdt|pst|pdt|cet|cest|eet|bst|ist|jst|aest|msk)\b"
        _TZ_CITY = r"\b(?:moscow|london|new\s*york|tokyo|paris|berlin|beijing|sydney|dubai)\s+time\b"
        if (
            re.search(_TZ_ABBR, low)
            or re.search(r"(?:gmt|utc)\s*[+-]\s*\d", low)
            or re.search(_TZ_CITY, low)
        ):
            return (None, "", None)
        # last week/month/quarter/year + только время (без дня недели/числа) →
        # момент внутри периода не определяется → None (паритет с RU).
        if self._ambiguous_last_period(low):
            return (None, "", None)
        # относительные рабочие дни (in N business days / next business day /
        # by the first business day of next month)
        br = self._business_relative(low, now)
        if br is not None:
            dt, sp = br
            title = self._title(low, [sp])
            return dt, title, None
        text = low  # title строим от нормализованного текста (спаны совпадают)
        spans = []  # (start, end) consumed by date/time/recurrence machinery

        # first/last/Nth <weekday|business day|weekend|week> of the month (+ every)
        om = self._ordinal_of_month(low, now) or self._month_day_rel(low, now)
        if om is not None:
            dt, sp = om
            spans.append(sp)
            rest = low[: sp[0]] + (" " * (sp[1] - sp[0])) + low[sp[1] :]
            tr = self._time(rest, now)
            if tr is not None and not isinstance(tr[3], tuple):
                h, m, tsp, _ = tr
                spans.append(tsp)
                dt.date_from = dt.date_from.replace(hour=h, minute=m)
                dt.date_to = dt.date_from
                dt.has_time = True
                dt.all_day = False
            title = self._title(text, spans)
            return dt, title, None

        rec, rspan = self._recurrence(low, now)

        # deadline?
        dl = self._deadline(low, now)
        if dl is not None:
            dt, sp = dl
            spans.append(sp)
            title = self._title(text, spans)
            return dt, title, None

        # Детектим дату первой и маскируем её в рабочей строке, чтобы цифры
        # даты (ISO 2026-02-17) не съедались range/time-регэкспами.
        date_res = self._date(low, now)
        low2 = low
        date = None
        fuzzy = False
        is_period = False
        period_end = None
        if date_res is not None:
            date, dsp, fuzzy, is_period, period_end = date_res
            spans.append(dsp)
            low2 = low[: dsp[0]] + (" " * (dsp[1] - dsp[0])) + low[dsp[1] :]

        # ranges → explicit period (calendar)
        rng = self._range(low2, now)
        if rng is not None:
            dt, sp = rng
            spans.append(sp)
            if date is not None:
                # перенести диапазон на явную дату (длительность берём ДО мутации date_from)
                span = dt.date_to - dt.date_from
                dt.date_from = dt.date_from.replace(year=date.year, month=date.month, day=date.day)
                dt.date_to = dt.date_from + span
                # is_past для диапазона на явной дате (yesterday/last Friday from ... to ...)
                dt.is_past = dt.date_from < now
            if rec is not None:
                dt.recurrence = rec
                spans.append(rspan)
                spans.extend(getattr(rec, "_extra_spans", ()))
            title = self._title(text, spans)
            return dt, title, None

        time_res = self._time(low2, now)  # (hour, minute, span, has_time|daypart-tuple)
        dur = self._duration(low2)
        _dm = self._duration_match(low2)
        if _dm is not None:
            spans.append(_dm[1])  # «for an hour and a half» не должно попадать в title

        # относительный интервал + время суток: «in two weeks at 16:05» =
        # целевой день из «in N units», час из «at HH:MM». Должно идти ДО
        # общей time-ветки, иначе время перебьёт интервал (даст сегодня).
        if rec is None and date is None:
            rel_pre = self._relative(low2, now)
            if rel_pre is not None:
                rdt, rsp = rel_pre
                if not rdt.has_time and time_res is not None and not isinstance(
                    time_res[3], tuple
                ):
                    h, m, tsp, _ = time_res
                    rdt.date_from = rdt.date_from.replace(
                        hour=h, minute=m, second=0, microsecond=0
                    )
                    rdt.date_to = rdt.date_from
                    rdt.has_time = True
                    rdt.all_day = False
                    rdt.is_past = rdt.date_from < now
                    spans.append(rsp)
                    spans.append(tsp)
                    title = self._title(text, spans)
                    return rdt, title, dur

        if rec is not None:
            spans.append(rspan)
            spans.extend(getattr(rec, "_extra_spans", ()))
            base = now.replace(second=0, microsecond=0)
            # «every 15 minutes» — напоминание с временем (паритет с RU «каждые 15 минут»)
            has_time = rec.frequency in ("MINUTELY", "HOURLY")
            if time_res is not None:
                h, m, tsp, _ = time_res
                base = base.replace(hour=h, minute=m)
                has_time = True
                spans.append(tsp)
            start = self._recurrence_dtstart(rec, base, now, has_time)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=start,
                date_to=start,
                has_time=has_time,
                all_day=not has_time,
                recurrence=rec,
                confidence=0.9,
            )
            title = self._title(text, spans)
            return dt, title, None

        if time_res is not None:
            h, m, tsp, has_time = time_res
            spans.append(tsp)
            if isinstance(has_time, tuple):  # daypart period
                s, e = has_time
                base_day = date or now
                df = base_day.replace(hour=s % 24, minute=0, second=0, microsecond=0)
                dtt = base_day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                    hours=e
                )
                if date is None and self.nf and dtt <= now:
                    df += timedelta(days=1)
                    dtt += timedelta(days=1)
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=df,
                    date_to=dtt,
                    has_time=True,
                    fuzzy=True,
                    confidence=0.75,
                    is_past=dtt < now,  # «this morning» в 14:00, «last night» — прошло (паритет с RU)
                )
                title = self._title(text, spans)
                return dt, title, dur
            base = (date or now).replace(hour=h, minute=m, second=0, microsecond=0)
            if date is None and self.nf and isinstance(has_time, str) and has_time.startswith("bare"):
                raw = int(has_time[4:])
                if 1 <= raw <= 11:
                    # ближайшее будущее из raw и raw+12 (паритет с RU _resolve_hour_nearest)
                    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    now_min = now.replace(second=0, microsecond=0)
                    c1 = day0 + timedelta(hours=raw)
                    c2 = day0 + timedelta(hours=raw + 12)
                    if c1 >= now_min:
                        base = c1
                    elif c2 > now_min:
                        base = c2
                    else:
                        base = c1 + timedelta(days=1)
            # «today/tomorrow/Friday at midnight» = конец названного дня → 00:00 следующего
            if date is not None and "midnight" in low2[tsp[0]:tsp[1]]:
                base += timedelta(days=1)
            if date is None and self.nf and base < now:
                base += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=base,
                date_to=base,
                has_time=True,
                confidence=0.9,
                is_past=base < now,
            )
            title = self._title(text, spans)
            return dt, title, dur

        if date is not None:
            if is_period:
                dt = DateTimeToken(
                    type=DateTimeType.PERIOD,
                    date_from=date,
                    date_to=period_end,
                    has_time=False,
                    all_day=not fuzzy,
                    fuzzy=fuzzy,
                    confidence=0.8,
                )
                # is_past для fuzzy-периода: весь период уже прошёл (last week …)
                if period_end is not None and period_end < now:
                    dt.is_past = True
            else:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=date,
                    date_to=date.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    fuzzy=fuzzy,
                    confidence=0.9,
                    is_past=date.date() < now.date(),
                )
            title = self._title(text, spans)
            return dt, title, dur

        rel = self._relative(low2, now)
        if rel is not None:
            dt, sp = rel
            spans.append(sp)
            title = self._title(text, spans)
            return dt, title, dur

        return None, self._title(text, spans), None

    def _ambiguous_last_period(self, low):
        """True для 'last week/month/quarter/year' + только время (без дня недели
        и без числа). Момент внутри периода неоднозначен → None. Продуктивные
        случаи (last week on Thursday, last month on the 15th) и чистый период без
        времени (last week review …) сюда не попадают."""
        m = re.search(r"\blast\s+(week|month|quarter|year)\b", low)
        if not m:
            return False
        unit = m.group(1)
        has_time = bool(re.search(r"\bat\s+\d", low) or re.search(r"\b\d{1,2}:\d{2}\b", low))
        has_wd = bool(re.search(r"\b" + _WD + r"\b", low))
        has_daynum = bool(re.search(r"\b\d{1,2}(?:st|nd|rd|th)\b", low))
        if not (has_time or has_wd or has_daynum):
            return False
        if unit == "week" and has_wd:
            return False
        if unit == "month" and has_daynum and not has_time and not has_wd:
            return False
        return True

    def _add_business_days(self, base, n):
        t = base
        added = 0
        while added < n:
            t += timedelta(days=1)
            if self._is_working(t):
                added += 1
        return t

    def _business_relative(self, low, now):
        """Относительные рабочие дни:
        in N business days → +N рабочих дней (09:00); next business day → +1;
        by the first business day of next month → дедлайн на 1-й рабочий день;
        N business days before end of month → конец месяца − N рабочих дней."""
        # before_end_business: N business days before [the] end of [the] month
        m = re.search(
            r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(business\s+|working\s+)?days?"
            r"\s+before\s+(?:the\s+)?end\s+of\s+(?:the\s+)?month\b",
            low,
        )
        if m:
            business = bool(m.group(2))
            w = m.group(1)
            n = NUM_WORDS.get(w)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                year, month = now.year, now.month
                last = monthrange(year, month)[1]
                target = datetime(year, month, last, 0, 0)
                if target.date() < now.date():
                    month2 = month + 1
                    year2 = year + (1 if month2 > 12 else 0)
                    month2 = (month2 - 1) % 12 + 1
                    last2 = monthrange(year2, month2)[1]
                    target = datetime(year2, month2, last2, 0, 0)
                if business:
                    stepped = 0
                    while stepped < int(n):
                        target -= timedelta(days=1)
                        if self._is_working(target):
                            stepped += 1
                else:
                    target -= timedelta(days=int(n))
                # как в RU: точка в начале рабочего дня (09:00), а не дедлайн 23:59 —
                # «remind two business days before end of month» — это когда напомнить
                target = target.replace(hour=9, minute=0)
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=False,
                    all_day=True,
                    confidence=0.9,
                )
                return dt, m.span()
        # «two days before friday», «2 business days before july 20»,
        # «a week before the 20th» → дата минус N (рабочих) дней, 09:00 (паритет с RU «за N дней до …»)
        m = re.search(
            r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(business\s+|working\s+)?(days?|weeks?)\s+before\s+",
            low,
        )
        if m and not re.match(r"(?:the\s+)?end\s+of\b", low[m.end():]):
            dres = self._date(low[m.end():], now)
            if dres is not None and not dres[3]:
                w = m.group(1)
                n = 1 if w in ("a", "an", "one") else (NUM_WORDS.get(w) or int(w))
                base = dres[0].replace(hour=9, minute=0, second=0, microsecond=0)
                if m.group(3).startswith("week"):
                    base -= timedelta(weeks=int(n))
                elif m.group(2):
                    stepped = 0
                    while stepped < int(n):
                        base -= timedelta(days=1)
                        if self._is_working(base):
                            stepped += 1
                else:
                    base -= timedelta(days=int(n))
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD, date_from=base, date_to=base,
                    has_time=False, all_day=True, confidence=0.9,
                    is_past=base.date() < now.date(),
                )
                return dt, (m.start(), m.end() + dres[1][1])
        # by the first business day of next month
        m = re.search(
            r"\b(?:by|before|due)\s+the\s+first\s+business\s+day\s+of\s+next\s+month\b", low
        )
        if m:
            mo2 = now.month + 1
            y2 = now.year + (1 if mo2 > 12 else 0)
            mo2 = (mo2 - 1) % 12 + 1
            dim = monthrange(y2, mo2)[1]
            target = None
            for d in range(1, dim + 1):
                cand = datetime(y2, mo2, d)
                if self._is_working(cand):
                    target = cand
                    break
            if target is not None:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=target.replace(hour=23, minute=59),
                    has_time=False,
                    is_deadline=True,
                    confidence=0.85,
                )
                return dt, m.span()
        # in N business days
        m = re.search(
            r"\bin\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+business\s+days?\b",
            low,
        )
        if m:
            w = m.group(1)
            n = NUM_WORDS.get(w)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                base = now.replace(hour=9, minute=0, second=0, microsecond=0)
                target = self._add_business_days(base, int(n))
                dt = DateTimeToken(
                    type=DateTimeType.SPAN_FORWARD,
                    date_from=target,
                    date_to=target,
                    has_time=False,
                    all_day=True,
                    confidence=0.9,
                )
                return dt, m.span()
        # next business day
        m = re.search(r"\bnext\s+business\s+day\b", low)
        if m:
            base = now.replace(hour=9, minute=0, second=0, microsecond=0)
            target = self._add_business_days(base, 1)
            dt = DateTimeToken(
                type=DateTimeType.SPAN_FORWARD,
                date_from=target,
                date_to=target,
                has_time=False,
                all_day=True,
                confidence=0.9,
            )
            return dt, m.span()
        return None

    # ── date ────────────────────────────────────────────────────────────
    def _is_working(self, d):
        cal = getattr(self.config, "calendar", None)
        if cal is not None:
            return cal.is_working_day(d)
        return d.weekday() < 5

    def _ordinal_of_month(self, low, now):
        from calendar import monthrange

        # «second week of october», «the last week of october 2027» — N-я неделя
        # названного месяца: 1–7, 8–14, 15–21, 22–28, последние 7 дней (паритет с RU)
        m = re.search(
            r"\b(?:in\s+|during\s+)?(?:the\s+)?(first|second|third|fourth|last|"
            r"1st|2nd|3rd|4th|1th|2th|3th|4th)\s+week\s+of\s+(" + _MON + r")\.?(?:\s+(\d{4}))?\b",
            low,
        )
        if m:
            w = m.group(1)
            wn = -1 if w == "last" else (int(w[0]) if w[0].isdigit()
                                         else {"first": 1, "second": 2, "third": 3, "fourth": 4}[w])
            mon = MONTHS[m.group(2)]
            year = int(m.group(3)) if m.group(3) else now.year
            last = monthrange(year, mon)[1]
            if not m.group(3) and self.nf and datetime(year, mon, last, 23, 59) < now:
                year += 1
                last = monthrange(year, mon)[1]
            if wn == -1:
                s0, e0 = datetime(year, mon, last - 6), datetime(year, mon, last, 23, 59)
            else:
                s0 = datetime(year, mon, (wn - 1) * 7 + 1)
                e0 = datetime(year, mon, min(wn * 7, last), 23, 59)
            dtw = DateTimeToken(type=DateTimeType.PERIOD, date_from=s0, date_to=e0, has_time=False,
                                all_day=True, confidence=0.95)
            return dtw, m.span()

        ORD = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "1st": 1,
            "2nd": 2,
            "3rd": 3,
            "4th": 4,
            "5th": 5,
            "last": -1,
            "penultimate": -2,
        }
        ord_alt = r"first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|penultimate|last|(?:second|next)[-\s]to[-\s]last"
        kind_alt = r"business\s+day|weekday|weekend|week|" + _WD
        # Форма с конкретным месяцем: «first Tuesday of [every] January» → YEARLY.
        fixed_month = None
        m = re.search(
            r"\b(every\s+)?(" + ord_alt + r")\s+(" + kind_alt + r")"
            r"\s+of\s+(?:every\s+)?(" + _MON + r")\b",
            low,
        )
        if m:
            fixed_month = MONTHS[m.group(4)]
            # «of every January» тоже означает повторение, даже без ведущего every
            if re.search(r"of\s+every\s+" + _MON, low):
                every_from_month = True
            else:
                every_from_month = False
        else:
            m = re.search(
                r"\b(every\s+)?(" + ord_alt + r")\s+(" + kind_alt + r")\s+of\s+the\s+month\b",
                low,
            )
            every_from_month = False
        if not m:
            return None
        every = bool(m.group(1)) or every_from_month
        ow = m.group(2)
        pos = -2 if "to" in ow else ORD.get(ow)
        if pos is None:
            return None
        kind_raw = m.group(3)
        wd = None
        if re.fullmatch(_WD, kind_raw):
            kind = "weekday_name"
            wd = WEEKDAYS[kind_raw]
        elif kind_raw == "weekend":
            kind = "weekend"
        elif kind_raw == "week":
            kind = "week"
        else:
            kind = "business"

        def compute(year, month):
            dim = monthrange(year, month)[1]
            if kind == "week":
                if pos == 1:
                    return datetime(year, month, 1), datetime(year, month, min(7, dim), 23, 59)
                return datetime(year, month, max(1, dim - 6)), datetime(year, month, dim, 23, 59)
            if kind == "weekday_name":
                days = [d for d in range(1, dim + 1) if datetime(year, month, d).weekday() == wd]
            elif kind == "business":
                days = [d for d in range(1, dim + 1) if self._is_working(datetime(year, month, d))]
            else:  # weekend → субботы
                days = [d for d in range(1, dim + 1) if datetime(year, month, d).weekday() == 5]
            idx = pos - 1 if pos > 0 else len(days) + pos
            if not (0 <= idx < len(days)):
                return None, None
            s = datetime(year, month, days[idx])
            e = s.replace(hour=23, minute=59)
            if kind == "weekend":
                e = (s + timedelta(days=1)).replace(hour=23, minute=59)
            return s, e

        if fixed_month is not None:
            # конкретный месяц: ищем ближайший год, где дата ещё не прошла
            y = now.year
            s, e = compute(y, fixed_month)
            if s is None or s.date() < now.date():
                s, e = compute(y + 1, fixed_month)
            if s is None:
                return None
        else:
            y, mo = now.year, now.month
            s, e = compute(y, mo)
            if s is None or s.date() < now.date():
                mo2 = mo + 1
                y2 = y + (1 if mo2 > 12 else 0)
                mo2 = (mo2 - 1) % 12 + 1
                s2, e2 = compute(y2, mo2)
                if s2 is not None:
                    s, e = s2, e2
            if s is None:
                return None
        rec = None
        if every:
            freq = "YEARLY" if fixed_month is not None else "MONTHLY"
            bm = [fixed_month] if fixed_month is not None else None
            if kind == "weekday_name":
                rec = RecurrenceRule(
                    frequency=freq, by_day=[f"{pos}{RRULE_DAYS[wd]}"], by_month=bm
                )
            elif kind == "business":
                rec = RecurrenceRule(
                    frequency=freq, by_day=["MO", "TU", "WE", "TH", "FR"],
                    by_set_pos=pos, by_month=bm,
                )
            elif kind == "weekend":
                rec = RecurrenceRule(
                    frequency=freq, by_day=["SA", "SU"], by_set_pos=pos, by_month=bm
                )
            else:
                rec = RecurrenceRule(frequency=freq, by_month=bm)
        is_range = kind in ("weekend", "week")
        dt = DateTimeToken(
            type=DateTimeType.PERIOD if is_range else DateTimeType.FIXED,
            date_from=s,
            date_to=e if is_range else s.replace(hour=23, minute=59),
            has_time=False,
            all_day=True,
            recurrence=rec,
            confidence=0.9,
        )
        if is_range:
            dt.is_explicit_range = True
        return dt, m.span()

    def _ordinal_of_month_disabled(self):
        pass

    def _month_day_rel(self, low, now):
        """first <weekday|business day> after the Nth;
        last <weekday|business day> before the end of the month."""
        from calendar import monthrange

        kind_alt = r"business\s+day|weekday|" + _WD

        def kind_of(raw):
            if re.fullmatch(_WD, raw):
                return ("weekday", WEEKDAYS[raw])
            return ("business", None)

        # after the Nth
        m = re.search(
            r"\b(?:first\s+)?(" + kind_alt + r")\s+after\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", low
        )
        if m:
            kind, wd = kind_of(m.group(1))
            n = int(m.group(2))
            if 1 <= n <= 31:

                def comp(y, mo):
                    dim = monthrange(y, mo)[1]
                    for d in range(n + 1, dim + 1):
                        dt = datetime(y, mo, d)
                        if (kind == "weekday" and dt.weekday() == wd) or (
                            kind == "business" and self._is_working(dt)
                        ):
                            return dt
                    return None

                t = comp(now.year, now.month)
                if t is None or t.date() < now.date():
                    mo2 = now.month + 1
                    y2 = now.year + (1 if mo2 > 12 else 0)
                    mo2 = (mo2 - 1) % 12 + 1
                    t = comp(y2, mo2) or t
                if t is not None:
                    dt = DateTimeToken(
                        type=DateTimeType.FIXED,
                        date_from=t,
                        date_to=t.replace(hour=23, minute=59),
                        has_time=False,
                        all_day=True,
                        confidence=0.9,
                    )
                    return dt, m.span()

        # before the end of the month
        m = re.search(
            r"\b(?:last\s+)?(" + kind_alt + r")\s+before\s+the\s+end\s+of\s+the\s+month\b", low
        )
        if m:
            kind, wd = kind_of(m.group(1))

            def comp(y, mo):
                dim = monthrange(y, mo)[1]
                for d in range(dim, 0, -1):
                    dt = datetime(y, mo, d)
                    if (kind == "weekday" and dt.weekday() == wd) or (
                        kind == "business" and self._is_working(dt)
                    ):
                        return dt
                return None

            t = comp(now.year, now.month)
            if t is None or t.date() < now.date():
                mo2 = now.month + 1
                y2 = now.year + (1 if mo2 > 12 else 0)
                mo2 = (mo2 - 1) % 12 + 1
                t = comp(y2, mo2) or t
            if t is not None:
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=t,
                    date_to=t.replace(hour=23, minute=59),
                    has_time=False,
                    all_day=True,
                    confidence=0.9,
                )
                return dt, m.span()
        return None

    def _date(self, low, now):
        # Диапазон дат «from MONTH D to [MONTH] D» → период (before N-units-ago,
        # иначе _range растащит «10 to 12» как время). Должно идти первым.
        dr = self._date_range(low, now)
        if dr is not None:
            return dr
        # кварталы: «in Q1», «in the first quarter», «in the 4th quarter of 2027»,
        # «next/this/last quarter» (паритет с RU «в первом квартале»)
        m = re.search(
            r"\b(?:in\s+|during\s+)?(?:the\s+)?(?:q([1-4])|(first|second|third|fourth|[1-4](?:st|nd|rd|th))"
            r"\s+quarter)(?:\s+(?:of\s+)?((?:19|20)\d{2}))?\b", low
        )
        if m:
            # предобработка превращает «first» в «1th» — берём цифру, если она есть
            words = {"first": 1, "second": 2, "third": 3, "fourth": 4}
            g2 = m.group(2)
            qn = int(m.group(1)) if m.group(1) else (int(g2[0]) if g2[0].isdigit() else words[g2])
            year = int(m.group(3)) if m.group(3) else now.year
            e = datetime(year, qn * 3, monthrange(year, qn * 3)[1], 23, 59)
            if not m.group(3) and self.nf and e < now:
                year += 1
                e = datetime(year, qn * 3, monthrange(year, qn * 3)[1], 23, 59)
            return datetime(year, qn * 3 - 2, 1), m.span(), True, True, e
        m = re.search(r"\b(?:in\s+|during\s+)?(this|next|last)\s+quarter\b", low)
        if m and not re.search(r"\b(?:beginning|start|middle|mid|end)\s+of\s+(?:the\s+)?(?:this|next|last)\s+quarter", low):
            off = {"this": 0, "next": 1, "last": -1}[m.group(1)]
            s, e = self._period_bounds("quarter", self._shift_ref("quarter", now, off))
            return s, m.span(), True, True, e
        # «in 3 weeks on monday», «monday in 2 weeks» — день недели в той неделе,
        # куда попадает «через N недель» (паритет с RU «через 3 недели в понедельник»)
        m = re.search(
            r"\bin\s+(\d+|a|an|one)\s+weeks?\s+(?:on\s+)?(" + _WD + r")\b", low
        ) or re.search(r"\b(?:on\s+)?(" + _WD + r")\s+in\s+(\d+|a|an|one)\s+weeks?\b", low)
        if m:
            g1, g2 = m.group(1), m.group(2)
            num, wdn = (g1, g2) if g2 in WEEKDAYS else (g2, g1)
            k = 1 if num in ("a", "an", "one") else int(num)
            base = (now + timedelta(weeks=k)).replace(hour=0, minute=0, second=0, microsecond=0)
            d = base - timedelta(days=base.weekday()) + timedelta(days=WEEKDAYS[wdn])
            return d, m.span(), False, False, None
        # «two weeks from friday» — ближайшая пятница + N недель; «friday after next»
        m = re.search(r"\b(\d+|a|an|one)\s+weeks?\s+from\s+(" + _WD + r")\b", low)
        if m:
            k = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
            delta = (WEEKDAYS[m.group(2)] - now.weekday()) % 7 or 7
            d = (now + timedelta(days=delta + 7 * k)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        m = re.search(r"\b(?:the\s+)?(" + _WD + r")\s+after\s+next\b", low)
        if m:
            delta = (WEEKDAYS[m.group(1)] - now.weekday()) % 7 or 7
            d = (now + timedelta(days=delta + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        m = re.search(r"\b(?:the\s+)?week\s+after\s+next\b", low)
        if m:
            s0, e0 = self._period_bounds("week", now + timedelta(weeks=2))
            return s0, m.span(), True, True, e0
        # N units ago → прошлая дата (three days ago, two weeks ago, a month ago)
        m = re.search(
            r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(day|days|week|weeks|month|months|year|years)\s+ago\b",
            low,
        )
        if m:
            w = m.group(1)
            n = 1 if w in ("a", "an") else NUM_WORDS.get(w, None)
            if n is None:
                try:
                    n = int(w)
                except ValueError:
                    n = None
            if n is not None:
                unit = m.group(2)
                base = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if unit.startswith("day"):
                    d = base - timedelta(days=n)
                elif unit.startswith("week"):
                    d = base - timedelta(weeks=n)
                elif unit.startswith("month"):
                    d = self._add_months(base, -n)
                else:
                    d = self._add_months(base, -n * 12)
                return d, m.span(), False, False, None
        # day after tomorrow
        m = re.search(r"\b(?:the\s+)?day after tomorrow\b", low)
        if m:
            d = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        m = re.search(r"\btomorrow\b", low)
        if m:
            return (
                (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        m = re.search(r"\b(?:the\s+)?day\s+before\s+yesterday\b", low)
        if m:
            return (
                (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(), False, False, None,
            )
        m = re.search(r"\byesterday\b", low)
        if m:
            return (
                (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        m = re.search(r"\btoday\b", low)
        if m:
            return (
                now.replace(hour=0, minute=0, second=0, microsecond=0),
                m.span(),
                False,
                False,
                None,
            )
        # диапазон дней недели: «from monday to wednesday», «mon-fri»
        # (паритет с RU «с понедельника по среду»)
        if not re.search(r"\b(?:every|each)\b", low):
            m = re.search(
                r"\b(?:from\s+)?(" + _WD + r")\s*(?:\bto\b|\btill\b|\buntil\b|\bthrough\b|\bthru\b|-|\u2013)\s*("
                + _WD + r")\b",
                low,
            )
            if m:
                w1, w2 = WEEKDAYS[m.group(1)], WEEKDAYS[m.group(2)]
                delta = (w1 - now.weekday()) % 7
                if delta == 0:
                    delta = 7 if self.nf else 0
                s = (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
                e = (s + timedelta(days=(w2 - w1) % 7)).replace(hour=23, minute=59)
                return s, m.span(), False, True, e
            # выходные: «this/next/last weekend», «on/over the weekend»
            m = re.search(
                r"\b(?:(this|next|last|coming)\s+(?:coming\s+)?weekend|(?:on|over|at|during)\s+the\s+weekend)\b",
                low,
            )
            if m:
                wd = now.weekday()
                sat = (now + timedelta(days=(5 - wd) if wd <= 5 else -1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                sat += timedelta(weeks={"next": 1, "last": -1}.get(m.group(1), 0))
                sun = (sat + timedelta(days=1)).replace(hour=23, minute=59)
                return sat, m.span(), False, True, sun
        # weekday inside a named calendar week (Mon–Sun):
        # «next week on Wednesday», «next week Wednesday», «on Wednesday next week»,
        # «Wednesday of next week», «last week on Thursday».
        m = re.search(
            r"\b(next|this|last)\s+week(?:\s*,)?\s+(?:on\s+)?(" + _WD + r")\b", low
        ) or re.search(
            r"\b(?:on\s+)?(" + _WD + r")\s+(?:of\s+)?(next|this|last)\s+week\b", low
        )
        if m:
            g1, g2 = m.group(1), m.group(2)
            mod, wdn = (g1, g2) if g1 in ("next", "this", "last") else (g2, g1)
            off = {"next": 1, "this": 0, "last": -1}[mod]
            mon = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            d = mon + timedelta(days=7 * off + WEEKDAYS[wdn])
            return d, m.span(), False, False, None
        # next/this/last week  («early/mid/late next week» — ниже, в частях периода)
        m = re.search(r"\b(?<!early )(?<!mid )(?<!late )(?<!of )(?<!of the )(next|this|last)\s+week\b", low)
        if m:
            ref = now + timedelta(weeks={"next": 1, "this": 0, "last": -1}[m.group(1)])
            mon = (ref - timedelta(days=ref.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sun = (mon + timedelta(days=6)).replace(hour=23, minute=59)
            return mon, m.span(), True, True, sun
        # [next|this|last] [coming] weekday
        # «coming» (this coming Saturday / coming Friday) = ближайший день, как this.
        m = re.search(r"\b(next|this|last)?\s*(?:coming\s+)?(" + _WD + r")\b", low)
        if m and m.group(2):
            wd = WEEKDAYS[m.group(2)]
            mod = m.group(1)
            if mod == "last":
                delta = -(((now.weekday() - wd) % 7) or 7)
            elif mod == "next":
                # Конвенция (как в RU): «next X» = ближайший X (включая сегодня) + неделя.
                # next Thursday в среду → чт следующей недели, НЕ завтра.
                delta = (wd - now.weekday()) % 7 + 7
            else:  # this / none → nearest upcoming (or today)
                delta = (wd - now.weekday()) % 7
                if delta == 0 and mod is None:
                    delta = 7 if self.nf else 0
            d = (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
            return d, m.span(), False, False, None
        # month-name forms
        d = self._month_date(low, now)
        if d is not None:
            return d
        # numeric MM/DD[/YYYY] or ISO
        d = self._numeric_date(low, now)
        if d is not None:
            return d
        # «on the 5th», «the 20th» — ближайшее такое число (паритет с RU «5 числа»)
        m = re.search(
            r"\b(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)\b"
            r"(?!\s+(?:of\s+)?(?:" + _MON + r"|week|month|year|day|business|" + _WD + r"))",
            low,
        )
        if m and 1 <= int(m.group(1)) <= 31:
            day = int(m.group(1))
            y, mo = now.year, now.month
            for _ in range(13):
                d = self._safe(y, mo, day)
                if d is not None and (d.date() >= now.date() or not self.nf):
                    return d, m.span(), False, False, None
                mo += 1
                if mo > 12:
                    mo, y = 1, y + 1
        # сезоны (in spring/…): после явных дат, чтобы «spring» в названии
        # не перебивал конкретную дату (March twenty first … spring presentation)
        sea = self._season(low, now)
        if sea is not None:
            return sea
        # end/beginning/middle of week/month/year (fuzzy period, no "by")
        m = re.search(
            r"\b(?:at\s+the\s+)?(beginning|start|middle|mid|end)\s+of\s+(?:the\s+)?(?:(this|next|last)\s+)?(week|month|year|quarter)\b",
            low,
        )
        if m:
            part = {
                "beginning": "start",
                "start": "start",
                "middle": "middle",
                "mid": "middle",
                "end": "end",
            }[m.group(1)]
            unit = m.group(3)
            off = {"next": 1, "last": -1}.get(m.group(2), 0)
            s_full, e_full = self._period_bounds(unit, self._shift_ref(unit, now, off))
            s, e = self._part_window(unit, part, s_full, e_full)
            # ближайшее будущее и для части периода («beginning of the month» 22-го →
            # начало следующего месяца); при явных this/next/last — как сказано
            if self.nf and m.group(2) is None and e < now:
                s_full, e_full = self._period_bounds(unit, self._shift_ref(unit, e_full, 1))
                s, e = self._part_window(unit, part, s_full, e_full)
            return s, m.span(), True, True, e
        # «last day of the month», «first day of next month» (паритет с RU)
        m = re.search(
            r"\b(?:the\s+)?(first|1st|1th|last)\s+day\s+of\s+(?:the\s+)?(?:(this|next)\s+)?month\b", low
        )
        if m:
            ref = self._shift_ref("month", now, 1 if m.group(2) == "next" else 0)
            s_full, e_full = self._period_bounds("month", ref)
            d = s_full if m.group(1) in ("first", "1st", "1th") else e_full.replace(hour=0, minute=0)
            if self.nf and d.date() < now.date() and not m.group(2):
                d = self._period_bounds("month", self._shift_ref("month", now, 1))[0]
            return d, m.span(), False, False, None
        # «early/mid/late next week|month|year»
        m = re.search(r"\b(early|mid|late)\s+(this|next|last)\s+(week|month|year)\b", low)
        if m:
            part = {"early": "start", "mid": "middle", "late": "end"}[m.group(1)]
            unit = m.group(3)
            off = {"this": 0, "next": 1, "last": -1}[m.group(2)]
            s_full, e_full = self._period_bounds(unit, self._shift_ref(unit, now, off))
            s, e = self._part_window(unit, part, s_full, e_full)
            return s, m.span(), True, True, e
        # «(in) this/next/last month|year» (паритет с RU «в следующем месяце»)
        m = re.search(r"\b(?:in\s+|during\s+)?(this|next|last)\s+(month|year)\b", low)
        if m:
            off = {"this": 0, "next": 1, "last": -1}[m.group(1)]
            s, e = self._period_bounds(m.group(2), self._shift_ref(m.group(2), now, off))
            return s, m.span(), True, True, e
        # месяц без дня: «in october», «in december 2026», «mid october», «late may»
        parts = r"(early|beginning\s+of|start\s+of|mid|middle\s+of|late|end\s+of)"
        m = (
            re.search(r"\b(?:in|during|for)\s+(?:" + parts + r"\s+)?(" + _MON + r")\.?(?:\s+(\d{4}))?\b", low)
            or re.search(r"\b" + parts + r"\s+(" + _MON + r")\.?(?:\s+(\d{4}))?\b", low)
            or re.search(r"\b()(" + _MON + r")\.?\s+(\d{4})\b", low)
        )
        if m:
            mon = MONTHS[m.group(2)]
            if m.group(3):
                year = int(m.group(3))
            else:
                year = now.year + (1 if (self.nf and mon < now.month) else 0)
            s = datetime(year, mon, 1)
            e = datetime(year, mon, monthrange(year, mon)[1], 23, 59)
            if m.group(1):
                p = m.group(1).split()[0]
                part = {"early": "start", "beginning": "start", "start": "start",
                        "mid": "middle", "middle": "middle", "late": "end", "end": "end"}[p]
                s, e = self._part_window("month", part, s, e)
            return s, m.span(), True, True, e
        # год: «in 2027»
        m = re.search(
            r"\b(?:in|during)\s+((?:19|20)\d{2})\b(?!\s*(?:sec|min|hour|hr|day|week|month|year))", low
        )
        if m:
            y = int(m.group(1))
            return datetime(y, 1, 1), m.span(), True, True, datetime(y, 12, 31, 23, 59)
        return None

    def _shift_ref(self, unit, now, off):
        """Опорная дата для this/next/last периода."""
        if unit == "week":
            return now + timedelta(weeks=off)
        if unit == "month":
            return self._add_months(now.replace(day=1), off)
        if unit == "quarter":
            return self._add_months(now.replace(day=1), 3 * off)
        return now.replace(year=now.year + off, month=1, day=1)

    def _date_range(self, low, now):
        """from MONTH D to [MONTH] D / from D to D MONTH → период дат.
        Конец в прошлом относительно старта → +год (december 25 to january 5)."""
        # from MONTH D to MONTH D
        m = re.search(
            r"\b(?:from\s+)?(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
            r"\s*(?:\bto\b|\btill\b|\buntil\b|\bthrough\b|\bthru\b|-|\u2013|\u2014)\s*"
            r"(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            low,
        )
        if m:
            mo1, d1 = MONTHS[m.group(1)], int(m.group(2))
            mo2, d2 = MONTHS[m.group(3)], int(m.group(4))
        else:
            # from MONTH D to D (второй день тот же месяц)
            m = re.search(
                r"\bfrom\s+(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
                r"\s+to\s+(\d{1,2})(?:st|nd|rd|th)?\b",
                low,
            )
            if m:
                mo1 = mo2 = MONTHS[m.group(1)]
                d1, d2 = int(m.group(2)), int(m.group(3))
            else:
                # from D to D MONTH (месяц в конце)
                m = re.search(
                    r"\bfrom\s+(\d{1,2})(?:st|nd|rd|th)?\s+to\s+"
                    r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MON + r")\.?\b",
                    low,
                )
                if not m:
                    return None
                mo1 = mo2 = MONTHS[m.group(3)]
                d1, d2 = int(m.group(1)), int(m.group(2))
        year = now.year
        start = self._safe(year, mo1, d1)
        if start is None:
            return None
        end_year = year + 1 if mo2 < mo1 else year
        end = self._safe(end_year, mo2, d2)
        if end is None:
            return None
        # весь период в прошлом → перенос на следующий год (оба конца)
        if self.nf and start.date() < now.date():
            start2 = self._safe(year + 1, mo1, d1)
            end2 = self._safe(year + 1 + (1 if mo2 < mo1 else 0), mo2, d2)
            if start2 is not None and end2 is not None:
                start, end = start2, end2
        end = end.replace(hour=23, minute=59)
        return start, m.span(), False, True, end

    def _month_date(self, low, now):
        # Feb 17 [, 2026] / Feb 17th
        m = re.search(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", low)
        if not m:
            # 17 Feb [2026] / 3rd of March
            m = re.search(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MON + r")\.?(?:,?\s+(\d{4}))?\b",
                low,
            )
            if not m:
                return None
            day = int(m.group(1))
            mon = MONTHS[m.group(2)]
            yr = m.group(3)
        else:
            mon = MONTHS[m.group(1)]
            day = int(m.group(2))
            yr = m.group(3)
        year = int(yr) if yr else now.year
        d = self._safe(year, mon, day)
        if d is None:
            return None
        if not yr and self.nf and d.date() < now.date():
            d2 = self._safe(year + 1, mon, day)
            if d2 is not None:
                d = d2
        return d, m.span(), False, False, None

    def _numeric_date(self, low, now):
        m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", low)
        if m:
            d = self._safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d is not None:
                return d, m.span(), False, False, None
        # MM/DD[/YYYY] (US month-first)
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
        if m:
            mo = int(m.group(1))
            day = int(m.group(2))
            yr = m.group(3)
            # 25/09: первое число не может быть месяцем → DD/MM (европейский
            # порядок), а не молча потерянная дата. 3/4 остаётся US MM/DD.
            if mo > 12 and 1 <= day <= 12:
                mo, day = day, mo
            if 1 <= mo <= 12:
                year = int(yr) if yr else now.year
                if year < 100:
                    year += 2000
                d = self._safe(year, mo, day)
                if d is not None:
                    if not yr and self.nf and d.date() < now.date():
                        d2 = self._safe(year + 1, mo, day)
                        if d2 is not None:
                            d = d2
                    return d, m.span(), False, False, None
        return None

    _SEASONS = {
        "spring": (3, 1, 5, 31),
        "summer": (6, 1, 8, 31),
        "fall": (9, 1, 11, 30),
        "autumn": (9, 1, 11, 30),
        "winter": (12, 1, 2, 28),
    }

    def _season(self, low, now):
        """«in spring/summer/fall/autumn/winter» → fuzzy-период сезона (паритет с RU).
        Winter пересекает год. Прошедший сезон → следующий год (nearest-future)."""
        m = re.search(r"\b(?:in\s+)?(?:(last|this|next)\s+)?(spring|summer|fall|autumn|winter)\b", low)
        if not m:
            return None
        mod = m.group(1)
        res = self._season_core(m.group(2), now)
        s0, e0 = res
        if mod == "last":  # «last winter» — сезон годом раньше ближайшего (паритет с RU «прошлой зимой»)
            s0 = s0.replace(year=s0.year - 1)
            e0 = e0.replace(year=e0.year - 1, day=monthrange(e0.year - 1, e0.month)[1] if e0.month == 2 else e0.day)
        elif mod == "next" and s0 <= now:
            s0, e0 = s0.replace(year=s0.year + 1), e0.replace(year=e0.year + 1)
        return s0, m.span(), True, True, e0

    def _season_core(self, name, now):
        sm, sd, em, ed = self._SEASONS[name]
        y = now.year
        winter = sm == 12
        if winter and now.month <= 2:
            y -= 1  # in Jan–Feb «winter» is the current one (started in December)
        ey = y + 1 if winter else y
        if winter:
            ed = monthrange(ey, 2)[1]  # Feb 29 in leap years
        s = datetime(y, sm, sd)
        e = datetime(ey, em, ed, 23, 59)
        if self.nf and e < now:
            ey2 = ey + 1
            ed2 = monthrange(ey2, 2)[1] if winter else ed
            s = datetime(y + 1, sm, sd)
            e = datetime(ey2, em, ed2, 23, 59)
        return s, e

    # ── time ────────────────────────────────────────────────────────────
    def _time(self, low, now):
        """Время + поправка на часть суток для любой ветки без am/pm:
        «tonight at 8:30» → 20:30, «this evening at 7:30» → 19:30."""
        r = self._time_raw(low, now)
        if r is None or isinstance(r[3], tuple):
            return r
        dp = re.search(r"\b(?:in\s+the\s+)?(towardsevening|morning|afternoon|evening|night|tonight)\b", low)
        if dp and r[0] < 12 and not re.search(r"am|pm|noon|midnight", low[r[2][0]:r[2][1]]):
            return (self._daypart_hour(r[0], dp.group(1)), r[1], r[2], True)
        return r

    def _time_raw(self, low, now):
        # «at» входит в спан, иначе в title остаётся висящее «at»
        m = re.search(r"\b(?:at\s+)?noon\b", low)
        if m:
            return (12, 0, m.span(), True)
        m = re.search(r"\b(?:at\s+)?midnight\b", low)
        if m:
            return (0, 0, m.span(), True)
        # daypart
        m = re.search(r"\b(?:in\s+the\s+)?(towardsevening|morning|afternoon|evening|night|tonight)\b", low)
        dp = m
        # at H[:MM][ ]?[am|pm]
        m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
        if m:
            h = int(m.group(1))
            mm = int(m.group(2) or 0)
            ap = m.group(3)
            if not (1 <= h <= 12 and 0 <= mm <= 59):
                return None  # «at 25pm» — не время; не сваливаемся в слабые паттерны
            if ap == "pm" and h != 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            return (h, mm, m.span(), True)
        # at H:MM (24h)
        m = re.search(r"\bat\s+(\d{1,2}):(\d{2})\b", low)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= h <= 23 and 0 <= mm <= 59):
                return None  # «at 12:60» — опечатка; честнее None, чем 12:00
            return (h, mm, m.span(), True)
        # standalone H:MM
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", low)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= h <= 23 and 0 <= mm <= 59):
                return None
            # «tonight at 8:30», «in the evening at 7:30» — часть суток задаёт PM
            if dp and h < 12:
                h = self._daypart_hour(h, dp.group(1))
            return (h, mm, m.span(), True)
        # at H (bare hour) — only with explicit "at"
        m = re.search(r"\bat\s+(\d{1,2})\b", low)
        if m:
            h = int(m.group(1))
            if not (0 <= h <= 23):
                return None
            raw = h
            if dp:
                # «every day in the morning at 7» → 07:00, «evening at 9» → 21:00
                return (self._daypart_hour(raw, dp.group(1)), 0, m.span(), True)
            if self.nf and 1 <= h <= 7:
                h += 12
            # "bare<raw>" — голый час без am/pm: при отсутствии даты действует
            # smart-hour (как в RU и в README): «at 10» в 14:00 → 22:00 сегодня.
            return (h, 0, m.span(), "bare%d" % raw)
        if dp:
            s, e = DAYPARTS[dp.group(1)]
            return (s, 0, dp.span(), (s, e))
        return None

    # ── ranges ──────────────────────────────────────────────────────────
    @staticmethod
    def _daypart_hour(h, part):
        """Час с учётом части суток (паритет с RU «в 7 утра / вечера / ночи»)."""
        if part == "morning":
            return 0 if h == 12 else h
        if part in ("afternoon", "evening", "tonight", "towardsevening"):
            return h + 12 if 1 <= h <= 11 else h
        if part == "night":
            if h == 12:
                return 0
            return h + 12 if 7 <= h <= 11 else h
        return h

    def _range(self, low, now):
        # between H and H
        m = re.search(
            r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            low,
        )
        if not m:
            # from H to H / H to H / H-H with am/pm
            m = re.search(
                r"\b(?:from\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-|–)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                low,
            )
            if not m:
                return None
        h1 = int(m.group(1))
        m1 = int(m.group(2) or 0)
        ap1 = m.group(3)
        h2 = int(m.group(4))
        m2 = int(m.group(5) or 0)
        ap2 = m.group(6)
        # «from 3 to 4:30pm» — pm конца распространяется на начало, если так логичнее
        if ap1 is None and ap2 is not None and self._ap(h1, ap2) <= self._ap(int(m.group(4)), ap2):
            ap1 = ap2
        h1 = self._ap(h1, ap1)
        h2 = self._ap(h2, ap2)
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23 and 0 <= m1 <= 59 and 0 <= m2 <= 59):
            return None
        # «9 to 5» (ранний старт) без am/pm: конец < старта и ≤7 → PM (17:00).
        # Поздний старт (≥18), напр. «23 to 1» → НЕ PM, а овернайт (+1 день ниже).
        if ap1 is None and ap2 is None and h2 < h1 and h2 <= 7 and h1 < 18:
            h2 += 12
        # если конец без am/pm, а начало pm и конец меньше — тянем в тот же смысл
        s = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        e = now.replace(hour=h2 % 24, minute=m2, second=0, microsecond=0)
        if self.nf and s < now:
            s += timedelta(days=1)
            e += timedelta(days=1)
        if e <= s:
            e += timedelta(days=1)
        dt = DateTimeToken(
            type=DateTimeType.PERIOD, date_from=s, date_to=e, has_time=True, confidence=0.9
        )
        dt.is_explicit_range = True
        return dt, m.span()

    def _ap(self, h, ap):
        if ap == "pm" and h != 12:
            return h + 12
        if ap == "am" and h == 12:
            return 0
        return h

    # ── recurrence ──────────────────────────────────────────────────────
    def _recurrence(self, low, now):
        rec, span = self._recurrence_base(low, now)
        if rec is None:
            return None, None
        span = self._apply_recur_mods(rec, low, now, span)
        # «every 30 minutes … on weekdays» — частое правило с днями недели (паритет с RU)
        if rec.frequency == "WEEKLY" and rec.by_day and rec.interval == 1:
            mf = re.search(r"\bevery\s+(\d+)\s+(minutes?|mins?|hours?|hrs?)\b", low)
            if mf:
                freq = "MINUTELY" if mf.group(2).startswith("min") else "HOURLY"
                fr = RecurrenceRule(frequency=freq, interval=int(mf.group(1)), by_day=list(rec.by_day))
                fr._extra_spans = [span] + list(getattr(rec, "_extra_spans", []))
                return fr, mf.span()
        return rec, span

    def _apply_recur_mods(self, rec, low, now, span):
        s0, e0 = span
        # участки модификаторов храним отдельно: склейка «every …» с «… 5 times»
        # в один отрезок съедала название между ними («every monday at 10 call 5 times»)
        extra = []
        # UNTIL: end of <period-word> | end of <month-name> | <date>
        m = re.search(
            r"\buntil\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+|next\s+)?(day|week|month|year|quarter)\b",
            low,
        )
        if m:
            _, e_full = self._period_bounds(m.group(1), now)
            rec.until = e_full
            extra.append((m.start(), m.end()))
        else:
            m = re.search(r"\buntil\s+(?:the\s+)?end\s+of\s+(" + _MON + r")\b", low)
            if m:
                mon = MONTHS[m.group(1)]
                year = now.year
                last = monthrange(year, mon)[1]
                e_full = datetime(year, mon, last, 23, 59)
                if self.nf and e_full < now:
                    last = monthrange(year + 1, mon)[1]
                    e_full = datetime(year + 1, mon, last, 23, 59)
                rec.until = e_full
                extra.append((m.start(), m.end()))
            else:
                # until <MONTH> без дня («until December») → конец этого месяца
                mm = re.search(r"\buntil\s+(" + _MON + r")\b(?!\s+\d)", low)
                if mm:
                    mon = MONTHS[mm.group(1)]
                    year = now.year
                    last = monthrange(year, mon)[1]
                    e_full = datetime(year, mon, last, 23, 59)
                    if self.nf and e_full < now:
                        last = monthrange(year + 1, mon)[1]
                        e_full = datetime(year + 1, mon, last, 23, 59)
                    rec.until = e_full
                    extra.append((mm.start(), mm.end()))
                else:
                    m = re.search(r"\buntil\s+", low)
                    if m:
                        dres = self._date(low[m.end() :], now)
                        if dres is not None:
                            rec.until = dres[0].replace(hour=23, minute=59)
                            extra.append((m.start(), m.end() + dres[1][1]))
        # COUNT: "N times"
        m = re.search(r"\b(\d+)\s+(?:times|occurrences|occurrence)\b", low)
        if m:
            rec.count = int(m.group(1))
            extra.append((m.start(), m.end()))
        # EXCEPT: consume ТОЛЬКО перечисление дней/выходных после except (не title)
        m = re.search(r"\b(?:except|excluding|but not)\s+", low)
        if m and rec.frequency == "WEEKLY" and rec.by_day:
            # «every weekday except friday» → убрать день из BYDAY
            tail = low[m.end():]
            scan = re.match(r"((?:(?:weekends?|" + _WD + r")(?:\s*(?:,|and)\s*)?)+)", tail)
            if scan:
                excl = {5, 6} if re.search(r"weekends?", scan.group(1)) else set()
                for wm in re.finditer(_WD, scan.group(1)):
                    excl.add(WEEKDAYS[wm.group(0)])
                kept = [d for d in rec.by_day if RRULE_DAYS.index(d) not in excl]
                if excl and kept:
                    rec.by_day = kept
                    extra.append((m.start(), m.end() + scan.end()))
        if m and rec.frequency == "DAILY":
            tail = low[m.end() :]
            scan = re.match(r"((?:(?:weekends?|" + _WD + r")(?:\s*(?:,|and)\s*)?)+)", tail)
            if scan:
                seg = scan.group(1)
                excl = set()
                if re.search(r"weekends?", seg):
                    excl |= {5, 6}
                for wm in re.finditer(_WD, seg):
                    excl.add(WEEKDAYS[wm.group(0)])
                if excl:
                    keep = [i for i in range(7) if i not in excl]
                    rec.frequency = "WEEKLY"
                    rec.by_day = [RRULE_DAYS[i] for i in keep]
                    extra.append((m.start(), m.end() + scan.end()))
        rec._extra_spans = extra
        return (s0, e0)

    def _has_specific_recurrence(self, low):
        """Более специфичный маркер every, который должен победить одиночный
        adverb daily/weekly/... стоящий в названии задачи ('run weekly planning')."""
        return bool(
            re.search(r"\bevery\s+(" + _WD + r")\b", low)
            or re.search(
                r"\bevery\s+(\d+|two|three|four|other)\s+"
                r"(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months)\b",
                low,
            )
            or re.search(r"\bevery\s+other\b", low)
            or re.search(r"\bevery\s+(?:week\s?day|business\s+day)\b", low)
            or re.search(r"\bon\s+week\s?days\b", low)
            or re.search(r"\b(?:on\s+weekends?|every\s+weekend)\b", low)
            or re.search(r"\bevery\s+month\s+on\s+the\b", low)
        )

    def _recurrence_base(self, low, now):
        # daily/weekly/monthly/yearly adverbs
        # adverb-маркер уступает более специфичному every-паттерну: в
        # «every Monday ... run weekly planning» слово weekly — часть title.
        m = re.search(r"\b(daily|weekly|monthly|yearly)\b", low)
        if m and not self._has_specific_recurrence(low):
            fm = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY", "yearly": "YEARLY"}
            return RecurrenceRule(frequency=fm[m.group(1)]), m.span()
        # every weekday / on weekdays / every business day
        m = re.search(r"\b(?:every\s+(?:week\s?day|business\s+day)|on\s+week\s?days)\b", low)
        if m:
            return RecurrenceRule(frequency="WEEKLY", by_day=RRULE_DAYS[:5]), m.span()
        # on weekends / every weekend → сб+вс
        m = re.search(r"\b(?:on\s+weekends?|every\s+weekend)\b", low)
        if m:
            return RecurrenceRule(frequency="WEEKLY", by_day=["SA", "SU"]), m.span()
        # every other week/day/month
        m = re.search(r"\bevery\s+other\s+(day|week|month)\b", low)
        if m:
            fm = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY"}
            return RecurrenceRule(frequency=fm[m.group(1)], interval=2), m.span()
        # every month on the Nth  |  on the Nth of every month
        m = re.search(
            r"\bevery\s+month\s+on\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", low
        ) or re.search(
            r"\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(?:every|each)\s+month\b", low
        )
        if m:
            return RecurrenceRule(frequency="MONTHLY", by_month_day=[int(m.group(1))]), m.span()
        # every N days/weeks/months [on <weekday>]
        m = re.search(
            r"\bevery\s+(\d+|two|three|four|other)\s+(minute|minutes|min|hour|hours|hr|day|days|week|weeks|month|months)\b",
            low,
        )
        if m:
            n = {"two": 2, "three": 3, "four": 4, "other": 2}.get(m.group(1))
            n = n if n else int(m.group(1))
            unit = {
                "minute": "MINUTELY",
                "minutes": "MINUTELY",
                "min": "MINUTELY",
                "hour": "HOURLY",
                "hours": "HOURLY",
                "hr": "HOURLY",
                "day": "DAILY",
                "days": "DAILY",
                "week": "WEEKLY",
                "weeks": "WEEKLY",
                "month": "MONTHLY",
                "months": "MONTHLY",
            }[m.group(2)]
            rec = RecurrenceRule(frequency=unit, interval=n)
            end = m.end()
            # on <weekday>[s] после every N недель («every 2 weeks on Mondays»);
            # допускаем мн.ч. и нормализуем перед поиском в WEEKDAYS
            wm = re.search(r"\bon\s+(" + _WD + r")s?\b", low[m.end() :])
            if wm:
                wd_key = wm.group(1).rstrip("s") if wm.group(1) not in WEEKDAYS else wm.group(1)
                if wd_key in WEEKDAYS:
                    rec.by_day = [RRULE_DAYS[WEEKDAYS[wd_key]]]
                    end = m.end() + wm.end()
            return rec, (m.start(), end)
        # every <weekday> [(and|,) <weekday>]*  («every monday and wednesday»)
        m = re.search(
            r"\bevery\s+(" + _WD + r")((?:\s*(?:,|and|&)\s*(?:" + _WD + r"))*)\b", low
        )
        if m:
            wds = {WEEKDAYS[m.group(1)]}
            for wm in re.finditer(_WD, m.group(2) or ""):
                wds.add(WEEKDAYS[wm.group(0)])
            return (
                RecurrenceRule(frequency="WEEKLY", by_day=[RRULE_DAYS[k] for k in sorted(wds)]),
                m.span(),
            )
        # every day/week/month/year
        m = re.search(r"\bevery\s+(day|week|month|year)\b", low)
        if m:
            fm = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}
            return RecurrenceRule(frequency=fm[m.group(1)]), m.span()
        return None, None

    def _recurrence_dtstart(self, rec, base, now, has_time):
        # поминутные/почасовые повторы стартуют сейчас (паритет с RU «каждые 15 минут»)
        if rec.frequency in ("MINUTELY", "HOURLY") and not rec.by_day:
            return base
        if rec.by_day:
            wds = sorted(RRULE_DAYS.index(d) for d in rec.by_day)
            best = None
            for wd in wds:
                delta = (wd - now.weekday()) % 7
                cand = base + timedelta(days=delta)
                if has_time and delta == 0 and cand <= now:
                    cand += timedelta(days=7)
                if best is None or cand < best:
                    best = cand
            return best
        if has_time and base <= now:
            return base + timedelta(days=1)
        return base

    # ── deadline ────────────────────────────────────────────────────────
    def _deadline(self, low, now):
        m = re.search(
            r"\b(by|before|due)\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?(day|week|month|year|quarter)\b",
            low,
        )
        if m:
            _, e_full = self._period_bounds(m.group(2), now)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e_full,
                has_time=False,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        # by end of <named month>: «by end of March» → 31.03 23:59
        # (паритет с RU «до конца марта»; прошедший месяц → следующий год)
        m = re.search(r"\b(by|before|due)\s+(?:the\s+)?end\s+of\s+(" + _MON + r")\b", low)
        if m:
            mon = MONTHS[m.group(2)[:3] if m.group(2)[:3] in MONTHS else m.group(2)]
            y = now.year
            e = datetime(y, mon, monthrange(y, mon)[1], 23, 59)
            if e < now:
                y += 1
                e = datetime(y, mon, monthrange(y, mon)[1], 23, 59)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e,
                has_time=False,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        # by/before/due <time>
        m = re.search(r"\b(by|before|due)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if re.search(r"\b(by|before|due)\s+noon\b", low):
            mm = re.search(r"\b(by|before|due)\s+noon\b", low)
            e = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if self.nf and e < now:
                e += timedelta(days=1)
            return (
                DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=e,
                    has_time=True,
                    is_deadline=True,
                    confidence=0.85,
                ),
                mm.span(),
            )
        # by <weekday|date>
        dm = re.search(
            r"\b(by|before|due)\s+(next|this)?\s*("
            + _WD
            + r"|"
            + _MON
            + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
            low,
        )
        if dm:
            sub = dm.group(0)
            # переиспользуем _date на «хвосте» после by/before/due
            tail = sub.split(None, 1)[1] if " " in sub else sub
            dres = self._date(tail, now)
            if dres is not None:
                d = dres[0]
                dt = DateTimeToken(
                    type=DateTimeType.FIXED,
                    date_from=now,
                    date_to=d.replace(hour=23, minute=59),
                    has_time=False,
                    is_deadline=True,
                    confidence=0.85,
                )
                return dt, dm.span()
        if m:
            h = int(m.group(2))
            mn = int(m.group(3) or 0)
            ap = m.group(4)
            # Валидация: с am/pm 1..12, иначе 0..23; минуты 0..59. «by 25:00» → None.
            if ap is not None:
                if not (1 <= h <= 12 and 0 <= mn <= 59):
                    return None
            elif not (0 <= h <= 23 and 0 <= mn <= 59):
                return None
            h = self._ap(h, ap)
            if ap is None and self.nf and 1 <= h <= 7:
                h += 12
            e = now.replace(hour=h % 24, minute=mn, second=0, microsecond=0)
            if self.nf and e < now:
                e += timedelta(days=1)
            dt = DateTimeToken(
                type=DateTimeType.FIXED,
                date_from=now,
                date_to=e,
                has_time=True,
                is_deadline=True,
                confidence=0.85,
            )
            return dt, m.span()
        return None

    # ── relative / duration ───────────────────────────────────────────────
    def _relative(self, low, now):
        _UNITS = r"(seconds|second|secs|sec|minute|minutes|mins|min|hour|hours|hrs|hr|day|days|week|weeks|month|months|year|years)"
        _NUMS = r"(\d+(?:\.\d+)?|a|an|half\s+an?|one|two|three|four|five|six|seven|eight|nine|ten)"

        def _num(w):
            if w in ("a", "an"):
                return 1
            if w.startswith("half"):
                return 0.5
            if re.match(r"^\d+\.\d+$", w):
                return float(w)
            v = NUM_WORDS.get(w)
            return v if v is not None else int(w)

        # «in X and a half <unit>»: in two and a half hours → 2.5
        m = re.search(r"\bin\s+" + _NUMS + r"\s+and\s+a\s+half\s+" + _UNITS + r"\b", low)
        if m:
            n = _num(m.group(1)) + 0.5
            unit = m.group(2)
        else:
            # «in an <unit> and a half»: in an hour and a half → 1.5
            m = re.search(r"\bin\s+an?\s+(minute|hour|day|week|month|year)\s+and\s+a\s+half\b", low)
            if m:
                n = 1.5
                unit = m.group(1)
            else:
                m = re.search(r"\bin\s+" + _NUMS + r"\s+" + _UNITS + r"\b", low)
                if not m:
                    return None
                n = _num(m.group(1))
                unit = m.group(2)
        try:
            if unit.startswith("sec"):
                target = now + timedelta(seconds=n)
                ht = True
            elif unit.startswith(("minute", "min")):
                target = now + timedelta(minutes=n)
                ht = True
            elif unit.startswith(("hour", "hr")):
                target = now + timedelta(hours=n)
                ht = True
            elif unit.startswith("day"):
                target = now + timedelta(days=n)
                ht = False
            elif unit.startswith("week"):
                target = now + timedelta(weeks=n)
                ht = False
            elif unit.startswith("month"):
                # дробные месяцы: целая часть календарно, половина ≈ 15 дней
                # (паритет с RU «через полтора месяца»)
                target = self._add_months(now, int(n))
                if n != int(n):
                    target += timedelta(days=15)
                ht = False
            else:
                target = self._add_months(now, int(n * 12))
                ht = False
        except (ValueError, OverflowError):
            # «in 999999999 years» — за пределами datetime; честный ответ None
            return None
        dt = DateTimeToken(
            type=DateTimeType.SPAN_FORWARD,
            date_from=target,
            date_to=target,
            has_time=ht,
            all_day=not ht,
            confidence=0.9,
        )
        return dt, m.span()

    _DUR_RE = re.compile(
        r"\bfor\s+(\d+(?:[.,]\d+)?|half\s+an?|an?|one|two|three|four|five|six)"
        r"(\s+and\s+a\s+half)?\s*"
        r"(hours?|hrs?|h|minutes?|mins?|m)\b"
        r"(\s+and\s+a\s+half)?"
    )

    def _duration_match(self, low):
        """«for 2 hours», «for 1.5 hours», «for an hour and a half»,
        «for 2 and a half hours», «for half an hour», «for 90 min», «for 2h».
        → (minutes, span) | None."""
        m = self._DUR_RE.search(low)
        if not m:
            return None
        w = m.group(1)
        if w.startswith("half"):
            n = 0.5
        elif w in ("a", "an"):
            n = 1
        else:
            n = NUM_WORDS.get(w)
            n = n if n is not None else float(w.replace(",", "."))
        if m.group(2) or m.group(4):
            n += 0.5
        unit = m.group(3)
        minutes = n * 60 if unit.startswith("h") else n
        if minutes <= 0:
            return None
        return int(round(minutes)), m.span()

    def _duration(self, low):
        r = self._duration_match(low)
        return r[0] if r else None

    # ── helpers ───────────────────────────────────────────────────────────
    def _safe(self, y, mo, d):
        try:
            return datetime(y, mo, d, 0, 0, 0)
        except ValueError:
            return None

    def _add_months(self, dt, months):
        m = dt.month - 1 + months
        y = dt.year + m // 12
        m = m % 12 + 1
        d = min(dt.day, monthrange(y, m)[1])
        return dt.replace(year=y, month=m, day=d)

    def _period_bounds(self, unit, now):
        if unit == "day":
            s = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return s, s.replace(hour=23, minute=59)
        if unit == "week":
            mon = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return mon, (mon + timedelta(days=6)).replace(hour=23, minute=59)
        if unit == "month":
            last = monthrange(now.year, now.month)[1]
            return datetime(now.year, now.month, 1), datetime(now.year, now.month, last, 23, 59)
        if unit == "quarter":
            q = (now.month - 1) // 3
            m1 = q * 3 + 1
            m2 = m1 + 2
            return datetime(now.year, m1, 1), datetime(
                now.year, m2, monthrange(now.year, m2)[1], 23, 59
            )
        return datetime(now.year, 1, 1), datetime(now.year, 12, 31, 23, 59)

    def _part_window(self, unit, part, s_full, e_full):
        pad = 1 if unit == "week" else (4 if unit == "month" else 9)
        if part == "start":
            return s_full, (s_full + timedelta(days=pad)).replace(hour=23, minute=59)
        if part == "end":
            return (e_full - timedelta(days=pad)).replace(hour=0, minute=0), e_full
        mid = s_full + (e_full - s_full) / 2
        half = pad // 2 + 1  # середина уже начала/конца (как в RU PeriodRecognizer)
        return (
            (mid - timedelta(days=half)).replace(hour=0, minute=0, second=0, microsecond=0),
            (mid + timedelta(days=half)).replace(hour=23, minute=59, second=0, microsecond=0),
        )

    def _title(self, text, spans):
        chars = list(text)
        for s, e in spans:
            # «on [friday]» / «on [the 5th]» — предлог даты уходит вместе с ней;
            # «turn the lights on [at 7pm]» — «on» тут часть глагола, остаётся
            frag = text[s:e].lstrip().lower()
            m_on = re.search(r"\bon\s*$", text[:s], re.IGNORECASE)
            if m_on and re.match(r"(?:" + _WD + r"|" + _MON + r"|the\b|\d)", frag):
                for k in range(m_on.start(), m_on.end()):
                    chars[k] = " "
            for k in range(s, min(e, len(chars))):
                chars[k] = "\x00"  # маркер вырезанного времени
        raw = "".join(chars)
        # предлог прямо перед вырезанным временем уходит вместе с ним: «meeting at [3pm]»
        raw = re.sub(r"\b(?:at|by|from|until)\s*(?=\x00)", " ", raw, flags=re.IGNORECASE)
        # висящий предлог/артикль рядом с вырезанным временем уходит; предлог со своим
        # словом остаётся («to the doctor», «with the team»)
        # «on»/«in» не трогаем: ими занимается правило фразовых глаголов выше
        _edge = "|".join(sorted(_EDGE_FILLER - {"on", "in"}, key=len, reverse=True))
        # цепочкой: «by the [end of the day]» → сначала «the», затем «by»
        for _ in range(4):
            new_raw = re.sub(r"\b(?:" + _edge + r")\s*(?=\x00)", " ", raw, flags=re.IGNORECASE)
            new_raw = re.sub(r"(?<=\x00)\s*\b(?:the|a|an|of)\b", " ", new_raw, flags=re.IGNORECASE)
            if new_raw == raw:
                break
            raw = new_raw
        raw = re.sub(r"\x00+", " \x00 ", raw)  # маркер как отдельное «слово»
        # второе время во фразе, не ставшее спаном: «… and call at 3pm» → «and call»
        raw = re.sub(
            r"\b(?:at|by|from|until)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", " ", raw,
            flags=re.IGNORECASE,
        )
        words = re.findall(r"[A-Za-z][A-Za-z']*|\x00", raw)
        temporal = (
            "today",
            "tomorrow",
            "tonight",
            "yesterday",
            "noon",
            "midnight",
            "morning",
            "afternoon",
            "evening",
            "night",
            "am",
            "pm",
            "week",
            "month",
            "year",
            "day",
            "days",
            "hours",
            "hour",
            "minutes",
            "minute",
            "weekday",
            "weekdays",
            "daily",
            "weekly",
            "monthly",
            "yearly",
            "st",
            "nd",
            "rd",
            "th",
            "other",
            "end",
            "beginning",
            "middle",
            "mid",
        )
        # Классы слов: SPAN — вырезанная дата/время, TIME — вырезанное именно время
        # (перед ним «on/in» не трогаем: «turn the lights on at 7pm»),
        # TEMPORAL — временное слово, EDGE — предлог/артикль, FILLER — паразит.
        date_like = re.compile(r"(?:" + _WD + r"|" + _MON + r"|the\b|\d|next\b|last\b|this\b|"
                               r"early\b|mid\b|middle\b|beginning\b|start\b|end\b)")
        frags = [text[s:e].lstrip().lower() for s, e in spans]
        seq, fi = [], 0
        for w in words:
            lw = w.lower()
            if w == "\x00":
                frag = frags[fi] if fi < len(frags) else ""
                fi += 1
                seq.append((w, "SPAN" if date_like.match(frag) else "TIME"))
            elif lw in WEEKDAYS or lw in MONTHS or lw in temporal:
                seq.append((w, "TEMPORAL"))
            elif lw in _EDGE_FILLER:
                seq.append((w, "EDGE"))
            elif lw in _FILLER:
                seq.append((w, "FILLER"))
            else:
                seq.append((w, "CONTENT"))
        # служебное слово рядом с вырезанным/временным — часть той конструкции
        removed = {"SPAN", "TEMPORAL", "TIME", "FILLER"}
        for _ in range(4):
            changed = False
            for i, (w, cls) in enumerate(seq):
                if cls != "EDGE":
                    continue
                lw = w.lower()
                # предлог относится к тому, что СПРАВА («to the doctor»), поэтому
                # смотрим только вперёд; в конце фразы указывать не на что
                nxt = seq[i + 1][1] if i + 1 < len(seq) else "FILLER"
                if lw in ("the", "a", "an"):
                    # артикль относится к существительному ПОСЛЕ вырезанного
                    # («run a [45 minute] demo», «write the [daily] summary»),
                    # поэтому снимаем его только вместе с предлогом слева
                    prev_w, prev_c = seq[i - 1] if i > 0 else ("", "")
                    # артикль в группе предлога («by the [end of day]») уходит вместе с ней,
                    # после смыслового слова («run a [45 minute] demo») — остаётся
                    in_prep_group = prev_c == "FILLER" or (
                        prev_c == "EDGE" and prev_w.lower() not in ("the", "a", "an")
                    )
                    rest = [c for _, c in seq[i + 1:] if c not in removed]
                    if nxt in removed and (in_prep_group or "CONTENT" not in rest):
                        seq[i] = (w, "FILLER")
                        changed = True
                    continue
                bad = {"SPAN", "TEMPORAL", "FILLER"} if lw in ("on", "in") else removed
                if nxt in bad:
                    seq[i] = (w, "FILLER")
                    changed = True
            if not changed:
                break
        kept = [w for w, c in seq if c == "CONTENT" or c == "EDGE"]
        filler_only = [w for w, c in seq if c == "FILLER"]
        _edge_noise = {"the", "a", "an", "and", "or"}
        while kept and kept[0].lower() in _edge_noise:
            kept.pop(0)
        while kept and kept[-1].lower() in _edge_noise:
            kept.pop()
        title = " ".join(kept).strip()
        if not title and filler_only:
            # если после удаления времени осталось только «reminder/meeting» — сохраняем
            title = " ".join(filler_only).strip()
        return title

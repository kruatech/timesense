"""
Распознавание комбинированных выражений (дата + время)
"""

from datetime import datetime, timedelta
from typing import List, Optional
from calendar import monthrange
import re

from .base import Recognizer
from ..models.token import TextToken
from ..models.datetime_token import DateTimeToken, DateTimeType
from ..dict.keywords import Keywords


class CombinedRecognizer(Recognizer):
    """Распознавание комбинированных дата + время"""

    MORNING_WORDS = {"утро", "утром", "утра", "утру"}
    DAY_WORDS = {"день", "днём", "днем", "дня", "дню"}
    EVENING_WORDS = {"вечер", "вечером", "вечера", "вечеру"}
    NIGHT_WORDS = {"ночь", "ночью", "ночи"}

    def recognize(self, tokens: List[TextToken], now: datetime) -> List[DateTimeToken]:
        results = []
        i = 0

        while i < len(tokens):
            on_date_time = self._try_parse_on_date_to_time(tokens, i, now)
            if on_date_time:
                results.append(on_date_time)
                tokens_used = 4
                for j in range(i, min(i + 10, len(tokens))):
                    if tokens[j].end >= on_date_time.end:
                        tokens_used = j - i + 1
                        break
                i += tokens_used
                continue

            combined = self._try_parse_day_and_time(tokens, i, now)
            if combined:
                results.append(combined)
                tokens_used = 2
                for j in range(i, min(i + 10, len(tokens))):
                    if tokens[j].end >= combined.end:
                        tokens_used = j - i + 1
                        break
                i += tokens_used
            else:
                i += 1

        return results

    def _find_part_of_day(self, tokens: List[TextToken], start_index: int) -> tuple:
        if start_index >= len(tokens):
            return (None, -1)

        token = tokens[start_index]
        token_val = token.value.lower()
        token_norm = token.normalized.lower() if token.normalized else ""

        if token_val in self.MORNING_WORDS or token_norm in self.MORNING_WORDS:
            return ("morning", start_index)
        elif token_val in self.EVENING_WORDS or token_norm in self.EVENING_WORDS:
            return ("evening", start_index)
        elif token_val in self.NIGHT_WORDS or token_norm in self.NIGHT_WORDS:
            return ("night", start_index)
        elif token_val in self.DAY_WORDS or token_norm in self.DAY_WORDS:
            return ("day", start_index)

        return (None, -1)

    def _resolve_hour(self, hour: int, part_of_day: Optional[str]) -> int:
        """
        Фиксированный маппинг часов:
        Без уточнения: 1-7 → +12, 8-12 → как есть, 0/13-23 → как есть
        С уточнением: уточнение побеждает.
        """
        if part_of_day is None:
            if 1 <= hour <= 7:
                return hour + 12
            return hour

        if part_of_day == "morning":
            return hour if hour <= 12 else hour
        elif part_of_day == "day":
            return hour + 12 if hour < 12 else hour
        elif part_of_day == "evening":
            return hour + 12 if hour <= 11 else hour
        elif part_of_day == "night":
            return hour

        return hour

    def _try_parse_on_date_to_time(
        self, tokens: List[TextToken], index: int, now: datetime
    ) -> Optional[DateTimeToken]:
        if index + 3 >= len(tokens):
            return None

        if tokens[index].normalized not in Keywords.TIME_ON:
            return None

        date_token = tokens[index + 1]
        offset = None

        if date_token.normalized in Keywords.TOMORROW:
            offset = 1
        elif date_token.normalized in Keywords.AFTER_TOMORROW:
            offset = 2
        elif date_token.normalized in Keywords.TODAY:
            offset = 0
        else:
            return None

        if (
            tokens[index + 2].normalized not in Keywords.TIME_BY
            and tokens[index + 2].normalized not in Keywords.TIME_FROM
        ):
            return None

        time_token = tokens[index + 3]
        hour = None
        minute = 0
        end_index = index + 3

        time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_token.value)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        elif time_token.value.isdigit():
            hour = int(time_token.value)
            if index + 4 < len(tokens):
                minute_result, minute_tokens = Keywords.parse_compound_minutes(
                    tokens, index + 4, self.morph
                )
                if minute_result is not None and 0 <= minute_result <= 59:
                    minute = minute_result
                    end_index = index + 3 + minute_tokens
        else:
            hour = Keywords.parse_number_word(time_token.value, self.morph)
            if hour is not None and index + 4 < len(tokens):
                minute_result, minute_tokens = Keywords.parse_compound_minutes(
                    tokens, index + 4, self.morph
                )
                if minute_result is not None and 0 <= minute_result <= 59:
                    minute = minute_result
                    end_index = index + 3 + minute_tokens

        if hour is None or hour > 23:
            return None

        # Проверяем часть суток ПОСЛЕ часа
        part_of_day, pod_index = self._find_part_of_day(tokens, end_index + 1)
        if part_of_day:
            end_index = pod_index

        hour = self._resolve_hour(hour, part_of_day)

        target_date = now + timedelta(days=offset)
        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=target_date,
            date_to=target_date,
            has_time=True,
            all_day=False,
            start=tokens[index].start,
            end=tokens[end_index].end,
        )

    def _try_parse_day_and_time(
        self, tokens: List[TextToken], index: int, now: datetime
    ) -> Optional[DateTimeToken]:
        if index + 1 >= len(tokens):
            return None

        day = None

        ordinal_match = re.match(r"^(\d+)-го$", tokens[index].value, re.IGNORECASE)
        if ordinal_match:
            day = int(ordinal_match.group(1))
        elif tokens[index].value.isdigit():
            day = int(tokens[index].value)
        else:
            day = Keywords.parse_number_word(tokens[index].value, self.morph)

        if day is None or not (1 <= day <= 31):
            return None

        month = None
        time_index = index + 1

        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            for i, month_words in enumerate(Keywords.months()):
                if next_token.normalized in month_words:
                    month = i + 1
                    time_index = index + 2
                    break

        hour = None
        minute = 0
        end_index = index
        part_of_day = None

        if time_index < len(tokens):
            time_token = tokens[time_index]
            time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_token.value)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    end_index = time_index

        if hour is None and time_index < len(tokens):
            preposition = tokens[time_index].normalized
            if (
                preposition in Keywords.TIME_FROM or preposition in Keywords.TIME_BY
            ) and time_index + 1 < len(tokens):
                hour_token = tokens[time_index + 1]
                time_match = re.match(r"(\d{1,2})[:\-](\d{2})", hour_token.value)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        end_index = time_index + 1
                else:
                    if hour_token.value.isdigit():
                        hour = int(hour_token.value)
                        end_index = time_index + 1
                    else:
                        hour = Keywords.parse_number_word(hour_token.value, self.morph)
                        if hour is not None:
                            end_index = time_index + 1

                # Проверяем часть суток ПОСЛЕ часа
                if hour is not None and end_index + 1 < len(tokens):
                    part_of_day, pod_index = self._find_part_of_day(tokens, end_index + 1)
                    if part_of_day:
                        end_index = pod_index

        if hour is None or hour > 23:
            return None

        hour = self._resolve_hour(hour, part_of_day)

        month_explicit = month is not None
        if month is None:
            month = now.month

        year = now.year

        max_day = monthrange(year, month)[1]
        if day > max_day:
            month += 1
            if month > 12:
                month = 1
                year += 1
            max_day = monthrange(year, month)[1]
            if day > max_day:
                day = max_day

        target_date = datetime(year, month, day, 0, 0, 0)
        if target_date.date() < now.date():
            if month_explicit:
                # Явно названный месяц («19 апреля») в прошлом → следующий год,
                # НЕ следующий месяц (иначе апрель уезжал в май).
                year += 1
            else:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            max_day = monthrange(year, month)[1]
            if day > max_day:
                day = max_day
            target_date = datetime(year, month, day, 0, 0, 0)

        final_datetime = datetime(year, month, day, hour, minute, 0)

        return DateTimeToken(
            type=DateTimeType.FIXED,
            date_from=final_datetime,
            date_to=final_datetime,
            has_time=True,
            all_day=False,
            start=tokens[index].start,
            end=tokens[end_index].end,
        )

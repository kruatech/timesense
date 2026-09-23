"""Диагностика разбора для ботов: почему фраза не распозналась и что уточнить.

    a = parser.analyze("в понедельник или вторник созвон")
    a.status        # ParseStatus.AMBIGUOUS
    a.reason        # "alternatives: several dates/times offered"
    a.alternatives  # [Task(понедельник), Task(вторник)] — можно предложить кнопками
    a.result        # None (parse() тоже вернул бы None)

parse() не меняется: analyze() — надстройка с тем же результатом плюс причиной.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional


class ParseStatus(str, Enum):
    OK = "ok"                          # распознано, см. .result
    EMPTY = "empty"                    # пустая строка / только пробелы
    TOO_LONG = "too_long"              # длиннее TimeConfig.max_text_length
    NO_DATETIME = "no_datetime"        # даты/времени во фразе нет
    AMBIGUOUS = "ambiguous"            # несколько вариантов («в пн или вт», «вчера и завтра»)
    MULTIPLE = "multiple"              # несколько отдельных событий («в пн, ср и пт в 10») —
                                       # все они в alternatives, в parse_multi() — списком
    INVALID_DATE = "invalid_date"      # невозможная дата/время («31 февраля», «в 25:00»)
    NEEDS_TIMEZONE = "needs_timezone"  # пояс в тексте («в 10 мск»), а tz пользователя не задан


class ParseAnalysis:
    def __init__(
        self,
        result: Any = None,
        status: ParseStatus = ParseStatus.NO_DATETIME,
        reason: str = "",
        alternatives: Optional[List[Any]] = None,
        language: Optional[str] = None,
    ) -> None:
        self.result = result
        self.status = status
        self.reason = reason
        self.alternatives = alternatives or []
        self.language = language

    @property
    def ok(self) -> bool:
        return self.status == ParseStatus.OK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "language": self.language,
            "result": self.result.to_dict() if self.result is not None else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
        }

    def __repr__(self) -> str:
        return "ParseAnalysis(status=%s, reason=%r, result=%r, alternatives=%d)" % (
            self.status.value, self.reason, self.result, len(self.alternatives))

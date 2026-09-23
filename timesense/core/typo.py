"""Исправление опечаток во временных словах (RU и EN).

«завтро» → «завтра», «понедельнек» → «понедельник», «сентебря» → «сентября»,
«wensday» → «wednesday», «tomorow» → «tomorrow».

Правила консервативные, чтобы не превращать обычные слова в даты:
  * только слова длиной ≥ 6 букв и только временные слова-цели (дни недели,
    месяцы, сегодня/завтра/послезавтра/вчера …);
  * расстояние Дамерау–Левенштейна ровно 1 (одна замена / вставка / удаление /
    перестановка соседних букв);
  * кандидат должен быть единственным;
  * стоп-список реальных слов на расстоянии 1 от временных («завтрак» ≠ «завтра»).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set

_MIN_LEN = 6


def _damerau1(a: str, b: str) -> bool:
    """True, если расстояние Дамерау–Левенштейна между a и b равно ровно 1."""
    la, lb = len(a), len(b)
    if a == b or abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        if len(diff) == 2 and diff[1] == diff[0] + 1:
            i, j = diff
            return a[i] == b[j] and a[j] == b[i]
        return False
    if la > lb:
        a, b = b, a  # a короче на 1
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


class TypoFixer:
    def __init__(self, vocab: Iterable, stop: Iterable[str] = (), word_re: str = r"[a-zа-яё]+"):
        """vocab — слова или группы форм одного значения (["пятница", "пятницу", …]):
        если опечатка близка к нескольким формам ОДНОЙ группы, это не неоднозначность."""
        self.group: Dict[str, int] = {}
        for gi, item in enumerate(vocab):
            forms = [item] if isinstance(item, str) else list(item)
            for w in forms:
                if len(w) >= _MIN_LEN:
                    self.group.setdefault(w.lower(), gi)
        self.vocab: Set[str] = set(self.group)
        self.stop: Set[str] = {w.lower() for w in stop}
        # индекс по первой букве (перестановка «firday» задевает уже вторую букву)
        self._index: Dict[str, List[str]] = {}
        for w in sorted(self.vocab):
            self._index.setdefault(w[:1], []).append(w)
        self._word_re = re.compile(word_re, re.IGNORECASE)
        self._cache: Dict[str, Optional[str]] = {}

    def correct(self, word: str) -> Optional[str]:
        low = word.lower()
        if len(low) < _MIN_LEN or low in self.vocab or low in self.stop:
            return None
        if low in self._cache:
            return self._cache[low]
        cands = [v for v in self._index.get(low[:1], ()) if _damerau1(low, v)]
        fix = cands[0] if cands and len({self.group[c] for c in cands}) == 1 else None
        if len(self._cache) < 10000:
            self._cache[low] = fix
        return fix

    def fix_text(self, text: str) -> str:
        def repl(m):
            w = m.group(0)
            fixed = self.correct(w)
            return fixed if fixed is not None else w

        return self._word_re.sub(repl, text)


_RU: Optional[TypoFixer] = None
_EN: Optional[TypoFixer] = None


def ru_fixer() -> TypoFixer:
    global _RU
    if _RU is None:
        from ..dict.keywords import Keywords

        vocab: List[Any] = ["сегодня", "завтра", "послезавтра", "позавчера", "вчера"]
        for forms in Keywords.days_of_week() + Keywords.days_of_week_dative():
            vocab.append(list(forms))
        for forms in Keywords.months():
            vocab.append(list(forms))
        stop = [
            # реальные слова на расстоянии 1 от временных
            "завтрак", "завтрака", "завтраку", "завтраком", "завтраке", "завтраки",
            "средний", "средняя", "среднее",
        ]
        # все слова, которые парсер уже знает («вечера», «утра», «недели»…), —
        # никогда не «исправляем»: «вечера» не должно стать «вчера»
        for name in dir(Keywords):
            val = getattr(Keywords, name)
            if isinstance(val, (list, tuple, set)):
                stop += [x for x in val if isinstance(x, str)]
        stop += ["вечера", "вечером", "вечеру", "утром", "утра", "ночью", "ночи", "днём",
                 "днем", "дня", "обеда", "обедом", "полудня", "полуночи", "недели", "неделе"]
        _RU = TypoFixer(vocab, stop, r"[а-яё]+")
    return _RU


def en_fixer() -> TypoFixer:
    global _EN
    if _EN is None:
        vocab = [
            "today", "tomorrow", "tonight", "yesterday",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "january", "february", "march", "april", "june", "july", "august",
            "september", "october", "november", "december",
            "morning", "evening", "afternoon", "midnight", "weekend", "weekday",
        ]
        stop = ["mornings", "evenings", "weekends", "weekdays", "mondays", "tuesdays",
                "fridays", "sundays", "saturdays", "thursdays", "wednesdays", "augusta",
                "marched", "junes", "tonights"]
        _EN = TypoFixer(vocab, stop, r"[a-z]+")
    return _EN

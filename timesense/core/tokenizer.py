"""Токенизатор текста"""

import re
from ..models.token import TextToken
from ..dict.morph_adapter import get_morph


class Tokenizer:
    def __init__(self):
        self.morph = get_morph()

    def tokenize(self, text):
        tokens = []
        pattern = r"""
            (\d{1,2}:\d{2}[-\u2013\u2014]\d{1,2}:\d{2}) |
            (\d{1,2}[-\u2013\u2014]\d{1,2}) |
            (\d{1,2}[./]\d{1,2}[./]\d{2,4}) |
            (\d+,\d+) |
            (\d{1,2}[./]\d{1,2}) |
            (\d{4}[-\u2013\u2014]\d{1,2}[-\u2013\u2014]\d{1,2}) |
            (\d{1,2}:\d{2}) |
            (\d+[-\u2013\u2014][а-яё]+) |
            ([а-яёa-z]+[-\u2013\u2014][а-яёa-z]+) |
            ([а-яёa-z]+) |
            (\d+)
        """
        for m in re.finditer(pattern, text, re.IGNORECASE | re.VERBOSE):
            v = m.group(0)
            nv = re.sub(r"[\u2013\u2014\u2212]", "-", v)
            n = self._normalize(nv)
            tokens.append(TextToken(value=nv, start=m.start(), end=m.end(), normalized=n))
        return tokens

    def _normalize(self, word):
        if any(c.isdigit() for c in word):
            return word.lower()
        return self.morph.normalize(word)

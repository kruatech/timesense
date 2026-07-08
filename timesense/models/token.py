"""Токены текста"""

from typing import Optional


class TextToken:
    def __init__(self, value: str, start: int = 0, end: int = 0, normalized: Optional[str] = None):
        self.value = value
        self.start = start
        self.end = end
        self.normalized = normalized or value.lower()

    def __repr__(self):
        return f"TextToken('{self.value}', {self.start}, {self.end})"

    def __str__(self):
        return self.value

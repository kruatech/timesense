"""Базовый класс"""

from abc import ABC, abstractmethod
from ..dict.morph_adapter import get_morph


class Recognizer(ABC):
    def __init__(self, config):
        self.config = config
        self.morph = get_morph()

    @abstractmethod
    def recognize(self, tokens, now):
        pass

    def find_token_by_words(self, tokens, words, start_index=0):
        wl = [w.lower() for w in words]
        for i in range(start_index, len(tokens)):
            if tokens[i].normalized in wl:
                return i
        return None

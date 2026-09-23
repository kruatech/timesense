"""Адаптер морфологии.

Морфология опциональна. По умолчанию пакет работает без внешних
зависимостей: normalize() возвращает word.lower(). Если в окружении
установлен pymorphy3 (предпочтительно) или pymorphy2 — он подхватывается
автоматически и используется для лемматизации.

Установка опциональной морфологии:
    pip install "timesense[morph]"
"""


import os


def _env_morph_disabled():
    v = os.environ.get("TIMESENSE_MORPH", "").strip().lower()
    return v in ("0", "false", "no", "off")


class MorphAdapter:
    def __init__(self, enabled=True):
        self.morph = None
        self.available = False
        if not enabled:
            return
        for mod_name in ("pymorphy3", "pymorphy2"):
            try:
                mod = __import__(mod_name)
                self.morph = mod.MorphAnalyzer()
                self.available = True
                break
            except Exception:
                # ImportError — модуль не установлен;
                # AttributeError — pymorphy2 на Python 3.11+ (getargspec удалён);
                # прочие — повреждённые словари и т.п. Тихо работаем без морфологии.
                self.morph = None
                self.available = False

    def normalize(self, word):
        if not self.available:
            return word.lower()
        try:
            parsed = self.morph.parse(word.lower())
            return parsed[0].normal_form if parsed else word.lower()
        except Exception:
            return word.lower()

    def has_lemma(self, word, lemma):
        return self.normalize(word) == lemma.lower()


_morph_adapter = None
_plain_adapter = None


def get_morph(enabled=None):
    """Общий адаптер морфологии.

    enabled=None  — авто: pymorphy3/pymorphy2, если установлен и не выключен
                    переменной окружения TIMESENSE_MORPH=0;
    enabled=False — без морфологии (быстрее в ~5 раз, меньше памяти);
    enabled=True  — попытаться подключить морфологию.
    """
    global _morph_adapter, _plain_adapter
    if enabled is False or (enabled is None and _env_morph_disabled()):
        if _plain_adapter is None:
            _plain_adapter = MorphAdapter(enabled=False)
        return _plain_adapter
    if _morph_adapter is None:
        _morph_adapter = MorphAdapter()
    return _morph_adapter

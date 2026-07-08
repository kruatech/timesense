# Вклад в TimeSense

Спасибо за интерес к проекту!

## Окружение

```bash
git clone https://github.com/kruatech/timesense
cd timesense
pip install -e ".[dev]"          # без морфологии
pip install -e ".[dev,morph]"    # с pymorphy3 (опционально)
```

## Тесты

Перед PR убедитесь, что все проверки зелёные:

```bash
python -m timesense.tests.test_fixes --fail-only     # RU-раннер
python -m timesense.tests.test_en_fixes --fail-only  # EN-раннер
pytest -q                                            # обёртки + EN pytest-набор

# релизные проверки (перед публикацией)
python -m build
python -m twine check dist/*
```

Новые возможности и исправления багов сопровождайте кейсами: RU — в
`timesense/tests/test_fixes.py` (функция `build_tests`, через `add(...)`),
EN — в `timesense/tests/test_en_fixes.py`.

## Стиль

- Python 3.9+, без обязательных внешних зависимостей в рантайме.
- `black` и `flake8` для форматирования/линтинга.
- Морфология опциональна: код обязан работать и без `pymorphy3`.

## Процесс

1. Откройте issue для крупных изменений.
2. Ветка → изменения + тесты → PR.
3. CI должен проходить на всех поддерживаемых версиях Python.

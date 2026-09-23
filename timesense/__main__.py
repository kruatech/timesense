"""Запуск из командной строки: `python -m timesense "завтра в 10 встреча"`.

    python -m timesense "в четверг утром в садик"
    python -m timesense --now "2026-09-22 14:00" --tz Europe/Moscow "в 10 мск созвон"
    python -m timesense --json "каждый понедельник в 10 планёрка"
    python -m timesense --ics "завтра в 10 встреча" > event.ics
    echo "завтра в 10 встреча" | python -m timesense      # по строке из stdin

Без ключей печатает разбор одной строкой (см. ReminderResult.summary()) и, если
фраза не распозналась, причину из analyze(): нет даты, неоднозначно, невозможная
дата, нужен часовой пояс.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List, Optional


def _parse_now(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise SystemExit("--now: ожидается «YYYY-MM-DD HH:MM», получено %r" % value)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="timesense",
        description="Разбор дат и событий из естественного языка (RU/EN).",
    )
    ap.add_argument("text", nargs="*", help="фраза; без неё читается stdin")
    ap.add_argument("--now", help="точка отсчёта, «YYYY-MM-DD HH:MM» (по умолчанию сейчас)")
    ap.add_argument("--tz", help="часовой пояс пользователя, например Europe/Moscow")
    ap.add_argument("--lang", choices=["auto", "ru", "en"], default="auto", help="язык фразы")
    ap.add_argument("--json", action="store_true", help="вывести to_dict() в JSON")
    ap.add_argument("--ics", action="store_true", help="вывести .ics")
    ap.add_argument("--multi", action="store_true", help="несколько событий (parse_multi)")
    ap.add_argument("--no-morph", action="store_true", help="без pymorphy3 (быстрее)")
    args = ap.parse_args(argv)

    from . import TimeConfig, TimeSenseParser, to_ics_calendar

    texts = [" ".join(args.text)] if args.text else [ln.strip() for ln in sys.stdin if ln.strip()]
    if not texts:
        ap.print_help()
        return 2

    parser = TimeSenseParser(TimeConfig(use_morph=False if args.no_morph else None))
    now = _parse_now(args.now)
    lang = None if args.lang == "auto" else args.lang
    exit_code = 0

    for text in texts:
        results = (
            parser.parse_multi(text, now=now, language=lang, tz=args.tz)
            if args.multi
            else [parser.parse(text, now=now, language=lang, tz=args.tz)]
        )
        results = [r for r in results if r is not None]
        if not results:
            a = parser.analyze(text, now=now, language=lang, tz=args.tz)
            en = a.language == "en"
            print("%s\n    %s: %s (%s)" % (text, "not recognized" if en else "не распознано",
                                           a.status.value, a.reason))
            for alt in a.alternatives:
                print("    %s: %s" % ("option" if en else "вариант", alt.summary()))
            exit_code = 1
            continue
        if args.json:
            out = [r.to_dict() for r in results]
            print(json.dumps(out if args.multi else out[0], ensure_ascii=False, indent=2))
        elif args.ics:
            print(to_ics_calendar(results), end="")
        else:
            if len(texts) > 1:
                print(text)
            for r in results:
                print(("    " if len(texts) > 1 else "") + r.summary())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

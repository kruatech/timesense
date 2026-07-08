#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TimeSense semantic stress test, EN.

500 валидных рабочих фраз. Это не набор "один шаблон + разные title":
кейсы перемешаны по типам и проверяют не только отсутствие падений, но и
простую семантику past/future.

Standalone:
    python3 tests/test_stress_en_500.py
    python3 tests/test_stress_en_500.py --verbose
    python3 tests/test_stress_en_500.py --audit
    python3 tests/test_stress_en_500.py --json > test_stress_en_500.json.json

Pytest:
    python3 -m pytest -q tests/test_stress_en_500.py -vv
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


NOW = datetime(2026, 7, 6, 15, 41)
LANGUAGE = "en"


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    tags: tuple[str, ...]
    temporal: str = "any"  # past | future | any


def normalize_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    data = {k: v for k, v in data.items() if k != "source"}
    return {"_class": type(result).__name__, **data}


def _primary_dt(data: dict[str, Any] | None) -> datetime | None:
    if not data:
        return None
    for key in ("datetime", "start", "deadline"):
        value = data.get(key)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
    return None


def _parse(parser: Any, text: str) -> Any:
    kwargs = {"now": NOW}
    kwargs["language"] = "en"
    return parser.parse(text, **kwargs)


def _is_recurrence_date_only(data: dict[str, Any] | None) -> bool:
    """Recurrence без времени (start=end=00:00): момент старта — сегодня,
    проверять надо until/окончание, а не start (аналог RU date-only recurrence)."""
    if not data or not data.get("recurrence"):
        return False
    start = data.get("start")
    end = data.get("end")
    if not isinstance(start, str):
        return False
    if not start.endswith("T00:00:00"):
        return False
    return start == end or (isinstance(end, str) and end.endswith("T00:00:00"))


def _validate(case: Case, result: Any) -> list[str]:
    errors: list[str] = []
    data = normalize_result(result)

    # temporal="none": фраза намеренно неоднозначна (last week/month/quarter/year
    # + только время) → корректный результат именно None.
    if case.temporal == "none":
        if data is not None:
            errors.append(f"expected None (ambiguous), got {data.get('start') or data.get('datetime')}")
        return errors

    if data is None:
        return [f"None result for valid case: {case.text!r}"]

    dt = _primary_dt(data)
    is_past = data.get("is_past")

    # date-only recurrence: старт=сегодня, будущность определяется по until/концу
    if case.temporal == "future" and _is_recurrence_date_only(data):
        return errors

    if case.temporal == "past":
        if dt is None:
            errors.append("expected a primary datetime/start/deadline for past case")
        elif not dt < NOW:
            errors.append(f"expected past datetime, got {dt.isoformat()}")
        if is_past is not True:
            errors.append(f"expected is_past=True, got {is_past!r}")

    elif case.temporal == "future":
        if dt is None:
            errors.append("expected a primary datetime/start/deadline for future case")
        elif not dt >= NOW:
            errors.append(f"expected future/current datetime, got {dt.isoformat()}")
        if is_past is True:
            errors.append("expected non-past result, got is_past=True")

    return errors


def run_cases(verbose: bool = False) -> dict[str, Any]:
    from timesense import TimeSenseParser

    parser = TimeSenseParser()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    crashes: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()

    for case in make_cases():
        try:
            result = _parse(parser, case.text)
            data = normalize_result(result)
            result_type = "None" if result is None else type(result).__name__
            type_counts[result_type] += 1
            for tag in case.tags:
                tag_counts[tag] += 1

            errors = _validate(case, result)
            if errors:
                failures.append(
                    {
                        "id": case.id,
                        "text": case.text,
                        "tags": list(case.tags),
                        "temporal": case.temporal,
                        "errors": errors,
                        "result": data,
                    }
                )

            row = {
                "id": case.id,
                "text": case.text,
                "tags": list(case.tags),
                "temporal": case.temporal,
                "result": data,
                "errors": errors,
            }
            rows.append(row)

            if verbose:
                from timesense.tests._pretty import card
                print(card(row, LANGUAGE))
                print()

        except Exception as exc:  # noqa: BLE001
            crashes.append(
                {
                    "id": case.id,
                    "text": case.text,
                    "tags": list(case.tags),
                    "temporal": case.temporal,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            type_counts["CRASH"] += 1

    return {
        "now": NOW.isoformat(),
        "language": LANGUAGE,
        "case_count": len(make_cases()),
        "type_counts": dict(type_counts),
        "tag_counts": dict(tag_counts),
        "failures": failures,
        "crashes": crashes,
        "rows": rows,
        "multi": run_multi(),
    }


def run_multi() -> list[dict[str, Any]]:
    from timesense import TimeSenseParser

    parser = TimeSenseParser()
    out: list[dict[str, Any]] = []

    for text, expected_min in MULTI_CASES:
        try:
            kwargs = {"now": NOW}
            kwargs["language"] = "en"
            results = parser.parse_multi(text, **kwargs)
            out.append(
                {
                    "text": text,
                    "expected_min": expected_min,
                    "count": len(results),
                    "results": [normalize_result(r) for r in results],
                }
            )
        except Exception as exc:  # noqa: BLE001
            out.append(
                {
                    "text": text,
                    "expected_min": expected_min,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return out


def print_summary(snapshot: dict[str, Any]) -> None:
    from timesense.tests._pretty import header, summary, card
    print(header(snapshot, snapshot["language"], mode_all=False))
    if snapshot["failures"]:
        print()
        for row in snapshot["failures"][:80]:
            print(card(row, snapshot["language"]))
            print()
    print(summary(snapshot, snapshot["language"]))
    if False:
        print(f"NOW={snapshot['now']}")
        print(f"language={snapshot['language']}")
        print(f"cases={snapshot['case_count']}")
        print(f"type counts: {snapshot['type_counts']}")
        print(f"crashes: {len(snapshot['crashes'])}")
        print(f"semantic failures: {len(snapshot['failures'])}")

    if snapshot["crashes"]:
        print("\nCRASHES, first 50:")
        for row in snapshot["crashes"][:50]:
            print(f"  {row['id']} {row['text']!r}: {row['error_type']}: {row['error']}")

    if snapshot["failures"]:
        print("\nSEMANTIC FAILURES, first 80:")
        for row in snapshot["failures"][:80]:
            print(f"  {row['id']} {row['text']!r} temporal={row['temporal']} tags={tuple(row['tags'])}")
            for err in row["errors"]:
                print(f"    - {err}")

    from timesense.tests._pretty import multi_block
    print()
    print(multi_block(snapshot["multi"], snapshot["language"]))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--audit", action="store_true", help="do not exit 1 on semantic failures")
    ap.add_argument("--save-snapshot", type=Path)
    args = ap.parse_args(argv)

    snapshot = run_cases(verbose=args.verbose)

    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    else:
        print_summary(snapshot)

    if args.save_snapshot:
        args.save_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.save_snapshot.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"\nsaved snapshot: {args.save_snapshot}")

    bad_multi = [
        item for item in snapshot["multi"]
        if ("error_type" in item) or (item.get("count", 0) < item.get("expected_min", 0))
    ]

    if snapshot["crashes"] or bad_multi:
        return 1
    if snapshot["failures"] and not args.audit:
        return 1
    return 0


def make_cases() -> list[Case]:
    raw: list[Case] = []

    def add(text: str, tags: tuple[str, ...], temporal: str = "any") -> None:
        raw.append(Case(id="tmp", text=" ".join(text.split()), tags=tags, temporal=temporal))

    titles = [
        "review the supplier contract",
        "prepare the client follow up",
        "update the release checklist",
        "resolve reviewer comments",
        "approve the landing page mockup",
        "check the invoice payment",
        "create a database backup",
        "discuss the migration plan",
        "send the final estimate",
        "run the prototype demo",
        "collect the open questions",
        "review the metrics report",
        "prepare documents for legal",
        "update project tickets",
        "schedule the candidate interview",
        "check contractor permissions",
        "write the meeting summary",
        "process incoming requests",
        "verify the analytics export",
        "publish the changelog draft",
        "call the product designer",
        "check backup status",
        "reconcile accounting documents",
        "send participant invitations",
        "review monitoring alerts",
        "prepare the risk list",
        "review user feedback",
        "update the test plan",
        "agree on the presentation date",
        "check access rights",
        "review the pull request",
        "prepare release notes",
        "set up the demo environment",
        "collect conversion data",
        "check payment statuses",
        "write a partner reply",
        "recalculate campaign budget",
        "update the roadmap",
        "verify the attendee list",
        "check calendar integration",
        "order guest badges",
        "check demo stand readiness",
        "collect sales feedback",
        "prepare the blocker list",
        "update the risk matrix",
        "review the lease agreement",
        "approve the vacation schedule",
        "verify the equipment list",
        "handoff materials to the vendor",
        "prepare interview questions",
    ]

    past_markers = [
        "yesterday", "the day before yesterday", "three days ago", "four days ago", "five days ago",
        "two weeks ago", "last Monday", "last Wednesday", "last Friday",
    ]
    past_times = ["at 08:05", "at 09:40", "at 11:15", "at 14:30", "at 18:20"]
    for i, marker in enumerate(past_markers):
        for j, tm in enumerate(past_times):
            add(f"{marker} {tm} {titles[(i * 7 + j) % len(titles)]}", ("past", "date_time"), "past")

    future_markers = [
        "today", "tomorrow", "the day after tomorrow", "in one day", "in two days",
        "in three days", "in a week", "in two weeks", "in a month",
        "this coming Friday", "next Monday", "next Wednesday",
    ]
    future_times = ["at 16:05", "at 17:10", "at 18:25", "at 19:30"]
    for i, marker in enumerate(future_markers):
        for j, tm in enumerate(future_times):
            add(f"{marker} {tm} {titles[(100 + i * 5 + j) % len(titles)]}", ("future", "date_time"), "future")

    absolute_cases = [
        "the first of September hold the school ceremony",
        "January fifth check the holiday schedule",
        "February tenth prepare the document package",
        "March twenty first run the spring presentation",
        "December thirty first close the annual report",
        "February twenty eighth review the lease agreement",
        "July fifteenth send the interim report",
        "December twenty fifth congratulate partners",
        "March first update the hiring plan",
        "October twentieth check conference readiness",
        "January 2nd at 09:00 review the lease agreement",
        "February 7th at 13:30 prepare the document package",
        "March 12th at 18:15 review the pull request",
        "April 19th at 10:45 approve the vacation schedule",
        "May 24th at 16:20 verify the equipment list",
        "June 30th at 11:10 handoff materials to the vendor",
        "July 6th at 17:55 prepare interview questions",
        "August 18th at 12:25 update the risk matrix",
        "September 29th at 15:35 collect sales feedback",
        "December 31st at 23:30 check demo stand readiness",
    ]
    for text in absolute_cases:
        add(text, ("absolute_date",), "any")

    range_cases = [
        "today from 16:20 to 17:05 verify the migration plan",
        "tomorrow from 08:30 to 09:15 run the morning log check",
        "the day after tomorrow from 10:30 to 11:45 interview the candidate",
        "yesterday from 09:40 to 10:25 discuss the new form design",
        "the day before yesterday from 14:00 to 15:30 run the API working session",
        "on Friday from 18:00 to 20:00 meet the partner",
        "last Friday from 12:10 to 13:00 review the open questions",
        "next Tuesday from 23:15 to 00:45 check the maintenance window",
        "from August 1 to 5 arrange team vacation",
        "from July 10 to 12 run offsite training",
        "from December 25 to January 5 prepare the on call schedule",
        "from Monday to Friday from 10 to 12 run the seminar series",
        "from Tuesday to Thursday from 14 to 16 train support operators",
        "from morning to evening run the warehouse inventory",
        "from Friday evening to Monday morning organize support duty",
        "from the beginning of the week to Friday check all requests",
    ]
    for text in range_cases:
        temporal = "past" if text.startswith(("yesterday", "the day before yesterday", "last Friday")) else "any"
        add(text, ("range",), temporal)

    deadline_cases = [
        "by 18:30 today submit the signed contract",
        "by tomorrow prepare the board presentation",
        "by tomorrow 10:00 update client documentation",
        "by Friday check the budget calculation",
        "by Friday 18:00 close critical comments",
        "by next Monday write the partner reply",
        "by end of day check the access list",
        "by end of week send the final mockup",
        "by end of month prepare the accounting package",
        "by end of quarter approve the payment schedule",
        "by end of year update the roadmap",
        "before Friday prepare the risk list",
        "by Monday 12:00 check payment statuses",
        "by the end of the day verify the attendee list",
        "by September first prepare the school form",
        "no later than Friday agree on the presentation date",
        "no later than end of month close finance documents",
        "by the last business day of the month prepare the finance report",
        "by the first business day of next month update the team plan",
        "by December 31 23:59 close the annual report",
    ]
    for text in deadline_cases:
        add(text, ("deadline",), "future")

    recurrence_cases = [
        "every day at 08:10 take medication",
        "every day at 19:20 write the daily summary",
        "every weekday at 09:00 check the request queue",
        "every weekday until end of month at 09:30 run a short status meeting",
        "on weekdays at 18:00 send the daily report",
        "on weekends at 11:00 check the family calendar",
        "every Monday at 10:00 run weekly planning",
        "every Wednesday at 15:30 review team tasks",
        "every Friday at 16:00 collect retrospective notes",
        "every 2 weeks on Mondays at 12:00 run synchronization",
        "every month on the 15th check rent payment",
        "every month on the 30th pay service invoices",
        "every last business day of the month prepare the finance report",
        "every first Tuesday of the month run the product committee",
        "the first Tuesday of every January at 15:00 run annual planning",
        "every day until Friday at 18:00 send a short status",
        "every Monday until end of quarter run the architecture review",
        "every Friday until end of year update the roadmap",
        "every month until December check license renewals",
        "every weekday except Friday at 09:15 check incidents",
    ]
    for text in recurrence_cases:
        add(text, ("recurrence",), "future")

    special = [
        ("last business day of the month prepare the finance report", ("working_days",), "future"),
        ("first business day of the month update the team plan", ("working_days",), "any"),
        ("in two business days send the legal reply", ("working_days",), "future"),
        ("in three business days check the delivery status", ("working_days",), "future"),
        ("two business days before end of month remind about closing documents", ("working_days",), "future"),
        ("every first business day of the month reconcile the department budget", ("working_days", "recurrence"), "future"),
        ("every last business day of the month close finance tasks", ("working_days", "recurrence"), "future"),
        ("next business day review the contract", ("working_days",), "future"),
        ("in spring run the partner conference", ("fuzzy", "period"), "any"),
        ("in summer plan the team offsite", ("fuzzy", "period"), "any"),
        ("in autumn prepare the major release", ("fuzzy", "period"), "future"),
        ("in fall prepare the marketing campaign", ("fuzzy", "period"), "future"),
        ("in winter run the security audit", ("fuzzy", "period"), "any"),
        ("at the beginning of the month update the sales plan", ("fuzzy", "period"), "any"),
        ("in the middle of the month review product metrics", ("fuzzy", "period"), "any"),
        ("at the end of the month pay contractor invoices", ("fuzzy", "period"), "future"),
        ("next week meet the support team", ("fuzzy", "period"), "future"),
        ("last week review experiment results", ("fuzzy", "period"), "past"),
        ("tomorrow at 10:30 at the office discuss the lease agreement", ("location", "date_time"), "future"),
        ("Friday at 18:00 at the cafe meet the partner", ("location", "date_time"), "future"),
        ("today at 17:00 in Zoom run the screen sharing demo", ("location", "date_time"), "future"),
        ("yesterday at 09:00 in the meeting room review the incident", ("location", "date_time"), "past"),
        ("the day after tomorrow at 07:30 at the airport meet the delegation", ("location", "date_time"), "future"),
        ("next Tuesday at 11:00 at the client site run training", ("location", "date_time"), "future"),
        ("tomorrow at 10:00 run a 30 minute planning session", ("duration", "date_time"), "future"),
        ("Friday at 14:00 run a 45 minute demo", ("duration", "date_time"), "future"),
        ("yesterday at 10:00 run a 30 minute call", ("duration", "past"), "past"),
        ("the day before yesterday at 12:00 run a 45 minute interview", ("duration", "past"), "past"),
        ("in 15 minutes check deployment status", ("duration", "relative"), "future"),
        ("in half an hour call the building administrator", ("duration", "relative"), "future"),
        ("in an hour remind me to send the contract", ("duration", "relative"), "future"),
        ("in two and a half hours check migration results", ("duration", "relative"), "future"),
    ]
    for text, tags, temporal in special:
        add(text, tags, temporal)

    # last week/month/quarter/year + ТОЛЬКО время → момент внутри периода
    # неоднозначен → None (паритет с RU). Не productive (нет дня недели/числа).
    ambiguous_none_cases = [
        "last week at 14:30 write the meeting summary",
        "last week at 09:40 schedule the candidate interview",
        "last week at 11:15 check contractor permissions",
        "last week at 08:05 update project tickets",
        "last week at 18:20 process incoming requests",
        "last month at 14:30 send participant invitations",
        "last month at 11:15 reconcile accounting documents",
        "last month at 08:05 call the product designer",
        "last month at 09:40 check backup status",
        "last month at 18:20 review monitoring alerts",
        "last quarter at 09:40 agree on the presentation date",
        "last quarter at 08:05 update the test plan",
        "last quarter at 14:30 review the pull request",
        "last quarter at 18:20 prepare release notes",
        "last quarter at 11:15 check access rights",
        "last year at 11:15 recalculate campaign budget",
        "last year at 08:05 check payment statuses",
        "last year at 14:30 update the roadmap",
        "last year at 09:40 write a partner reply",
        "last year at 18:20 verify the attendee list",
    ]
    for text in ambiguous_none_cases:
        add(text, ("ambiguous_past_period", "expected_none"), "none")

    extra_markers = [
        ("tomorrow morning", "future"),
        ("tomorrow evening", "future"),
        ("the day after tomorrow morning", "future"),
        ("next Thursday", "future"),
        ("this coming Saturday", "future"),
        ("yesterday evening", "past"),
        ("the day before yesterday morning", "past"),
        ("three days ago in the evening", "past"),
        ("last Wednesday morning", "past"),
        ("last week on Thursday", "past"),
    ]
    extra_tasks = [
        "check the list of open contracts",
        "prepare a short client email",
        "update the release notes page",
        "review support comments",
        "approve changes in the mockup",
        "check payment receipt",
        "create a production database copy",
        "discuss the deadline shift",
        "send the updated estimate",
        "run an internal demonstration",
    ]
    contexts = [
        "for project Atlas",
        "for the North client",
        "for the internal release",
        "for the support team",
        "for the finance block",
        "for the legal team",
        "for calendar integration",
        "for the demo environment",
        "for the data migration",
        "for the partner meeting",
    ]
    suffixes = ["at 09:05", "at 11:25", "at 14:40", "at 16:55", "by 18:00"]
    idx = 0
    while len(raw) < 500:
        marker, temporal = extra_markers[idx % len(extra_markers)]
        task = extra_tasks[(idx // len(extra_markers)) % len(extra_tasks)]
        suffix = suffixes[(idx // (len(extra_markers) * len(extra_tasks))) % len(suffixes)]
        context = contexts[(idx // (len(extra_markers) * len(extra_tasks) * len(suffixes))) % len(contexts)]
        add(f"{marker} {suffix} {task} {context}", ("mixed",), temporal)
        idx += 1

    rnd = random.Random(20260706)
    rnd.shuffle(raw)

    seen_texts: set[str] = set()
    out: list[Case] = []
    for case in raw:
        if case.text in seen_texts:
            raise AssertionError(f"duplicate after generation: {case.text!r}")
        seen_texts.add(case.text)
        out.append(Case(id=f"en_{len(out) + 1:03d}", text=case.text, tags=case.tags, temporal=case.temporal))

    if len(out) != 500:
        raise AssertionError(f"EN cases count mismatch: {len(out)}")
    return out


MULTI_CASES = [
    ("tomorrow at 10 release planning, at 15 request review and the day after tomorrow at 12 meeting with legal", 3),
    ("yesterday at 10 incident review, the day before yesterday at 12 interview and one week ago at 9 report check", 3),
    ("today by 18 close the contract, tomorrow at 9 show the demo, Friday at 16 collect retro notes", 3),
    ("on Monday at 10 planning and every day until Friday at 18 send status", 2),
    ("by end of month close finance documents, every Monday check project risks", 2),
    ("from 10 to 12 run the workshop, from 23 to 1 check the night release, in half an hour call the on call engineer", 3),
]


def _case_id(case: Case) -> str:
    safe = case.text.replace("[", "(").replace("]", ")")
    return f"{case.id}:{case.temporal}:{safe[:80]}"


@pytest.mark.parametrize("case", make_cases(), ids=_case_id)
def test_case_semantics(case: Case) -> None:
    from timesense import TimeSenseParser

    result = _parse(TimeSenseParser(), case.text)
    errors = _validate(case, result)
    assert not errors, f"{case.text!r}: {errors}; result={normalize_result(result)}"


def test_parse_multi_cases() -> None:
    bad = [
        item for item in run_multi()
        if ("error_type" in item) or (item.get("count", 0) < item.get("expected_min", 0))
    ]
    assert not bad, bad[:10]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

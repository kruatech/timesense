# -*- coding: utf-8 -*-
"""Документация не должна расходиться с кодом: каждый пример командной строки
в README.md и README.ru.md (блоки ```console с `$ python -m timesense …`)
запускается и сравнивается с напечатанным выводом дословно.
Если README нет рядом (тесты запущены из sdist без них) — пропуск."""

import os
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
READMES = [ROOT / "README.md", ROOT / "README.ru.md"]


def _examples():
    out = []
    for fn in READMES:
        if not fn.is_file():
            continue
        txt = fn.read_text(encoding="utf-8")
        for block in re.findall(r"```console\n(.*?)```", txt, re.S):
            lines = block.rstrip("\n").split("\n")
            i = 0
            while i < len(lines):
                if lines[i].startswith("$ python -m timesense"):
                    cmd, exp = lines[i][2:], []
                    i += 1
                    while i < len(lines) and not lines[i].startswith("$ "):
                        if lines[i].strip():
                            exp.append(lines[i])
                        i += 1
                    out.append((fn.name, cmd, exp))
                else:
                    i += 1
    return out


EXAMPLES = _examples()


@pytest.mark.skipif(not EXAMPLES, reason="README рядом нет")
@pytest.mark.parametrize("readme,cmd,expected", EXAMPLES, ids=[f"{r}:{c[20:60]}" for r, c, _ in EXAMPLES])
def test_readme_cli_example(readme, cmd, expected, capsys):
    from timesense.__main__ import main

    args = shlex.split(cmd)[3:]  # после «python -m timesense»
    assert "--now" in args, f"{readme}: пример без --now не воспроизводим: {cmd}"
    main(args)
    got = [ln for ln in capsys.readouterr().out.rstrip("\n").split("\n") if ln.strip()]
    assert got == expected, f"{readme}: пример устарел\n  {cmd}"

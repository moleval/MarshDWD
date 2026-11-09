# -*- coding: utf-8 -*-
"""Таблицы «имя файла -> Этаж» и «марка -> цвет» через НАСТОЯЩИЙ LISP-код.

Функции md:floor-value / md:mark-color / md:layer-default берутся из
src/MARSHDWG.lsp и исполняются интерпретатором tools/lisp_sim.py.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
import lisp_sim  # noqa: E402
import test_names  # noqa: E402

SRC = HERE.parent / "src" / "MARSHDWG.lsp"


def main():
    sim = lisp_sim.load(SRC)
    floor = sim.build("md:floor-value")
    color = sim.build("md:mark-color")
    default = sim.build("md:layer-default")
    ok = True

    bad = [(n, floor(n), e) for n, e in test_names.FLOOR.items()
           if floor(n) != e]
    for n, got, exp in bad:
        print(f"FAIL Этаж({n!r}) = {got!r}, ожидалось {exp!r}")
    ok = ok and not bad
    print(f"{'OK  ' if not bad else 'FAIL'} имя файла -> атрибут: "
          f"{len(test_names.FLOOR)} случаев (из LISP)")

    bad = [(t, color(t), c) for t, c in test_names.COLORS.items()
           if color(t) != c]
    for t, got, exp in bad:
        print(f"FAIL цвет({t!r}) = {got!r}, ожидалось {exp!r}")
    ok = ok and not bad
    print(f"{'OK  ' if not bad else 'FAIL'} марка -> цвет: "
          f"{len(test_names.COLORS)} случаев (из LISP)")

    bad = [(l, default(l), c) for l, c in test_names.LAYER_DEFAULT.items()
           if default(l) != c]
    for l, got, exp in bad:
        print(f"FAIL цвет по слою({l!r}) = {got!r}, ожидалось {exp!r}")
    ok = ok and not bad
    print(f"{'OK  ' if not bad else 'FAIL'} слой -> цвет: "
          f"{len(test_names.LAYER_DEFAULT)} случаев (из LISP)")

    print("ИТОГ:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Структура и контракт MARSHDWG.lsp.

1. src и dist разбираются как LISP (формы, арности, CP1251/CRLF).
2. Ни один (defun не вложен в другой и скобки сходятся (полноценный
   токенизатор lisp_parse, а не подсчёт символов: `\"` он понимает).
3. Все вызовы md:* имеют defun, все defun md:* вызываются.
4. Все переменные *md:* объявлены и читаются.
5. Правила в коде совпадают с эталоном tests/check_rules.py.
"""
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lisp_parse  # noqa: E402
import check_rules  # noqa: E402

ROOT = HERE.parent
SRC = ROOT / "src" / "MARSHDWG.lsp"
DIST = ROOT / "dist" / "MARSHDWG.lsp"
EXPECT_DEFUN = 53


def top_level_defun(src):
    """Сколько defun стоит на верхнем уровне — по разобранному дереву."""
    forms = lisp_parse.parse(src)
    return sum(1 for f in forms
               if isinstance(f, list) and f and f[0].lower() == "defun")


def main():
    ok = True
    for path, enc, crlf in ((SRC, "utf-8", False), (DIST, "cp1251", True)):
        try:
            info = lisp_parse.check(path, encoding=enc, crlf=crlf)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {path}: {exc}")
            ok = False
            continue
        print(f"OK   {path.name} ({enc}): top-level={info['forms']}, "
              f"defun={info['defun']}, if={info['if']}, "
              f"foreach={info['foreach']}, while={info['while']}, "
              f"bytes={info['bytes']}")

    src = SRC.read_text(encoding="utf-8")

    # Незакрытая форма «проглатывает» следующие defun: для парсера это
    # валидное дерево, defun просто оказывается вложенным. Считаем не по
    # символам, а по разобранному дереву — lisp_parse понимает `\"` в строках.
    try:
        total = len(re.findall(r"\(defun\s+", src))
        top = top_level_defun(src)
        if top != total:
            print(f"FAIL проглоченные defun: {total - top} из {total} "
                  "вложены в другие формы")
            ok = False
        elif top != EXPECT_DEFUN:
            print(f"FAIL defun на верхнем уровне: {top}, ожидалось {EXPECT_DEFUN}"
                  " — если число изменено намеренно, поправьте EXPECT_DEFUN")
            ok = False
        else:
            print(f"OK   скобки: глубина 0, все {top} defun на верхнем уровне")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL разбор дерева: {exc}")
        ok = False

    if src.replace("\n", "\r\n").encode("cp1251") == DIST.read_bytes():
        print("OK   dist == src (CP1251/CRLF)")
    else:
        print("FAIL dist/MARSHDWG.lsp не совпадает с src — запустите tools/build.py")
        ok = False

    defined = set(re.findall(r"\(defun\s+(md:[^\s()]+)", src))
    called = set(re.findall(r"\((md:[^\s()]+)", src))
    undefined = sorted(called - defined)
    unused = sorted(defined - called)
    if undefined:
        print("FAIL вызовы без defun:", undefined)
        ok = False
    if unused:
        print("FAIL defun без вызова:", unused)
        ok = False
    if not undefined and not unused:
        print(f"OK   функций md:*: {len(defined)}, все вызываются")

    cmds = set(re.findall(r"\(defun\s+(c:[A-Za-zА-Яа-я0-9_]+)", src))
    expect = {"c:MARSHDWG", "c:MARSHDWGFILE", "c:MARSHDWGSRC", "c:MARSHDWGCFG"}
    if cmds == expect:
        print("OK   команды:", ", ".join(sorted(cmds)))
    else:
        print("FAIL команды:", sorted(cmds))
        ok = False

    declared = {"*md:" + n + "*"
                for n in re.findall(r"\(setq\s+\*md:([^*()\s]+)\*", src)}
    used = {"*md:" + n + "*"
            for n in re.findall(r"(?<![\w*-])\*md:([^*()\s]+)\*", src)}
    missing = sorted(used - declared)
    if missing:
        print("FAIL переменные без setq:", missing)
        ok = False
    else:
        print(f"OK   переменных *md:*: {len(declared)}")

    # Конфиг-параметры должны читаться в коде, а не только объявляться:
    # иначе флаг в README обещает то, чего код не делает.
    dead = sorted(n for n in ("recurse", "scan-paperspace", "require-backup")
                  if src.count(f"*md:{n}*") < 2)
    if dead:
        print("FAIL параметры объявлены, но не используются:", dead)
        ok = False
    else:
        print("OK   параметры *md:recurse*, *md:scan-paperspace*, "
              "*md:require-backup* используются")

    # зеркало правил
    checks = [
        (check_rules.OFF_LAYERS, "слои выключить"),
        (check_rules.GRAY_LAYERS, "слои серые"),
        (check_rules.DIM_LAYERS, "слои размеров"),
        (check_rules.PROD_LAYERS, "слои изделий"),
        (check_rules.ELEV_LAYERS, "слои отметок"),
    ]
    for lst, caption in checks:
        for name in lst:
            if f'"{name}"' not in src:
                print(f"FAIL нет слоя {name} ({caption})")
                ok = False
    for pat, col in check_rules.MARK_COLORS:
        if f'(cons "{pat}"' not in src:
            print(f"FAIL нет правила цвета {pat} -> {col}")
            ok = False
    for name, col in check_rules.PROD_DEFAULT:
        if f'"{name}" {col})' not in src:
            print(f"FAIL нет цвета по слою {name} -> {col}")
            ok = False
    simple = [
        (f'(setq *md:gray-color* {check_rules.GRAY_COLOR})', "цвет 251"),
        (f'(setq *md:grid-layer* "{check_rules.GRID_LAYER}")', "слой марок осей"),
        (f'(setq *md:grid-color* {check_rules.GRID_COLOR})', "цвет марок осей"),
        (f'(setq *md:elev-color* {check_rules.ELEV_COLOR})', "цвет отметок"),
        (f'(setq *md:dim-height* {check_rules.DIM_HEIGHT})', "H размеров"),
        (f'(setq *md:prod-height* {check_rules.PROD_HEIGHT})', "H изделий"),
        (f'(setq *md:block-name* "{check_rules.BLOCK_NAME}")', "имя блока"),
        (f'(setq *md:attr-tag* "{check_rules.ATTR_TAG}")', "тег атрибута"),
        (f'(setq *md:name-marker* "{check_rules.NAME_MARKER}")', "маркер имени"),
    ]
    for frag, caption in simple:
        if frag not in src:
            print(f"FAIL правило не совпадает: {caption} ({frag})")
            ok = False
    if ok:
        print("OK   правила LISP == tests/check_rules.py")

    print("ИТОГ:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Парсер AutoLISP: формы, строки, комментарии, арности, кодировка файла."""
from pathlib import Path

SPECIAL = {
    "defun": (3, None),      # имя, список аргументов, тело
    "lambda": (1, None),
    "if": (2, None),
    "cond": (1, None),
    "progn": (0, None),
    "foreach": (2, None),
    "while": (1, None),
    "repeat": (1, None),
    "setq": (2, None),
    "vl-catch-all-apply": (1, None),
}


def parse(text):
    forms, stack = [], []
    i, line, size = 0, 1, len(text)
    while i < size:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        if ch == ";":
            end = text.find("\n", i)
            i = size if end < 0 else end
            continue
        if ch == "'":
            i += 1
            continue
        if ch == "(":
            node = []
            (stack[-1] if stack else forms).append(node)
            stack.append(node)
            i += 1
            continue
        if ch == ")":
            if not stack:
                raise ValueError(f"лишняя ) в строке {line}")
            stack.pop()
            i += 1
            continue
        if ch == '"':
            end = i + 1
            while end < size:
                if text[end] == "\\":
                    end += 2
                    continue
                if text[end] == '"':
                    break
                if text[end] == "\n":
                    line += 1
                end += 1
            if end >= size:
                raise ValueError(f"незакрытая строка в строке {line}")
            (stack[-1] if stack else forms).append(text[i:end + 1])
            i = end + 1
            continue
        end = i
        while end < size and not text[end].isspace() and text[end] not in "();'\"":
            end += 1
        (stack[-1] if stack else forms).append(text[i:end])
        i = end
    if stack:
        raise ValueError(f"незакрытых форм: {len(stack)}")
    return forms


def walk(forms, stats, errors):
    for form in forms:
        if not isinstance(form, list):
            continue
        if form and isinstance(form[0], str):
            op = form[0].lower()
            stats[op] = stats.get(op, 0) + 1
            argc = len(form) - 1
            if op in SPECIAL:
                lo, hi = SPECIAL[op]
                if argc < lo or (hi is not None and argc > hi):
                    errors.append((op, argc))
        walk(form, stats, errors)


def check(path: Path, encoding="cp1251", crlf=True):
    raw = path.read_bytes()
    text = raw.decode(encoding)
    if text.startswith("\ufeff"):
        raise ValueError("BOM в файле")
    if "\ufffd" in text:
        raise ValueError("U+FFFD в файле")
    if crlf and b"\n" in raw and raw.count(b"\r\n") != raw.count(b"\n"):
        raise ValueError("не CRLF")
    forms = parse(text)
    stats, errors = {}, []
    walk(forms, stats, errors)
    if errors:
        raise ValueError(f"арности: {errors[:8]}")
    return {
        "forms": len(forms),
        "defun": stats.get("defun", 0),
        "if": stats.get("if", 0),
        "foreach": stats.get("foreach", 0),
        "while": stats.get("while", 0),
        "repeat": stats.get("repeat", 0),
        "bytes": len(raw),
        "lines": text.count("\r\n"),
    }

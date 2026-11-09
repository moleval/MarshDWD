# -*- coding: utf-8 -*-
"""Прогон «чистых» функций MARSHDWG.lsp без AutoCAD.

Читает defun прямо из src/MARSHDWG.lsp и интерпретирует подмножество
AutoLISP, которое там используется: setq, defun, if, cond, progn, and, or,
not, null, while, foreach, strcat, substr, strlen, strcase, wcmatch,
vl-string-search, vl-string-translate, vl-filename-base, vl-filename-directory,
list, cons/car/cdr, assoc, equal, type, арифметика.

Нужно, чтобы проверять логику в самом файле, а не её пересказ на Python.
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import lisp_parse  # noqa: E402


def wcmatch(s, pat):
    """Автокадовский wcmatch: * # ? [..] [~..]."""
    out, i = [], 0
    while i < len(pat):
        ch = pat[i]
        if ch == "*":
            out.append(".*")
        elif ch == "#":
            out.append("[0-9]")
        elif ch == "?":
            out.append(".")
        elif ch == "[":
            j = pat.index("]", i)
            body = pat[i + 1:j]
            out.append("[^" + body[1:] + "]" if body.startswith("~")
                       else "[" + body + "]")
            i = j
        else:
            out.append(re.escape(ch))
        i += 1
    return re.fullmatch("".join(out), s, re.S) is not None


def truth(v):
    """В AutoLISP ложь только nil; 0 и \"\" — истина."""
    return v is not None and v is not False


class Pair:
    """Точечная пара (cons a b), где b — не список."""

    def __init__(self, head, tail):
        self.head, self.tail = head, tail

    def __repr__(self):
        return f"({self.head!r} . {self.tail!r})"


class Env(dict):
    def __missing__(self, key):
        return None


class Sim:
    def __init__(self, src):
        self.forms = lisp_parse.parse(src)
        self.defs = {}
        for f in self.forms:
            if isinstance(f, list) and f and f[0].lower() == "defun":
                self.defs[f[1].lower()] = f
        self.globals = Env()
        self.load_globals()

    def load_globals(self):
        """Верхние (setq *md:...) — это и есть конфиг."""
        for f in self.forms:
            if isinstance(f, list) and f and f[0] == "setq":
                try:
                    self.eval(f, self.globals)
                except Exception:  # noqa: BLE001
                    pass

    def build(self, name):
        form = self.defs[name.lower()]
        decl = [p.lower() for p in form[2]]
        cut = decl.index("/") if "/" in decl else len(decl)
        params, locals_ = decl[:cut], decl[cut + 1:]
        body = form[3:]

        def run(*args):
            env = Env(self.globals)
            for p in locals_:
                env[p] = None
            for p, a in zip(params, args):
                env[p] = a
            return self.eval_seq(body, env)

        return run

    def eval_seq(self, forms, env):
        res = None
        for f in forms:
            res = self.eval(f, env)
        return res

    def eval(self, node, env):
        if isinstance(node, str):
            if node.startswith('"') and node.endswith('"'):
                return node[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            if re.fullmatch(r"-?\d+", node):
                return int(node)
            if re.fullmatch(r"-?\d+\.\d*", node):
                return float(node)
            if node.startswith("'"):
                return node[1:]
            if node.lower() == "nil":
                return None
            if node.lower() == "t":
                return True
            return env[node.lower()]
        if not isinstance(node, list) or not node:
            return None
        op = node[0].lower() if isinstance(node[0], str) else None
        args = node[1:]

        if op == "setq":
            val = None
            for i in range(0, len(args) - 1, 2):
                val = self.eval(args[i + 1], env)
                env[args[i].lower()] = val
            return val
        if op == "if":
            return (self.eval(args[1], env) if truth(self.eval(args[0], env))
                    else (self.eval(args[2], env) if len(args) > 2 else None))
        if op == "cond":
            for clause in args:
                if truth(self.eval(clause[0], env)):
                    return self.eval_seq(clause[1:], env)
            return None
        if op == "progn":
            return self.eval_seq(args, env)
        if op == "and":
            res = True
            for a in args:
                res = self.eval(a, env)
                if not truth(res):
                    return None
            return res
        if op == "or":
            for a in args:
                v = self.eval(a, env)
                if truth(v):
                    return v
            return None
        if op == "null":
            return None if truth(self.eval(args[0], env)) else True
        if op == "not":
            return None if truth(self.eval(args[0], env)) else True
        if op == "while":
            guard = 0
            while truth(self.eval(args[0], env)):
                self.eval_seq(args[1:], env)
                guard += 1
                if guard > 10000:
                    raise RuntimeError("while: предохранитель")
            return None
        if op == "foreach":
            var = args[0].lower()
            out = None
            for item in (self.eval(args[1], env) or []):
                env[var] = item
                out = self.eval_seq(args[2:], env)
            return out
        if op == "strcat":
            return "".join(str(self.eval(a, env)) for a in args)
        if op == "strlen":
            return len(str(self.eval(args[0], env) or ""))
        if op == "substr":
            s = str(self.eval(args[0], env) or "")
            start = int(self.eval(args[1], env) or 1)
            if len(args) > 2:
                return s[start - 1:start - 1 + int(self.eval(args[2], env))]
            return s[start - 1:]
        if op == "strcase":
            return str(self.eval(args[0], env) or "").upper()
        if op == "vl-string-search":
            pat = str(self.eval(args[0], env))
            s = str(self.eval(args[1], env))
            start = int(self.eval(args[2], env)) if len(args) > 2 else 0
            i = s.find(pat, start)
            return None if i < 0 else i
        if op == "vl-string-translate":
            a = str(self.eval(args[0], env))
            b = str(self.eval(args[1], env))
            return str(self.eval(args[2], env)).translate(str.maketrans(a, b))
        if op == "vl-filename-base":
            # у AutoLISP имя без .dwg остаётся как есть: «Объект ОП1.dwg» -> «Объект ОП1»
            p = re.split(r"[\\/]", str(self.eval(args[0], env)))[-1]
            return p[:-4] if p.lower().endswith(".dwg") else p
        if op == "vl-filename-directory":
            p = str(self.eval(args[0], env))
            return p.rsplit("\\", 1)[0] if "\\" in p else ""
        if op == "vl-princ-to-string":
            return str(self.eval(args[0], env))
        if op == "vl-string-right-trim":
            chars = str(self.eval(args[0], env))
            s = str(self.eval(args[1], env))
            return s.rstrip(chars)
        if op == "wcmatch":
            return wcmatch(str(self.eval(args[0], env) or ""),
                           str(self.eval(args[1], env) or ""))
        if op == "equal":
            a = self.eval(args[0], env)
            b = self.eval(args[1], env)
            if len(args) > 2:
                return abs((a or 0) - (b or 0)) <= self.eval(args[2], env)
            return a == b
        if op == "=":
            return self.eval(args[0], env) == self.eval(args[1], env)
        if op == "/=":
            return self.eval(args[0], env) != self.eval(args[1], env)
        if op == ">":
            return self.eval(args[0], env) > self.eval(args[1], env)
        if op == "<":
            return self.eval(args[0], env) < self.eval(args[1], env)
        if op == ">=":
            return self.eval(args[0], env) >= self.eval(args[1], env)
        if op == "<=":
            return self.eval(args[0], env) <= self.eval(args[1], env)
        if op == "type":
            v = self.eval(args[0], env)
            return {str: "STR", int: "INT", float: "REAL"}.get(type(v), "LIST")
        if op == "+":
            return sum(self.eval(a, env) or 0 for a in args)
        if op == "-":
            first = self.eval(args[0], env) or 0
            if len(args) == 1:
                return -first
            return first - sum(self.eval(a, env) or 0 for a in args[1:])
        if op == "1+":
            return (self.eval(args[0], env) or 0) + 1
        if op == "1-":
            v = self.eval(args[0], env)
            return (v if v is not None else 0) - 1
        if op == "atoi":
            m = re.match(r"\s*(-?\d+)", str(self.eval(args[0], env) or ""))
            return int(m.group(1)) if m else 0
        if op == "itoa":
            return str(int(self.eval(args[0], env) or 0))
        if op == "rtos":
            v = float(self.eval(args[0], env) or 0)
            prec = int(self.eval(args[2], env)) if len(args) > 2 else 2
            return f"{v:.{prec}f}"
        if op == "list":
            return [self.eval(a, env) for a in args]
        if op == "cons":
            head = self.eval(args[0], env)
            tail = self.eval(args[1], env)
            return [head] + tail if isinstance(tail, list) else Pair(head, tail)
        if op == "car":
            v = self.eval(args[0], env)
            if isinstance(v, Pair):
                return v.head
            return v[0] if v else None
        if op == "cdr":
            v = self.eval(args[0], env)
            if isinstance(v, Pair):
                return v.tail
            return v[1:] if isinstance(v, list) else None
        if op == "nth":
            return self.eval(args[1], env)[self.eval(args[0], env)]
        if op == "length":
            return len(self.eval(args[0], env) or [])
        if op == "assoc":
            key = self.eval(args[0], env)
            for pair in (self.eval(args[1], env) or []):
                if isinstance(pair, Pair) and pair.head == key:
                    return pair
                if isinstance(pair, list) and pair and pair[0] == key:
                    return pair
            return None
        if op == "subst":
            new, old, lst = (self.eval(a, env) for a in args)
            return [new if x == old else x for x in (lst or [])]
        if op == "append":
            out = []
            for a in args:
                out += list(self.eval(a, env) or [])
            return out
        if op == "princ":
            return None
        if op in self.defs:
            return self.build(op)(*[self.eval(a, env) for a in args])
        raise NotImplementedError(f"оператор {op} в {node}")


def load(src_path):
    return Sim(Path(src_path).read_text(encoding="utf-8"))

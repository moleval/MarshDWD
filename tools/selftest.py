# -*- coding: utf-8 -*-
"""Полная проверка MARSHDWG без AutoCAD — одной командой.

    python3 tools/selftest.py

Что делает:

1. собирает dist из src и сверяет размер/хэш;
2. гоняет tests/structure.py, tests/test_lisp_logic.py;
3. строит тестовый DXF-чертёж и источник блока («Марка этажа»);
4. прогоняет правила (tools/dryrun.py) и проверяет результат по пунктам:
   слои, цвета, высоты, маски, фон штриховок, блок и атрибут «Этаж»;
5. второй прогон — все счётчики по нулям (идемпотентность);
6. проверяет md:collect на реальной папке: рекурсия и исключение
   MARSHDWG_BACKUP.

Коды выхода: 0 — всё OK, 1 — есть провалы (они перечислены).
DXF — не DWG: это проверка правил, а не результат в AutoCAD.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))


def sh(*args):
    """Команда в корне репозитория; вывод печатаем и возвращаем успех."""
    r = subprocess.run([sys.executable, *args], cwd=ROOT,
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    for line in out.splitlines():
        print("   ", line)
    return r.returncode == 0


def main():
    ok = True

    print("=== 1. сборка dist из src ===")
    ok &= sh("tools/build.py")

    print("=== 2. тесты ===")
    ok &= sh("tests/structure.py")
    ok &= sh("tests/test_lisp_logic.py")

    print("=== 3. тестовый чертёж и источник блока ===")
    ok &= sh("tools/make_test_dxf.py")

    print("=== 4. прогон правил (первый раз) ===")
    ok &= sh("tools/dryrun.py", "out/test/Тест ОП1.dxf",
             "out/test/Марка этажа.dxf", "out/test", "Тест ОП1.dwg")

    print("=== 5. проверка результата по пунктам ===")
    from ezdxf import recover
    import check_rules as R
    import dryrun

    out = ROOT / "out" / "test" / "Тест ОП1 (проверка).dxf"
    doc, _ = recover.readfile(str(out))
    fails = []

    # п.1 слои выключены, но не заморожены
    for n in R.OFF_LAYERS:
        if n in doc.layers:
            lay = doc.layers.get(n)
            if not lay.is_off():
                fails.append(f"слой {n} не выключен")
            if lay.is_frozen():
                fails.append(f"слой {n} заморожен (нельзя)")
    # п.2 серые
    for n in R.GRAY_LAYERS:
        if n in doc.layers and doc.layers.get(n).dxf.color != R.GRAY_COLOR:
            fails.append(f"слой {n} не серый {R.GRAY_COLOR}")

    def height(e, t):
        return e.dxf.get("height") if t == "TEXT" else e.dxf.get("char_height")

    colored = {}
    for e in dryrun.iter_entities(doc):
        t, lay = e.dxftype(), e.dxf.layer.upper()
        if t in ("MTEXT", "TEXT", "ATTRIB"):
            if t == "MTEXT" and e.dxf.get("bg_fill", 0) == 1:
                fails.append(f"маска осталась: {lay}")
            if lay in R.DIM_LAYERS and abs(height(e, t) - 250) > 1e-6:
                fails.append(f"H размера {lay} = {height(e, t)}, ждали 250")
            if lay in R.PROD_LAYERS:
                if abs(height(e, t) - 225) > 1e-6:
                    fails.append(f"H изделия {lay} = {height(e, t)}, ждали 225")
                txt = e.plain_text() if t == "MTEXT" else e.dxf.text
                colored[txt] = e.dxf.color
            if lay in R.ELEV_LAYERS:
                if abs(height(e, t) - 250) > 1e-6:
                    fails.append(f"H отметки = {height(e, t)}, ждали 250")
                if e.dxf.color != R.ELEV_COLOR:
                    fails.append(f"отметка цвет {e.dxf.color}, ждали 200")
            if lay == R.GRID_LAYER and e.dxf.color != R.GRID_COLOR:
                fails.append(f"марка оси цвет {e.dxf.color}, ждали 1")
        if t == "HATCH" and e.bgcolor is not None:
            fails.append("у штриховки остался фон")

    want = {"ДВ-1": 5, "ДГ-2": 5, "ОК-1": 2, "ББ-1": 2, "Б-2": 2,
            "ОЛ-3.1": 4, "ВТ-2": 3, "ДПВ EI30": 1, "А": 2}
    for mark, exp in want.items():
        got = colored.get(mark)
        if got != exp:
            fails.append(f"марка {mark}: цвет {got}, ждали {exp}")

    # контрольный слой не трогаем
    for e in doc.modelspace():
        if e.dxftype() == "TEXT" and e.dxf.layer == "A-WALL":
            if abs(e.dxf.height - 321) > 1e-6 or e.dxf.color != 256:
                fails.append("текст на A-WALL изменён, а не должен")

    # блок: точка 0,0, масштаб 1, атрибут «Этаж»
    refs = [e for e in doc.modelspace()
            if e.dxftype() == "INSERT" and e.dxf.name == R.BLOCK_NAME]
    if len(refs) != 1:
        fails.append(f"вставок «{R.BLOCK_NAME}»: {len(refs)}, ждали 1")
    else:
        ref = refs[0]
        if tuple(ref.dxf.insert)[:2] != (0.0, 0.0):
            fails.append(f"блок вставлен в {tuple(ref.dxf.insert)[:2]}, ждали 0,0")
        if abs(ref.dxf.xscale - 1.0) > 1e-9:
            fails.append(f"масштаб блока {ref.dxf.xscale}, ждали 1.0")
        atts = {a.dxf.tag: a.dxf.text for a in ref.attribs}
        if atts.get(R.ATTR_TAG) != "1":
            fails.append(f"атрибут «{R.ATTR_TAG}» = {atts.get(R.ATTR_TAG)!r}, ждали '1'")

    for f in fails:
        print("    FAIL", f)
    if fails:
        ok = False
    else:
        print(f"    OK   пункты правил: слои, цвета, высоты, маски, штриховки,"
              f" блок и атрибут ({len(want)} марок)")

    print("=== 6. повторный прогон (должны быть нули) ===")
    doc2, _ = recover.readfile(str(out))
    again = dryrun.apply_rules(doc2)
    extra = {k: v for k, v in again.items() if k != "dim"}
    print("    счётчики:", again)
    if extra:
        for k, v in extra.items():
            print("    FAIL повторно изменилось:", k, v)
        ok = False
    else:
        print("    OK   идемпотентность: меняется только счётчик «размеров»")

    print("=== 7. md:collect: рекурсия и MARSHDWG_BACKUP ===")
    ok &= check_collect()

    print()
    print("ИТОГ:", "OK" if ok else "FAIL")
    return 0 if ok else 1


def check_collect():
    import lisp_sim

    src = (ROOT / "src" / "MARSHDWG.lsp").read_text(encoding="utf-8")
    i = src.index("(defun md:collect ")
    body = src[i:src.index("\n\n", i)]
    head = ('(setq *md:recurse* %s)\n'
            '(setq *md:backup-subdir* "MARSHDWG_BACKUP")\n')

    root = Path(tempfile.mkdtemp())
    for name in ("a.dwg", "b.dwg"):
        (root / name).write_bytes(b"x")
    (root / "sub").mkdir()
    (root / "sub" / "c.dwg").write_bytes(b"x")
    (root / "sub" / "deep").mkdir()
    (root / "sub" / "deep" / "d.dwg").write_bytes(b"x")
    (root / "MARSHDWG_BACKUP").mkdir()
    (root / "MARSHDWG_BACKUP" / "old.dwg").write_bytes(b"x")

    names = lambda lst: sorted(Path(p).name for p in lst)  # noqa: E731
    flat = lisp_sim.Sim((head % "nil") + body).build("md:collect")(str(root))
    deep = lisp_sim.Sim((head % "t") + body).build("md:collect")(str(root))
    ok = True
    if names(flat) != ["a.dwg", "b.dwg"]:
        print("    FAIL recurse=nil:", names(flat))
        ok = False
    if not ("c.dwg" in names(deep) and "d.dwg" in names(deep)):
        print("    FAIL recurse=t не обошёл вложенные папки:", names(deep))
        ok = False
    if "old.dwg" in names(deep):
        print("    FAIL recurse=t затянул MARSHDWG_BACKUP:", names(deep))
        ok = False
    if ok:
        print("    OK   recurse=nil — только папка; recurse=t — вложенные,"
              " MARSHDWG_BACKUP исключён")
    return ok


if __name__ == "__main__":
    sys.exit(main())

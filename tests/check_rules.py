# -*- coding: utf-8 -*-
"""Правила обработчика в терминах содержимого DWG (эталон для сверки).

Читает JSON-дамп LibreDWG и проверяет, что в файле есть всё, к чему
обращаются правила: слои, марки осей, размеры, обозначения изделий,
отметки, штриховки, блок «Марка этажа» и атрибут «Этаж».

Запуск: python3 tests/check_rules.py dump/op1.json --name "Объект ОП1.dwg"
        python3 tests/check_rules.py --source dump/mark.json
"""
from pathlib import Path
import json
import re
import sys

# --- правила (зеркало конфиг-блока MARSHDWG.lsp) -----------------------------
OFF_LAYERS = ["A-ANNO-NOTE", "A-AREA-IDEN", "A-DETL", "A-FLOR-IDEN",
              "G-ANNO-NOTE", "G-ANNO-REVC", "G-ANNO-REVC-IDEN", "G-ANNO-TEXT",
              "I-FURN", "P-SANR-FIXT"]
GRAY_COLOR = 251
GRAY_LAYERS = ["A-ANNO-DIMS", "A-ANNO-DIMS-100", "S-GRID", "S-GRID-IDEN"]
GRID_LAYER, GRID_COLOR = "S-GRID-IDEN", 1
DIM_HEIGHT = 250.0
DIM_LAYERS = ["A-ANNO-DIMS", "A-ANNO-DIMS-100", "G-ANNO-DIMS"]
PROD_HEIGHT = 225.0
PROD_LAYERS = ["A-DOOR-IDEN", "A-GLAZ-IDEN", "A-WALL-IDEN"]
MARK_COLORS = [("*EI*", 1), ("Д*", 5), ("ОК*", 2), ("ББ*", 2), ("Б*", 2),
               ("ОЛ*", 4), ("ВТ*", 3)]
PROD_DEFAULT = [("A-GLAZ-IDEN", 2), ("A-DOOR-IDEN", 5), ("A-WALL-IDEN", 3)]
ELEV_LAYERS, ELEV_COLOR = ["G-ANNO-DIMS"], 200
BLOCK_NAME, ATTR_TAG = "Марка этажа", "Этаж"
NAME_MARKER = "ОП"


# --- чтение дампа ------------------------------------------------------------
def hid(x):
    return x[2] if isinstance(x, list) else x


def load(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    objs = d["OBJECTS"]
    layers = {hid(o["handle"]): o["name"] for o in objs if o.get("object") == "LAYER"}
    blocks = {hid(o["handle"]): o for o in objs if o.get("object") == "BLOCK_HEADER"}
    return d, objs, layers, blocks


def layer_of(o, layers):
    lay = o.get("layer")
    return layers.get(hid(lay)) if isinstance(lay, list) else lay


def plain(s):
    s = s or ""
    s = re.sub(r"\\[A-Za-z][^;]*;", "", s)
    s = s.replace("\\P", " ").replace("{", "").replace("}", "")
    return s.strip()


def mark_color(text):
    u = plain(text).upper()
    for pat, col in MARK_COLORS:
        if re.fullmatch(pat.replace("*", ".*"), u):
            return col
    return None


def floor_value(name):
    """Атрибут «Этаж»: часть имени после последнего «ОП»; None если «ОП» нет."""
    base = Path(name).stem if str(name).lower().endswith(".dwg") else str(name)
    up = base.upper()
    i = up.rfind(NAME_MARKER)
    if i < 0:
        return None
    before = up[i - 1] if i > 0 else " "
    if before.isalnum():          # ПОП1, АОП1 — это не «...ОП<этаж>»
        return None
    val = base[i + len(NAME_MARKER):].strip()
    return val or None


def block_entities(bh, objs_by_handle):
    return [objs_by_handle[hid(ref)] for ref in (bh.get("entities") or [])
            if hid(ref) in objs_by_handle]


# --- проверка ---------------------------------------------------------------
def check(path, mode="target"):
    d, objs, layers, blocks = load(path)
    by_h = {hid(o["handle"]): o for o in objs}
    names = set(layers.values())
    report = {"layers": {}, "counts": {}, "issues": []}

    for name in OFF_LAYERS + GRAY_LAYERS:
        report["layers"][name] = "ок" if name in names else "нет в файле"

    cnt = {k: 0 for k in ("grid", "dim", "dim_text", "prod", "elev", "hatch",
                          "prod_colored", "unmapped_marks")}
    prod_texts = []
    for o in objs:
        ent = o.get("entity")
        lay = layer_of(o, layers)
        if ent == "HATCH":
            cnt["hatch"] += 1
        elif ent and ent.startswith("DIMENSION"):
            cnt["dim"] += 1
        elif lay == GRID_LAYER:
            cnt["grid"] += 1
        elif ent in ("MTEXT", "TEXT"):
            if lay in ELEV_LAYERS:
                cnt["elev"] += 1
            elif lay in DIM_LAYERS:
                cnt["dim_text"] += 1
            elif lay in PROD_LAYERS:
                cnt["prod"] += 1
                txt = o.get("text")
                if isinstance(txt, list):
                    txt = "".join(map(str, txt))
                prod_texts.append(plain(txt))
                if mark_color(txt) or dict(PROD_DEFAULT).get(lay):
                    cnt["prod_colored"] += 1

    # марки идут парами «ДВ» + «-1»: склеиваем подряд идущие по Y
    pairs, i = [], 0
    while i < len(prod_texts):
        a = prod_texts[i]
        b = prod_texts[i + 1] if i + 1 < len(prod_texts) else ""
        pairs.append(a + b if b.startswith("-") else a)
        i += 2 if b.startswith("-") else 1
    for p in pairs:
        if mark_color(p) is None:
            cnt["unmapped_marks"] += 1
            report["issues"].append(
                f"марка {p}: под шаблон не подошла, цвет по слою "
                "(ожидаемо для одиночных «А»/«Б» на A-GLAZ-IDEN)")
    report["counts"] = cnt
    report["pairs"] = pairs

    bh = next((b for b in blocks.values() if b.get("name") == BLOCK_NAME), None)
    if bh is None and mode == "source":
        report["issues"].append("блок «Марка этажа» не найден")
        report["block"] = None
    elif bh is None:
        report["block"] = None
    else:
        ents = block_entities(bh, by_h)
        tags = [e.get("tag") for e in ents if e.get("entity") == "ATTDEF"]
        atts = [e.get("tag") for e in ents if e.get("entity") == "ATTRIB"]
        report["block"] = {
            "name": BLOCK_NAME,
            "attdef": tags,
            "attrib": atts,
            "entities": len(ents),
            "inserts": len(bh.get("inserts") or []),
            "base_pt": bh.get("base_pt"),
        }
        if ATTR_TAG not in tags:
            report["issues"].append(f"в блоке нет атрибута «{ATTR_TAG}»")
    return report


def main(argv):
    mode, files, given = "target", [], None
    it = iter(argv)
    for a in it:
        if a in ("--source", "--target"):
            mode = a[2:]
        elif a == "--name":
            given = next(it, None)
        else:
            files.append(a)
    ok = True
    for p in files:
        rep = check(p, mode)
        print(f"=== {p}")
        absent = [k for k, v in rep["layers"].items() if v != "ок"]
        print("  нет слоёв:", ", ".join(absent) if absent else "— (все 14 на месте)")
        print("  счётчики:", rep["counts"])
        if rep["pairs"]:
            print("  марки:", ", ".join(sorted(set(rep["pairs"]))))
        if rep["block"]:
            print("  блок:", rep["block"])
        if mode == "target":
            val = floor_value(given or p)
            print("  атрибут «Этаж»:", repr(val))
            if Path(given or p).stem.upper().find(NAME_MARKER) >= 0 and not val:
                ok = False
                print("  [ОШИБКА] маркер «ОП» в имени есть, а значение пустое")
        for i in rep["issues"]:
            print("  [i]", i)
        print("  [OK]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

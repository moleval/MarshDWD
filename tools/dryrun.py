# -*- coding: utf-8 -*-
"""Сухой прогон (предпросмотр) без AutoCAD.

Берёт DXF-конверсию реального DWG, применяет те же правила, что
MARSHDWG.lsp, копирует блок «Марка этажа» из источника, вставляет его в 0,0
с атрибутом «Этаж» и сохраняет out/<имя> (проверка).dxf.

DXF — только чтобы посмотреть глазами; рабочий результат даёт LISP на DWG.
"""
from pathlib import Path
import sys

from ezdxf import recover
from ezdxf.addons import Importer
from ezdxf.entities import Material

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import check_rules as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def layer_color(doc, name, index):
    """Индексный цвет; true_color мешает — снимаем."""
    if name in doc.layers:
        lay = doc.layers.get(name)
        lay.dxf.color = index
        if lay.dxf.hasattr("true_color"):
            lay.dxf.discard("true_color")


def layer_off(doc, name):
    if name in doc.layers:
        lay = doc.layers.get(name)
        c = lay.dxf.get("color", 7)
        lay.dxf.color = -abs(c) if 0 < abs(c) <= 255 else -7


def ensure_tables(doc):
    """Importer требует материалы в целевом документе.

    DXF из LibreDWG ссылается на MATERIAL по handle, а сами объекты в файл не
    попадают — досоздаём их на тех же handle.
    """
    dct = doc.rootdict.get("ACAD_MATERIAL")
    if dct is None:
        return
    for name, handle in list(dct.items()):
        if doc.entitydb.get(handle) is None:
            Material.new(doc=doc, handle=handle, dxfattribs={"name": name})


def apply_rules(doc):
    stats = {}
    for n in R.OFF_LAYERS:
        layer_off(doc, n)
    for n in R.GRAY_LAYERS:
        layer_color(doc, n, R.GRAY_COLOR)
    layer_color(doc, R.GRID_LAYER, R.GRID_COLOR)

    for ds in doc.dimstyles:
        ds.dxf.dimtfill = 0            # фон «нет»
        ds.dxf.dimtxt = R.DIM_HEIGHT   # высота текста размера

    for e in doc.modelspace():
        t = e.dxftype()
        lay = e.dxf.layer.upper()
        if t in ("MTEXT", "TEXT", "ATTRIB"):
            if t == "MTEXT" and e.dxf.get("bg_fill", 0) == 1:
                e.dxf.bg_fill = 0      # маска -> нет фона
                stats["bg_off"] = stats.get("bg_off", 0) + 1
            if lay in R.ELEV_LAYERS:
                e.dxf.char_height = R.DIM_HEIGHT
                e.dxf.color = R.ELEV_COLOR
                stats["elev"] = stats.get("elev", 0) + 1
            elif lay in R.DIM_LAYERS:
                e.dxf.char_height = R.DIM_HEIGHT
                stats["dim_text"] = stats.get("dim_text", 0) + 1
            elif lay in R.PROD_LAYERS:
                e.dxf.char_height = R.PROD_HEIGHT
                txt = e.plain_text() if t == "MTEXT" else e.dxf.get("text", "")
                col = R.mark_color(txt) or dict(R.PROD_DEFAULT).get(lay)
                if col:
                    e.dxf.color = col
                stats["prod"] = stats.get("prod", 0) + 1
        elif t == "HATCH":
            stats["hatch"] = stats.get("hatch", 0) + 1
        elif t.startswith("DIMENSION"):
            stats["dim"] = stats.get("dim", 0) + 1
        elif lay == R.GRID_LAYER:
            e.dxf.color = R.GRID_COLOR
            stats["grid"] = stats.get("grid", 0) + 1
        elif lay in R.ELEV_LAYERS:
            e.dxf.color = R.ELEV_COLOR
            stats["elev"] = stats.get("elev", 0) + 1
    return stats


def copy_mark_block(src_path, dst_doc, floor, at=(0, 0, 0), scale=1.0):
    src, _ = recover.readfile(str(src_path))
    ensure_tables(dst_doc)
    imp = Importer(src, dst_doc)
    imp.import_block(R.BLOCK_NAME)
    imp.finalize()
    ref = dst_doc.modelspace().add_blockref(
        R.BLOCK_NAME, at,
        dxfattribs={"xscale": scale, "yscale": scale, "zscale": scale})
    ref.add_auto_attribs({R.ATTR_TAG: floor})
    return ref


def main(dxf_in, dxf_src, out_dir, name):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc, _ = recover.readfile(str(dxf_in))
    floor = R.floor_value(name) or "?"
    print("правила:", apply_rules(doc))
    ref = copy_mark_block(dxf_src, doc, floor)
    print(f"блок вставлен: {R.BLOCK_NAME} @ {tuple(ref.dxf.insert)[:2]}, "
          f"поле «{R.ATTR_TAG}» = {floor}")
    out = out_dir / f"{Path(name).stem} (проверка).dxf"
    doc.saveas(str(out))
    print("сохранено:", out, out.stat().st_size, "байт")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        raise SystemExit(2)
    main(a[0], a[1], a[2] if len(a) > 2 else ROOT / "out",
         a[3] if len(a) > 3 else Path(a[0]).stem)

# -*- coding: utf-8 -*-
"""Сухой прогон (предпросмотр) без AutoCAD.

Берёт DXF-конверсию реального DWG, применяет те же правила, что
MARSHDWG.lsp, копирует блок «Марка этажа» из источника, вставляет его в 0,0
с атрибутом «Этаж» и сохраняет out/<имя> (проверка).dxf.

DXF — только чтобы посмотреть глазами; рабочий результат даёт LISP на DWG.

Важно: правила здесь повторяют LISP по порядку из md:do-obj и считают
изменения только по факту (второй прогон даёт нули) — иначе предпросмотр
расходится с тем, что делает MARSHDWG.lsp.
"""
from pathlib import Path
import sys

from ezdxf import recover
from ezdxf.addons import Importer
from ezdxf.entities import Material

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import check_rules as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# --- служебное ---------------------------------------------------------------
def bump(stats, key, changed):
    """Счётчик растёт только если правило действительно что-то изменило."""
    if changed:
        stats[key] = stats.get(key, 0) + 1
    return changed


def iter_entities(doc):
    """Модель + определения блоков (LISP обходит и их), без листов и xref."""
    yield from doc.modelspace()
    for blk in doc.blocks:
        if blk.name.lower().startswith("*"):
            continue
        yield from blk


def set_height(e, t, h):
    attr = "height" if t == "TEXT" else "char_height"
    if abs((e.dxf.get(attr) or 0) - h) < 1e-9:
        return False
    e.dxf.set(attr, h)
    return True


def set_color(e, c):
    if e.dxf.get("color") == c:
        return False
    e.dxf.color = c
    return True


def layer_color(doc, name, index):
    """Индексный цвет слоя; true_color мешает — снимаем. True = было изменение."""
    if name not in doc.layers:
        return False
    lay = doc.layers.get(name)
    changed = lay.dxf.get("color") != index or lay.dxf.hasattr("true_color")
    lay.dxf.color = index
    if lay.dxf.hasattr("true_color"):
        lay.dxf.discard("true_color")
    return changed


def layer_off(doc, name):
    """Выключить слой: только видимость, без заморозки и блокировки."""
    if name not in doc.layers:
        return False
    lay = doc.layers.get(name)
    if lay.is_off():
        return False
    c = lay.dxf.get("color", 7)
    lay.dxf.color = -abs(c) if 0 < abs(c) <= 255 else -7
    return True


def hatch_bg_off(hatch):
    """Фон штриховки «Нет».

    В DXF активный фон — это XDATA HATCHBACKGROUNDCOLOR (ezdxf: .bgcolor),
    поэтому «нет фона» = XDATA отсутствует. В LISP то же самое: ColorMethod
    = None (0xC8) в BackgroundColor.
    """
    try:
        if hatch.bgcolor is None:
            return False
        del hatch.bgcolor
        return True
    except Exception:  # noqa: BLE001 — нет XDATA / старая версия DXF
        return False


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


# --- правила -----------------------------------------------------------------
def apply_rules(doc):
    stats = {}

    for n in R.OFF_LAYERS:
        bump(stats, "layers_off", layer_off(doc, n))
    for n in R.GRAY_LAYERS:
        bump(stats, "layers_gray", layer_color(doc, n, R.GRAY_COLOR))
    # Слой марок осей получает 251 (п.2), а его объекты — 1 (п.3): цвет слоя
    # красным не делаем, иначе предпросмотр расходится с LISP.
    layer_color(doc, R.GRID_LAYER, R.GRAY_COLOR)

    for ds in doc.dimstyles:
        if ds.dxf.get("dimtfill", 0) != 0:
            ds.dxf.dimtfill = 0                       # фон «нет»
            bump(stats, "dimstyle", True)
        if abs((ds.dxf.get("dimtxt") or 0) - R.DIM_HEIGHT) > 1e-9:
            ds.dxf.dimtxt = R.DIM_HEIGHT              # высота текста размера
            bump(stats, "dimstyle", True)

    for e in iter_entities(doc):
        t = e.dxftype()
        lay = e.dxf.layer.upper()

        if t == "HATCH":
            bump(stats, "hatch", hatch_bg_off(e))
        elif t.startswith("DIMENSION"):
            stats["dim"] = stats.get("dim", 0) + 1   # «сколько размеров», не изменение
        elif lay == R.GRID_LAYER:
            # как md:do-obj: марки осей проверяются раньше текстов
            bump(stats, "grid", set_color(e, R.GRID_COLOR))
        elif lay in R.ELEV_LAYERS and t not in ("MTEXT", "TEXT", "ATTRIB"):
            bump(stats, "elev", set_color(e, R.ELEV_COLOR))
        elif t in ("MTEXT", "TEXT", "ATTRIB"):
            if t == "MTEXT" and e.dxf.get("bg_fill", 0) == 1:
                e.dxf.bg_fill = 0                     # маска -> нет фона
                bump(stats, "bg_off", True)
            if lay in R.ELEV_LAYERS:
                bump(stats, "height", set_height(e, t, R.DIM_HEIGHT))
                bump(stats, "elev", set_color(e, R.ELEV_COLOR))
            elif lay in R.DIM_LAYERS:
                bump(stats, "dim_text", set_height(e, t, R.DIM_HEIGHT))
            elif lay in R.PROD_LAYERS:
                bump(stats, "prod", set_height(e, t, R.PROD_HEIGHT))
                txt = e.plain_text() if t == "MTEXT" else e.dxf.get("text", "")
                col = R.mark_color(txt) or dict(R.PROD_DEFAULT).get(lay)
                if col:
                    bump(stats, "color", set_color(e, col))
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

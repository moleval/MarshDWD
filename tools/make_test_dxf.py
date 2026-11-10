# -*- coding: utf-8 -*-
"""Сборка тестовых DXF для прогона MARSHDWG без реальных DWG.

Делает два файла, повторяющие структуру боевых:

    out/test/Тест ОП1.dxf        — «обрабатываемый» чертёж
    out/test/Марка этажа.dxf     — источник блока «Марка этажа» (ATTDEF «Этаж»)

В тестовом чертеже есть по одному объекту каждого типа, который трогают
правила, плюс «ловушки»:

* все 10 слоёв на выключение и 4 серых слоя;
* марки осей: MTEXT и объект внутри блока «Ось сетки» (проверка обхода блоков);
* тексты размеров, изделий (ДВ-1, ОК-2, ББ-1, ОЛ-3.1, ВТ-2, EI30, «А», «7»),
  отметки +0,000 и -0,010;
* текст с маской (MTEXT bg_fill) — должен потерять фон;
* штриховка с Solid-заливкой — фон должен стать «Нет»;
* размер со стилем — DIMTFILL = 0;
* слой S-GRID-IDEN одновременно в «серых» и в «марках осей»;
* слой, которого нет в правилах (контроль, что не трогаем лишнего).

Запуск:

    python3 tools/make_test_dxf.py
    python3 tools/dryrun.py out/test/"Тест ОП1.dxf" out/test/"Марка этажа.dxf" \
        out/test "Тест ОП1.dwg"
"""
from pathlib import Path
import sys

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import check_rules as R  # noqa: E402

OUT = ROOT / "out" / "test"


def ensure_layer(doc, name, color=7):
    if name not in doc.layers:
        doc.layers.add(name, color=color)


def build_source():
    """Источник: блок «Марка этажа» с ATTDEF «Этаж», текст 2400 (решение заказчика)."""
    doc = ezdxf.new("R2013", setup=True)
    blk = doc.blocks.new(name=R.BLOCK_NAME, base_point=(0, 0, 0))
    blk.add_attdef(
        tag=R.ATTR_TAG,
        insert=(0, 0),
        text="",
        height=2400,
        dxfattribs={"layer": "0"},
    )
    # рамка марки, чтобы блок был виден на предпросмотре
    blk.add_lwpolyline([(-3000, -3000), (3000, -3000), (3000, 3000), (-3000, 3000)],
                       close=True, dxfattribs={"layer": "0"})
    path = OUT / "Марка этажа.dxf"
    doc.saveas(str(path))
    return path


def build_target():
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 4  # миллиметры

    for name in R.OFF_LAYERS + R.GRAY_LAYERS + R.DIM_LAYERS + \
            R.PROD_LAYERS + R.ELEV_LAYERS + [R.GRID_LAYER, "A-WALL", "0"]:
        ensure_layer(doc, name)

    msp = doc.modelspace()

    # --- марки осей: MTEXT на слое + содержимое блока -----------------------
    msp.add_mtext("1", dxfattribs={"layer": R.GRID_LAYER, "char_height": 250,
                                   "insert": (0, 5000)})
    msp.add_mtext("А", dxfattribs={"layer": R.GRID_LAYER, "char_height": 250,
                                   "insert": (5000, 0)})
    grid = doc.blocks.new(name="Ось сетки")
    grid.add_mtext("2", dxfattribs={"layer": R.GRID_LAYER, "char_height": 250,
                                    "insert": (0, 0)})
    grid.add_line((0, 0), (0, 1000), dxfattribs={"layer": R.GRID_LAYER})
    msp.add_blockref("Ось сетки", (10000, 0))

    # --- тексты размеров ----------------------------------------------------
    for i, txt in enumerate(("1200", "3400", "5600")):
        msp.add_text(txt, height=180,
                     dxfattribs={"layer": "A-ANNO-DIMS", "insert": (0, -2000 * i)})

    # --- обозначения изделий: все ветки таблицы цветов ----------------------
    marks = [("ДВ-1", "A-DOOR-IDEN"), ("ДГ-2", "A-DOOR-IDEN"),
             ("ОК-1", "A-GLAZ-IDEN"), ("ББ-1", "A-GLAZ-IDEN"),
             ("Б-2", "A-GLAZ-IDEN"), ("ОЛ-3.1", "A-GLAZ-IDEN"),
             ("ВТ-2", "A-WALL-IDEN"), ("ДПВ EI30", "A-DOOR-IDEN"),
             ("А", "A-GLAZ-IDEN"), ("7", "A-GLAZ-IDEN")]
    for i, (txt, lay) in enumerate(marks):
        msp.add_text(txt, height=180,
                     dxfattribs={"layer": lay, "insert": (2000 * i, 3000)})

    # --- отметки: фиолетовый 200 + высота 250 -------------------------------
    for i, txt in enumerate(("+0,000", "-0,010")):
        msp.add_text(txt, height=180,
                     dxfattribs={"layer": "G-ANNO-DIMS",
                                 "insert": (2000 * i, -3000)})

    # --- маска текста: должна сняться --------------------------------------
    mtext = msp.add_mtext("Текст с маской", dxfattribs={
        "layer": "A-ANNO-NOTE", "char_height": 200, "insert": (0, 6000)})
    mtext.dxf.bg_fill = 1          # 1 = цвет фона чертежа (маска включена)

    # --- штриховка: фон должен стать «Нет» ---------------------------------
    hatch = msp.add_hatch(color=8, dxfattribs={"layer": "A-AREA-IDEN"})
    hatch.set_solid_fill(color=8)
    hatch.bgcolor = (255, 255, 255)   # фон включён — правило должно его снять
    hatch.paths.add_polyline_path([(0, 0), (5000, 0), (5000, 5000), (0, 5000)])

    # --- размер со стилем ---------------------------------------------------
    ds = doc.dimstyles.get("Standard")
    ds.dxf.dimtfill = 2            # «фон есть» — правило должно сбросить в 0
    ds.dxf.dimtxt = 180
    msp.add_linear_dim(base=(0, -4000), p1=(0, 0), p2=(5000, 0),
                       dxfattribs={"layer": "A-ANNO-DIMS"}).render()

    # --- контроль: слой вне правил, трогать нельзя -------------------------
    msp.add_text("не трогать", height=321,
                 dxfattribs={"layer": "A-WALL", "insert": (20000, 20000)})

    path = OUT / "Тест ОП1.dxf"
    doc.saveas(str(path))
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = build_source()
    tgt = build_target()
    for p in (tgt, src):
        print(f"{p} — {p.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    sys.exit(main())

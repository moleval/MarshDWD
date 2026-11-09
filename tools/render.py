# -*- coding: utf-8 -*-
"""Картинка «до/после» по DXF: проверка глазами, без AutoCAD."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import ezdxf  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402
from ezdxf.addons.drawing.config import (  # noqa: E402
    Configuration, BackgroundPolicy)


def render(dxf_path, png_path, title, skip_off=True):
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    if skip_off:
        off = {lay.dxf.name for lay in doc.layers if lay.is_off()}
        for e in list(msp):
            if e.dxf.get("layer", "0") in off:
                msp.delete_entity(e)
    fig = plt.figure(figsize=(13, 9), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("white")
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        msp, finalize=True)
    ax.set_title(title, fontsize=9)
    fig.savefig(str(png_path), facecolor="white")
    plt.close(fig)
    print("картинка:", png_path)


if __name__ == "__main__":
    a = sys.argv[1:]
    render(Path(a[0]), Path(a[1]), a[2] if len(a) > 2 else "")

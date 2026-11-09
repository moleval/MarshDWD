# -*- coding: utf-8 -*-
"""DWG -> JSON-дамп через LibreDWG (dwgread) для офлайн-проверок.

Пример: python3 tools/dwg_dump.py input/*.dwg
Путь к dwgread: переменная MARSHDWG_DWGREAD или PATH.
"""
from pathlib import Path
import os
import subprocess
import sys

DWGREAD = os.environ.get("MARSHDWG_DWGREAD", "dwgread")


def dump(dwg, outdir):
    dwg, outdir = Path(dwg), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (dwg.stem + ".json")
    with out.open("wb") as fh:
        subprocess.run([DWGREAD, str(dwg), "-O", "json"], stdout=fh, check=True)
    print(f"{dwg} -> {out} ({out.stat().st_size} байт)")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    for p in sys.argv[1:]:
        dump(p, "dump")

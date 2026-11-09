# -*- coding: utf-8 -*-
"""Сборка: src/MARSHDWG.lsp (UTF-8/LF) -> dist/MARSHDWG.lsp (CP1251/CRLF)."""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "MARSHDWG.lsp"
DST = ROOT / "dist" / "MARSHDWG.lsp"


def main():
    text = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    data = text.replace("\n", "\r\n").encode("cp1251")
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_bytes(data)
    print("{}: {} байт, строк {}, sha256 {}".format(
        DST.relative_to(ROOT), len(data), data.count(b"\r\n"),
        hashlib.sha256(data).hexdigest()[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

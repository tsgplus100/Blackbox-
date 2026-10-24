"""Clip pads: Speed (src/stretch.c). Loaded by duck.py, like gran.py."""
import os
import struct

from thumb import ROOT, bl, bw, symbols

sym = symbols(os.path.join(ROOT, "out", "cave.elf"))


def hook(at, stock, name):
    return (at, bl(at, stock), bl(at, sym[name]))


def ids(*v):
    return struct.pack(f"<{len(v)}H", *v)


PATCHES = [
    # every call of the clip-length worker FUN_08064a94 (one of them a tail call)
    *[hook(a, 0x08064A94, "clip_duration") for a in
      (0x08066E9E, 0x08066FAC, 0x080679CE, 0x08068312, 0x0806838A, 0x0806840C, 0x08068632, 0x080686A8)],
    (0x08067B38, bw(0x08067B38, 0x08064A94), bw(0x08067B38, sym["clip_duration"])),
    # its two tick -> frame conversions
    hook(0x08064B9E, 0x08070420, "clip_ticks"),
    hook(0x08064E54, 0x08070420, "clip_ticks"),
    # the class B pad's block (vtable 0x080d0890 +0xc's thunk)
    hook(0x08068C6A, 0x08067FA4, "clip_process"),
    # Speed on the Clip pads' Pos page, after Loop Mode / Beat Count / Quant Size / Sync (both copies)
    (0x080EF990 + 8, ids(0), ids(0x1CF)),
    (0x080EF288 + 8, ids(0), ids(0x1CF)),
]

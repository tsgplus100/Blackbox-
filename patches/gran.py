"""Granular pads: Grain Size and Density as modulation destinations, LFO 2 / 3 knobs on their pages (src/gran.c).
Loaded by duck.py, which owns the LFO / ENV patches it builds on."""
import os
import struct

from thumb import ROOT, bl, symbols, word

sym = symbols(os.path.join(ROOT, "out", "cave.elf"))
TARGETS = sym["gran_mod_targets"]
N_STOCK, N_OURS = 28, 30


def hook(at, stock, name):
    return (at, bl(at, stock), bl(at, sym[name]))


def ids(*v):
    return struct.pack(f"<{len(v)}H", *v)


PATCHES = [
    # engine: every grain start (respawn, voice start, the two in the density update) and a class A pad's block
    *[hook(a, 0x08057AB0, "gran_grain_start") for a in (0x08057FBA, 0x08058B8A, 0x0805961E, 0x08059692)],
    hook(0x0805BB5A, 0x080596B0, "gran_pad_process"),
    # CC and engine-wide sources: the class A pad's vtable +0x40 (vtable at 0x080d06c8), and the pad's reset
    (0x080D0708, word(0x0805511D), word(sym["gran_attach"] | 1)),
    hook(0x08059E28, 0x08076080, "gran_reset"),
    # UI: the pad screen's list of parameters that have a MOD page (FUN_080b8898, FUN_080b892c)
    (0x080B8924, word(0x080F12BC), word(TARGETS)),
    (0x080B88D6, bytes.fromhex("03f13801"), bytes.fromhex("03f1") + bytes([2 * N_OURS]) + bytes.fromhex("01")),  # add.w r1,r3,#0x38 -> #0x3c
    (0x080B8BF8, word(0x080F12BC), word(TARGETS)),
    (0x080B896A, bytes([N_STOCK, 0x22]), bytes([N_OURS, 0x22])),   # movs r2,#28 -> #30
    (0x080B8980, bytes([N_STOCK, 0x22]), bytes([N_OURS, 0x22])),
    # Granular pad pages (both copies, see duck.py): LFO page gets LFO 2 Wave / Rate / Trig after the stock five,
    # Gran page gets LFO 3 Wave / Rate after its six. Eight knobs a page is all the screen has.
    *[(page + 10, ids(0, 0, 0), ids(0x1A9, 0x1AA, 0x1AB)) for page in (0x080EF5A0, 0x080EF000)],
    *[(page + 12, ids(0, 0), ids(0x1AD, 0x1AE)) for page in (0x080EF5E8, 0x080EF048)],
]

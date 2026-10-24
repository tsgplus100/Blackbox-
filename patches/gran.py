"""Granular pads: Grain Size and Density as modulation destinations, LFO 2 / 3 knobs on their pages; LFO 2 / 3 Depth
knobs and destinations on every pad (src/gran.c, src/lfo.c).
Loaded by duck.py, which owns the LFO / ENV patches it builds on."""
import os
import struct

from thumb import ROOT, bl, symbols, word

sym = symbols(os.path.join(ROOT, "out", "cave.elf"))
TARGETS = sym["gran_mod_targets"]
N_STOCK, N_OURS = 28, 40


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
    # ... and the class B pad's (Clip, Slicer): vtable at 0x080d0890, reset in FUN_08067fa4
    (0x080D08D0, word(0x08063DF1), word(sym["gran_attach_b"] | 1)),
    hook(0x08068556, 0x08076080, "gran_reset_b"),
    # UI: the pad screen's list of parameters that have a MOD page (FUN_080b8898, FUN_080b892c)
    (0x080B8924, word(0x080F12BC), word(TARGETS)),
    (0x080B88D6, bytes.fromhex("03f13801"), bytes.fromhex("03f1") + bytes([2 * N_OURS]) + bytes.fromhex("01")),  # add.w r1,r3,#0x38 -> #0x50
    (0x080B8BF8, word(0x080F12BC), word(TARGETS)),
    (0x080B896A, bytes([N_STOCK, 0x22]), bytes([N_OURS, 0x22])),   # movs r2,#28 -> #30
    (0x080B8980, bytes([N_STOCK, 0x22]), bytes([N_OURS, 0x22])),
    # Granular pad pages (both copies, see duck.py). Eight knobs a page is all the screen has. LFO page: LFO 1's
    # Waveform / Rate / Depth (its Beat Sync and Trig leave the page, keeping their values), then all five of LFO 2's.
    # Gran page: its six, then Pitch Rnd and Pitch Mode; Pos page: its six, then Scan and Lvl Rnd (gran.c's). LFO 3
    # has no knobs on these pads (it runs on its defaults when a slot uses it).
    *[(page, ids(8, 9, 0xB, 0xC, 0xD, 0, 0, 0), ids(8, 9, 0xB, 0x1A9, 0x1AA, 0x1C8, 0x1AB, 0x1AC)) for page in (0x080EF5A0, 0x080EF000)],
    *[(page + 12, ids(0, 0), ids(0x1CB, 0x1CD)) for page in (0x080EF5E8, 0x080EF048)],
    (0x080EF558 + 12, ids(0, 0), ids(0x1CA, 0x1CE)),
    (0x080EEFB8 + 4, ids(0, 0), ids(0x1CA, 0x1CE)),      # the second copy's Pos page has only two of its own
    # Lvl Rnd: the grain renderer's two pan-gain calls
    hook(0x08057EA2, 0x08061730, "gran_gain_l"),
    hook(0x08057EAE, 0x08061778, "gran_gain_r"),
    # LFO 2 / 3 Depth (0x1c8, 0x1c9): after the stock LFO's five on the LFO page of Sample, Multisample and Slicer
    # pads (and the second copy's Sample, Slicer); Clip pads: patches/stretch.py. Granular pads: 2 Depth is on their LFO page, above.
    *[(page + 10, ids(0, 0), ids(0x1C8, 0x1C9)) for page in
      (0x080EFCA8, 0x080EFB40, 0x080EF870, 0x080EF438, 0x080EF168)],
    # Conf page (a list): Insert and Input right under Saturation, as filter.py puts them on the other pads. Both run
    # in the class A pad's block (insert.c), which Granular pads share. No Fidelity: grains have their own reader.
    *[(page, ids(0xDB, 0x93, 0x95, 0x62, 0xC4, 0x6A, 0xD0, 0xF5, 0, 0), ids(0xDB, 0x1B6, 0x1C7, 0x93, 0x95, 0x62, 0xC4, 0x6A, 0xD0, 0xF5))
      for page in (0x080EF630, 0x080EF090)],
]

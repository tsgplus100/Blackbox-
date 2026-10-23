"""The power-on screen spells SYEN (src/splash.c). Loaded by duck.py, like gran.py."""
import os

from thumb import ROOT, bl, symbols

sym = symbols(os.path.join(ROOT, "out", "cave.elf"))

PATCHES = [
    (0x080C72B0, bl(0x080C72B0, 0x080AEC44), bl(0x080C72B0, sym["splash_logo"])),
]

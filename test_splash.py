"""The power-on screen spells SYEN (src/splash.c) under Unicorn.

Real code runs for splash_logo. Stubbed: the label's set-text (FUN_080c3b98) and the view's add-child
(FUN_080aec44), each recording what it was handed.
NOT checked: how the screen really looks (the renderer in the commit that added this was the preview).
"""
import struct
import sys

from emu import BASE, Emu

IMG = "out/solo+slice+duck+chord+cond+filter+cpu+od+comp+seqfix+fx2+munchi+master+fault+cave/BLACKBOX.bin"
e = Emu(IMG, "out/cave.elf")
img = open(IMG, "rb").read()
stock = open("firmware/BLACKBOX-3.1.9.bin", "rb").read()
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if not cond else ""))
    fails += not cond


def bl_target(at):
    h1, h2 = struct.unpack("<HH", img[at - BASE:at - BASE + 4])
    s = (h1 >> 10) & 1
    i1, i2 = 1 - (((h2 >> 13) & 1) ^ s), 1 - (((h2 >> 11) & 1) ^ s)
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    return at + 4 + off - (s << 25)


check("the screen's last step (adding the version line) goes through splash_logo",
      bl_target(0x080C72B0) == e.sym["splash_logo"] and stock[0x080C72B0 - BASE:0x080C72B4 - BASE] != img[0x080C72B0 - BASE:0x080C72B4 - BASE])

VIEW, VERSION = 0x24050000, 0x24050000 + 0x1EC
e.uc.mem_write(VIEW, bytes(0x300))
texts, added = [], []
e.stub(0x080C3B98, lambda: texts.append((e.arg(0), e.cstr(e.arg(1)))), value=1)
e.stub(0x080AEC44, lambda: added.append((e.arg(0), e.arg(1))))
e.call("splash_logo", VIEW, VERSION)
LOGO = ["   ##### #   # ##### #   #", "   #     #   # #     ##  #", "  #####  ###  ####  # # #",
        "      #   #   #     #  ##", "     #   #   #     #   #", "#####   #   ##### #   #"]
lines = [VIEW + 0x34 + 0x58 * i for i in range(6)]
check("the six lines get the six rows of SYEN, top to bottom", texts == list(zip(lines, LOGO)), texts)
rects = [struct.unpack("<4i", e.uc.mem_read(l + 4, 16)) for l in lines]
check("one under the other, 16 pixels apart (y counts up), 312 wide from x = 4: 312 x 96 pixels",
      rects == [(4, 152 - 16 * i, 312, 16) for i in range(6)], rects)
check("all left-aligned (the version line was right-aligned)", all(e.r8(l + 0x51) == 1 for l in lines))
check("...then the version line is added to the screen, as stock did", added == [(VIEW, VERSION)], added)
check("every row fits a line: 26 characters (312 / 12) at most, 31 the label's buffer", all(len(r) <= 26 for r in LOGO))

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

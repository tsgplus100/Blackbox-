"""Granular pads: Grain Size and Density as modulation destinations, LFO 2 / 3 knobs on their pages (src/gran.c).

Real code runs for the wrappers and the slot sums. Stubbed: the grain start (FUN_08057ab0), the pad's block
(FUN_080596b0) and the density update (FUN_08059158), each recording what it was handed.
NOT checked: that the MOD page opens on Grain Size and Density, that the knobs show on the LFO and Gran pages, preset
save / load of those routings, how the modulation sounds.
"""
import struct
import sys

from unicorn.arm_const import UC_ARM_REG_SP

from emu import BASE, STACK, Emu

IMG = "out/solo+slice+duck+chord+cond+filter+cpu+od+comp+seqfix+fx2+munchi+master+fault+cave/BLACKBOX.bin"
e = Emu(IMG, "out/cave.elf")
img = open(IMG, "rb").read()
stock = open("firmware/BLACKBOX-3.1.9.bin", "rb").read()
fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if not cond else ""))
    fails += not cond


def words(buf, addr, n):
    return list(struct.unpack(f"<{n}H", buf[addr - BASE:addr - BASE + 2 * n]))


def bl_target(at):
    h1, h2 = struct.unpack("<HH", img[at - BASE:at - BASE + 4])
    s = (h1 >> 10) & 1
    j1, j2 = (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    off -= (s << 25)
    return at + 4 + off


def wf(a, v):
    e.uc.mem_write(a, struct.pack("<f", v))


def rf(a):
    return struct.unpack("<f", e.uc.mem_read(a, 4))[0]


# ---- the image
T = e.sym["gran_mod_targets"]
check("MOD page list: stock's 28 and then Grain Size (0x17c) and Density (0x180)",
      words(img, T, 30) == words(stock, 0x080F12BC, 28) + [0x17C, 0x180], words(img, T, 30))
check("...both users of the list point at it, the loop runs to its end and both counts say 30",
      struct.unpack("<II", img[0x080B8924 - BASE:0x080B8928 - BASE] + img[0x080B8BF8 - BASE:0x080B8BFC - BASE]) == (T, T)
      and img[0x080B88D6 - BASE:0x080B88DA - BASE] == bytes.fromhex("03f13c01")
      and img[0x080B896A - BASE] == 30 and img[0x080B8980 - BASE] == 30)
for name, pages, have, add in (("LFO", (0x080EF5A0, 0x080EF000), 5, [0x1A9, 0x1AA, 0x1AB]),
                               ("Gran", (0x080EF5E8, 0x080EF048), 6, [0x1AD, 0x1AE])):
    for copy, base in zip(("", " (second copy)"), pages):
        got = words(img, base, 9)
        check(f"Granular {name} page{copy}: its own {have} knobs, then {', '.join(hex(x) for x in add)}, at most eight, ends in 0",
              got[:have] == words(stock, base, have) and got[have:have + len(add)] == add and got[have + len(add):] == [0] * (9 - have - len(add)), got)
for at in (0x08057FBA, 0x08058B8A, 0x0805961E, 0x08059692):
    check(f"grain start @{at:#x} goes through gran_grain_start", bl_target(at) == e.sym["gran_grain_start"] and
          struct.unpack("<HH", stock[at - BASE:at - BASE + 4]) != struct.unpack("<HH", img[at - BASE:at - BASE + 4]))
check("the class A pad's block goes through gran_pad_process", bl_target(0x0805BB5A) == e.sym["gran_pad_process"])
check(f"the image still fits bank 1: {len(img)} of {0x08100000 - BASE} bytes", len(img) <= 0x08100000 - BASE)

# ---- memory: the boot-time block, as master.c leaves it
e.uc.mem_map(0x38800000, 0x1000)
e.uc.mem_map(0x58024000, 0x1000)
e.uc.mem_map(0xC0000000, 0x90000)
BLOCKMEM, LFOS = 0xC0000000, 0xC0000000 + 0x56800
GRAN = LFOS + 0x800
e.w32(0x38800F70, BLOCKMEM)
e.w32(0x38800F74, BLOCKMEM ^ 0x5052534D)
e.w32(LFOS, 0x4C464F32)                       # lfo.c's state, started


def lfo_value(q, k, v):
    wf(LFOS + 0x18 + (q * 2 + k) * 28 + 4, v)


PAD, VOICE, VOICE2, NOW, CTX = 0x24030000, 0x24031000, 0x24032000, 0x24033000, 0x24033100
SIZE, DENS = PAD + 0x590, PAD + 0x5A0


def fresh(pad_id=0x0201):
    for a in (PAD, VOICE, VOICE2):
        e.uc.mem_write(a, bytes(0x800))
    e.w32(PAD + 0x18, pad_id)
    e.uc.mem_write(PAD + 0x589, b"\x01")


def slots(*entries):
    for i, (amount, target, source) in enumerate(entries):
        e.uc.mem_write(PAD + 0x4EC + 12 * i, struct.pack("<fHHB3x", amount, target, source, i))
    e.w32(PAD + 0x54C, len(entries))


# ---- Grain Size
seen = []
def grain_start():
    sp = e.uc.reg_read(UC_ARM_REG_SP)
    seen.append((e.r32(SIZE), [e.arg(i) for i in range(4)], (e.r32(sp), e.r32(sp + 4))))


e.stub(0x08057AB0, grain_start)


def start(voice=VOICE, size=24360):
    seen.clear()
    e.w32(SIZE, size)
    e.w32(STACK, 0x5A)
    e.w32(STACK + 4, 0x24034000)
    e.call("gran_grain_start", PAD, NOW, voice, 1)
    return seen[0][0] if len(seen) == 1 else None


fresh()
check("no slot on Grain Size: the grain starts with the knob's size, all six arguments passed on",
      start() == 24360 and seen[0][1] == [PAD, NOW, VOICE, 1] and seen[0][2] == (0x5A, 0x24034000) and e.r32(SIZE) == 24360, seen)
slots((0.5, 0x17C, 0xD))
wf(VOICE + 0x88, 1.0)                          # VEL = 1
check("VEL 1.0 at +50 %: half the knob's range more (24360 + 23872), floored to 840s; the knob's size is back after",
      start() == 47880 and e.r32(SIZE) == 24360, (start(), e.r32(SIZE)))
wf(VOICE + 0x88, 0.25)
check("VEL 0.25 at +50 %: 24360 + 5968 -> 30240", start() == 30240, start())
slots((-1.0, 0x17C, 0xD))
wf(VOICE + 0x88, 1.0)
check("pulled below the bottom: the smallest grain, 840 samples", start() == 840, start())
slots((1.0, 0x17C, 0xD))
check("pushed past the top: 48944 floored, 48720", start() == 48720, start())
check("a synced size longer than the knob goes (96000) is not cut down by a push up", start(size=96000) == 96000 // 840 * 840, start(size=96000))
slots((0.5, 0x17C, 1), (-0.25, 0x17C, 5), (0.5, 0x11, 0xD))
wf(VOICE + 0x50, 0.5)                          # ENV level
lfo_value(9, 0, 1.0)                           # pad 10's LFO 2
check("ENV 0.5 at +50 % and LFO2 1.0 at -25 % add up (0 net); a slot on Cutoff is not counted", start() == 24360, start())
lfo_value(9, 0, -1.0)
check("...LFO2 at -1: +0.5 of the range, 24360 + 23872 -> 47880", start() == 47880, start())
e.uc.mem_write(PAD + 0x589, b"\x00")
check("a pad that is not granular is left alone", start() == 24360, start())
fresh()
slots((0.5, 0x17C, 0xD), (0.5, 0x17C, 0xE))
wf(VOICE2 + 0x88, 1.0)
wf(VOICE2 + 0x90, -0.2)                        # KEY: an octave below middle C
check("the voice that starts the grain is the one read: VEL 1 and KEY -0.2 -> +0.4 of the range", start(VOICE2) == (24360 + int(0.4 * 47744)) // 840 * 840, start(VOICE2))
slots((0.5, 0x17C, 0x19), (0.5, 0x17C, 0x10))
check("MIDI and duck sources are not in the slot list's reach: no change", start() == 24360, start())

# ---- Density
blocks, dens = [], []
e.stub(0x080596B0, lambda: blocks.append((e.arg(0), e.arg(1))), value=1)
e.stub(0x08059158, lambda: dens.append((round(rf(DENS), 4), e.arg(1))))
e.w32(CTX, NOW)


def block():
    blocks.clear()
    dens.clear()
    e.call("gran_pad_process", PAD, CTX)
    return list(dens)


fresh()
wf(DENS, 0.3)
check("no slot on Density: the pad's block runs, density untouched, nothing set up", block() == [] and blocks == [(PAD, CTX)] and e.r32(GRAN + 4) == 0)
slots((0.5, 0x180, 5))
lfo_value(9, 0, 0.4)
check("LFO2 0.4 at +50 %: density 0.3 -> 0.5, through the stock update, with the block's clock", block() == [(0.5, NOW)] and blocks == [(PAD, CTX)], dens)
check("...pad 10 marked as moved, its knob value kept", e.r32(GRAN + 4) == 1 << 9 and round(rf(GRAN + 8 + 4 * 9), 4) == 0.3)
lfo_value(9, 0, 0.402)
check("a change under 0.002 is not worth a stock update", block() == [])
lfo_value(9, 0, 0.6)
check("...a bigger one is: 0.6", block() == [(0.6, NOW)], dens)
wf(DENS, 0.7)                                  # the knob turned (stock wrote it and ran its own update)
check("the knob turned to 0.7: that is the new centre, 0.7 + 0.3 = 1.0", block() == [(1.0, NOW)], dens)
lfo_value(9, 0, 1.0)
check("clamped at 1", block() == [], dens)
slots()
check("slot removed: the knob's 0.7 put back, once, and the pad no longer marked", block() == [(0.7, NOW)] and e.r32(GRAN + 4) == 0, dens)
check("...then nothing more", block() == [])
slots((-1.0, 0x180, 0xD))
e.w32(PAD + 0x6C, 2)
e.w32(PAD + 0x2C, VOICE)
e.w32(PAD + 0x30, VOICE2)
e.uc.mem_write(VOICE2, b"\x01")
wf(VOICE2 + 0x88, 0.5)
wf(VOICE + 0x88, 1.0)
check("VEL from the first playing voice (the second; the first is idle): 0.7 - 0.5 = 0.2", block() == [(0.2, NOW)], dens)
e.uc.mem_write(VOICE2, b"\x00")
check("no voice playing: VEL counts 0, back to 0.7", block() == [(0.7, NOW)], dens)
e.uc.mem_write(PAD + 0x589, b"\x00")
wf(DENS, 0.1)
check("not a granular pad: only the stock block", block() == [] and blocks == [(PAD, CTX)])

# ---- no memory block
e.uc.mem_write(0x38800F70, bytes(8))
fresh()
slots((0.5, 0x180, 0xD), (0.5, 0x17C, 5))
wf(DENS, 0.3)
check("without the memory block Density is left alone and the block still runs", block() == [] and blocks == [(PAD, CTX)])
check("...and an LFO2 slot on Grain Size reads nothing (no crash)", start() == 24360, start())

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

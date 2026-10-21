"""Granular pads: Grain Size and Density as modulation destinations, LFO 2 / 3 knobs on their pages (src/gran.c).

Real code runs for the wrappers, the slot sums and the pad's slot setup (FUN_08056810, through env_mod_setup).
Stubbed: the grain start (FUN_08057ab0), the pad's block (FUN_080596b0), the density update (FUN_08059158), the pad's
engine-wide attach (FUN_0805511c) and the reset helper (FUN_08076080), each recording what it was handed.
NOT checked: that the MOD page opens on Grain Size and Density, that the knobs show on the LFO and Gran pages, preset
save / load of those routings, how the modulation sounds.
"""
import struct
import sys

from unicorn.arm_const import UC_ARM_REG_S0, UC_ARM_REG_SP

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
check("MOD page list: stock's 28 and then Grain Size (0x17c), Density (0x180), LFO 2 / 3 Depth (0x1c8, 0x1c9)",
      words(img, T, 32) == words(stock, 0x080F12BC, 28) + [0x17C, 0x180, 0x1C8, 0x1C9], words(img, T, 32))
check("...both users of the list point at it, the loop runs to its end and both counts say 32",
      struct.unpack("<II", img[0x080B8924 - BASE:0x080B8928 - BASE] + img[0x080B8BF8 - BASE:0x080B8BFC - BASE]) == (T, T)
      and img[0x080B88D6 - BASE:0x080B88DA - BASE] == bytes.fromhex("03f14001")
      and img[0x080B896A - BASE] == 32 and img[0x080B8980 - BASE] == 32)
for name, page, have in (("Sample", 0x080EFCA8, 5), ("Multisample", 0x080EFB40, 5), ("Clip", 0x080EF9D8, 5), ("Slicer", 0x080EF870, 5),
                         ("second-copy Sample", 0x080EF438, 5), ("second-copy Clip", 0x080EF2D0, 5), ("second-copy Slicer", 0x080EF168, 5),
                         ("Granular Pos", 0x080EF558, 6), ("second-copy Granular Pos", 0x080EEFB8, 2)):
    got = words(img, page, have + 3)
    check(f"{name} page: its own {have} knobs, then 2 Depth and 3 Depth, then the end",
          got[:have] == words(stock, page, have) and words(stock, page, have + 3)[have:] == [0, 0, 0] and got[have:] == [0x1C8, 0x1C9, 0], got)
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
check("the class A pad's vtable +0x40 (engine-wide sources) is gran_attach, the pad reset's helper call is gran_reset",
      struct.unpack("<I", img[0x080D0708 - BASE:0x080D070C - BASE])[0] == e.sym["gran_attach"] | 1
      and struct.unpack("<I", stock[0x080D0708 - BASE:0x080D070C - BASE])[0] == 0x0805511D and bl_target(0x08059E28) == e.sym["gran_reset"])
check("...and the class B pad's: gran_attach_b, gran_reset_b",
      struct.unpack("<I", img[0x080D08D0 - BASE:0x080D08D4 - BASE])[0] == e.sym["gran_attach_b"] | 1
      and struct.unpack("<I", stock[0x080D08D0 - BASE:0x080D08D4 - BASE])[0] == 0x08063DF1 and bl_target(0x08068556) == e.sym["gran_reset_b"])
check(f"the image still fits bank 1: {len(img)} of {0x08100000 - BASE} bytes", len(img) <= 0x08100000 - BASE)

# ---- memory: the boot-time block, as master.c leaves it
e.uc.mem_map(0x38800000, 0x1000)
e.uc.mem_map(0x58024000, 0x1000)
e.uc.mem_map(0xC0000000, 0x90000)
BLOCKMEM, LFOS = 0xC0000000, 0xC0000000 + 0x56800
GRAN = LFOS + 0x800
e.w32(0x38800F70, BLOCKMEM)
e.w32(0x38800F74, BLOCKMEM ^ 0x5052534D)
e.w32(LFOS, 0x4C464F33)                       # lfo.c's state, started


def lfo_value(q, k, v):
    wf(LFOS + 0x18 + (q * 2 + k) * 28 + 4, v)


PAD, VOICE, VOICE2, NOW, CTX = 0x24030000, 0x24031000, 0x24032000, 0x24033000, 0x24033100
SIZE, DENS = PAD + 0x590, PAD + 0x5A0


def fresh(pad_id=0x0201):
    for a in (PAD, VOICE, VOICE2):
        e.uc.mem_write(a, bytes(0x800))
    e.w32(PAD, 0x080D06C8)                     # a class A pad's vtable
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

# ---- MIDI sources: PTCH / MODW / MVOL / MPAN kept in the pad's list for our targets (env_mod_setup)
CMD = 0x24035000
e.uc.mem_write(0x38800F70, struct.pack("<II", BLOCKMEM, BLOCKMEM ^ 0x5052534D))


def slot_cmd(target, slot, source, amount):
    e.uc.mem_write(CMD, struct.pack("<BBHIIIIHh", 0x3A, 0, 0, 0, 0, target, slot, source, amount))
    e.call("env_mod_setup", PAD, CMD)


def listed():
    return [(round(rf(PAD + 0x4EC + 12 * i), 3), e.r16(PAD + 0x4F0 + 12 * i), e.r16(PAD + 0x4F2 + 12 * i)) for i in range(e.r32(PAD + 0x54C))]


fresh()
slot_cmd(0x17C, 0, 0x1A, 500)
slot_cmd(0x180, 1, 0x19, -250)
slot_cmd(0x11, 0, 0x1A, 500)
check("MODW on Grain Size and PTCH on Density stay in the pad's list; MODW on Cutoff goes stock's way (not listed)",
      listed() == [(0.5, 0x17C, 0x1A), (-0.25, 0x180, 0x19)], listed())
wf(PAD + 0x128, 1.0)                           # mod wheel all the way up
check("MODW 1.0 at +50 %: +0.5 of the range -> 47880", start() == 47880, start())
for code, obj in ((0x19, 0x13C), (0x1C, 0x12C), (0x1D, 0x134)):
    fresh()
    slot_cmd(0x17C, 0, code, 500)
    wf(PAD + obj + 4, 1.0)
    check(f"source {code:#x} reads pad +{obj + 4:#x}", start() == 47880, (start(), listed()))
fresh()
slot_cmd(0x17C, 0, 0x1A, 500)
slot_cmd(0x17C, 0, 0, 0)
check("setting the slot back to none takes it out of the list", listed() == [], listed())

# ---- CC and engine-wide sources: through the pad's vtable +0x40
attached = []
e.stub(0x0805511C, lambda: attached.append((e.arg(0), e.arg(1), e.arg(2), e.arg(3), round(struct.unpack("<f", struct.pack("<I", e.uc.reg_read(UC_ARM_REG_S0) & 0xFFFFFFFF))[0], 3))))
CC = 0x24036000


def attach(source, target, slot, amount):
    attached.clear()
    e.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", amount))[0])
    e.call("gran_attach", PAD, source, target, slot)
    return list(attached)


fresh()
e.uc.mem_write(CC, bytes(16))
wf(CC + 4, 1.0)
check("a CC on Grain Size, slot 1: kept, and stock's attach still runs with everything it was given",
      attach(CC, 0x17C, 1, 0.5) == [(PAD, CC, 0x17C, 1, 0.5)], attached)
check("...the grain is 0.5 of the range bigger", start() == 47880, start())
wf(CC + 4, 0.0)
check("...and back when the CC is 0", start() == 24360, start())
wf(CC + 4, 1.0)
check("a CC on Cutoff goes to stock only", attach(CC, 0x11, 0, 0.5) == [(PAD, CC, 0x11, 0, 0.5)] and start() == 47880)
attach(0, 0x17C, 1, 0.0)
check("the CC taken off (source 0): no change any more", start() == 24360, start())
attach(CC, 0x180, 2, -0.5)
wf(DENS, 0.6)
check("a CC on Density at -50 %: 0.6 -> 0.1", block() == [(0.1, NOW)], dens)
attach(CC, 0x17C, 0, 0.25)
resets = []
e.stub(0x08076080, lambda: resets.append(e.arg(0)))
e.call("gran_reset", PAD + 0x2F4)
check("the pad's reset hands its helper the same object and empties the pad's CC slots", resets == [PAD + 0x2F4] and start() == 24360, (resets, start()))
check("...so Density goes back to the knob's 0.6", block() == [(0.6, NOW)], dens)
fresh(0x0302)                                  # another pad (row 3, col 2) keeps its own
attach(CC, 0x17C, 0, 0.5)
fresh(0x0201)
check("CC slots are per pad", start() == 24360, start())

# ---- LFO 2 / 3 Depth: slot-list part from the class A pad's block, CC part per pad, both through gran_depth
DEPTH = GRAN + 136 + 16 * 4 * 3 * 8


def gran_depth(q, k):
    e.call("gran_depth", q, k)
    return round(struct.unpack("<f", struct.pack("<I", e.uc.reg_read(UC_ARM_REG_S0) & 0xFFFFFFFF))[0], 4)


fresh()
e.uc.mem_write(PAD + 0x589, b"\x00")           # a Sample pad: Depth is for every class A pad
slots((0.5, 0x1C8, 0xD), (-0.25, 0x1C9, 5))
e.w32(PAD + 0x6C, 1)
e.w32(PAD + 0x2C, VOICE)
e.uc.mem_write(VOICE, b"\x01")
wf(VOICE + 0x88, 1.0)
lfo_value(9, 0, 1.0)
block()
check("a Sample pad's block works out VEL 1 x 50 % on LFO 2 Depth and LFO2 1 x -25 % on LFO 3 Depth",
      (gran_depth(9, 0), gran_depth(9, 1)) == (0.5, -0.25) and blocks == [(PAD, CTX)], (rf(DEPTH + 72), rf(DEPTH + 76)))
check("...each is used once (the next block works it out again)", (gran_depth(9, 0), gran_depth(9, 1)) == (0.0, 0.0))
slots()
block()
check("no slot on either Depth: nothing", gran_depth(9, 0) == 0.0)
attach(CC, 0x1C9, 2, 0.5)
wf(CC + 4, 0.5)
check("a CC on LFO 3 Depth counts on every look, not once", (gran_depth(9, 1), gran_depth(9, 1)) == (0.25, 0.25))
check("an out-of-range pad index reads nothing", gran_depth(16, 0) == 0.0)
e.call("gran_reset", PAD + 0x2F4)
check("the pad's reset empties it", gran_depth(9, 1) == 0.0)
slot_cmd(0x1C8, 0, 0x1A, 1000)
check("MODW on LFO 2 Depth stays in the pad's list", listed() == [(1.0, 0x1C8, 0x1A)], listed())

# ---- class B pads (Clip, Slicer): CC and engine-wide sources only, through their own vtable +0x40 and reset
PADB = 0x24037000
e.uc.mem_write(PADB, bytes(0x900))
e.w32(PADB, 0x080D0890)                        # a class B pad's vtable
e.w32(PADB + 0x18, 0x0003)                     # pad 4
battached = []
e.stub(0x08063DF0, lambda: battached.append((e.arg(0), e.arg(1), e.arg(2), e.arg(3))))
e.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", -1.0))[0])
e.call("gran_attach_b", PADB, CC, 0x1C8, 0)
check("class B: a CC on LFO 2 Depth is kept and stock's attach still runs", battached == [(PADB, CC, 0x1C8, 0)] and gran_depth(3, 0) == -0.5, battached)
e.uc.reg_write(UC_ARM_REG_S0, 0)
e.call("gran_attach_b", PADB, CC, 0x11, 0)
check("class B: a CC on Cutoff goes to stock only", battached[-1] == (PADB, CC, 0x11, 0) and gran_depth(3, 0) == -0.5)
resets.clear()
e.call("gran_reset_b", PADB + 0x26C + 0x410 + 0x1D4)   # the second layer's call first: not a pad, left alone
check("class B reset, second layer's call: not 0x440 into a pad, nothing emptied", gran_depth(3, 0) == -0.5 and resets == [PADB + 0x850])
e.call("gran_reset_b", PADB + 0x26C + 0x1D4)
check("class B reset, first layer's call: the pad's CC slots emptied", gran_depth(3, 0) == 0.0 and resets[-1] == PADB + 0x440)

# ---- no memory block
e.uc.mem_write(0x38800F70, bytes(8))
fresh()
slots((0.5, 0x180, 0xD), (0.5, 0x17C, 5))
wf(DENS, 0.3)
check("without the memory block Density is left alone and the block still runs", block() == [] and blocks == [(PAD, CTX)])
check("...and an LFO2 slot on Grain Size reads nothing (no crash)", start() == 24360, start())

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

"""Granular pads: Grain Size and Density as modulation destinations, LFO 2 / 3 knobs on their pages (src/gran.c).

Real code runs for the wrappers, the slot sums and the pad's slot setup (FUN_08056810, through env_mod_setup).
Stubbed: the grain start (FUN_08057ab0), the pad's block (FUN_080596b0), the density update (FUN_08059158), the pad's
engine-wide attach (FUN_0805511c) and the reset helper (FUN_08076080), each recording what it was handed.
NOT checked: that the MOD page opens on Grain Size and Density, that the knobs show on the LFO and Gran pages, preset
save / load of those routings, how the modulation sounds.
"""
import math
import struct
import sys

from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_S0, UC_ARM_REG_SP

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
OURS = [0x17C, 0x180, 0x1C8, 0x1C9, 0x5B, 0x17E, 0x17F, 0x1CA, 0x1CB, 0x1CE, 0x193, 0x195]
check("MOD page list: stock's 28, then Grain Size, Density, LFO 2 / 3 Depth, Window, Scatter, Pan Rnd, Scan, Pitch Rnd, Lvl Rnd, Clip Grain, Jitter",
      words(img, T, 40) == words(stock, 0x080F12BC, 28) + OURS, words(img, T, 40))
check("...both users of the list point at it, the loop runs to its end and both counts say 40",
      struct.unpack("<II", img[0x080B8924 - BASE:0x080B8928 - BASE] + img[0x080B8BF8 - BASE:0x080B8BFC - BASE]) == (T, T)
      and img[0x080B88D6 - BASE:0x080B88DA - BASE] == bytes.fromhex("03f15001")
      and img[0x080B896A - BASE] == 40 and img[0x080B8980 - BASE] == 40)
for name, page, have in (("Sample", 0x080EFCA8, 5), ("Multisample", 0x080EFB40, 5), ("Slicer", 0x080EF870, 5),
                         ("second-copy Sample", 0x080EF438, 5), ("second-copy Slicer", 0x080EF168, 5)):
    got = words(img, page, have + 3)
    check(f"{name} page: its own {have} knobs, then 2 Depth and 3 Depth, then the end",
          got[:have] == words(stock, page, have) and words(stock, page, have + 3)[have:] == [0, 0, 0] and got[have:] == [0x1C8, 0x1C9, 0], got)
for copy, base in zip(("", " (second copy)"), (0x080EF5A0, 0x080EF000)):
    check(f"Granular LFO page{copy}: LFO 1 Waveform / Rate / Depth (no Beat Sync, no Trig), then LFO 2's five",
          words(stock, base, 6) == [8, 9, 0xB, 0xC, 0xD, 0] and words(img, base, 9) == [8, 9, 0xB, 0x1A9, 0x1AA, 0x1C8, 0x1AB, 0x1AC, 0], words(img, base, 9))
for copy, base in zip(("", " (second copy)"), (0x080EF5E8, 0x080EF048)):
    check(f"Granular Gran page{copy}: its own six, then Pitch Rnd and Pitch Mode",
          words(img, base, 6) == words(stock, base, 6) and words(stock, base, 7)[6] == 0 and words(img, base, 9)[6:] == [0x1CB, 0x1CD, 0], words(img, base, 9))
for copy, base, have in (("", 0x080EF558, 6), (" (second copy)", 0x080EEFB8, 2)):
    check(f"Granular Pos page{copy}: its own {have}, then Scan and Lvl Rnd",
          words(img, base, have) == words(stock, base, have) and words(stock, base, have + 3)[have:] == [0, 0, 0]
          and words(img, base, have + 3)[have:] == [0x1CA, 0x1CE, 0], words(img, base, have + 3))
check("Lvl Rnd: both pan-gain calls of the grain renderer go through gran_gain_l / gran_gain_r",
      bl_target(0x08057EA2) == e.sym["gran_gain_l"] and bl_target(0x08057EAE) == e.sym["gran_gain_r"])
for at in (0x08057FBA, 0x08058B8A, 0x0805961E, 0x08059692):
    check(f"grain start @{at:#x} goes through gran_grain_start", bl_target(at) == e.sym["gran_grain_start"] and
          struct.unpack("<HH", stock[at - BASE:at - BASE + 4]) != struct.unpack("<HH", img[at - BASE:at - BASE + 4]))
check("the class A pad's block goes through gran_pad_process", bl_target(0x0805BB5A) == e.sym["gran_pad_process"])
for copy, base in zip(("", " (second copy)"), (0x080EF630, 0x080EF090)):
    check(f"Granular Conf page{copy}: Insert and Input right under Saturation, the stock rows after, no Fidelity",
          words(img, base, 11) == [0xDB, 0x1B6, 0x1C7, 0x93, 0x95, 0x62, 0xC4, 0x6A, 0xD0, 0xF5, 0]
          and words(stock, base, 9) == [0xDB, 0x93, 0x95, 0x62, 0xC4, 0x6A, 0xD0, 0xF5, 0], words(img, base, 11))
check("the insert's run hook is where the Granular voice loop ends too (b.w 0x08059a7c @0x0805a9fe, stock)",
      img[0x0805A9FE - BASE:0x0805AA02 - BASE] == stock[0x0805A9FE - BASE:0x0805AA02 - BASE] == bytes.fromhex("fff73db8"))
check("no LFO 3 knob on any Granular page", not any(x in (0x1AD, 0x1AE, 0x1AF, 0x1B0, 0x1C9)
                                                   for b in (0x080EF510, 0x080EEF70) for x in words(img, b, 5 * 0x24)))
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
GRAN = BLOCKMEM + 0x56800 + 0x2D100              # master.c's block, behind comp.c's clipper
EXT = 6                                       # bytes a CC slot: source, amount per mille (packed)
e.w32(0x38800F70, BLOCKMEM)
e.w32(0x38800F74, BLOCKMEM ^ 0x5052534D)
e.w32(LFOS, 0x4C464F33)                       # lfo.c's state, started


def lfo_value(q, k, v):
    wf(LFOS + 0x18 + (q * 2 + k) * 28 + 4, v)


PAD, VOICE, VOICE2, NOW, CTX = 0x24030000, 0x24031000, 0x24032000, 0x24033000, 0x24033100
SIZE, DENS = PAD + 0x590, PAD + 0x5A0
WIN, SCAT, PANR = PAD + 0x594, PAD + 0x598, PAD + 0x59C


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
    seen.append((e.r32(SIZE), [e.arg(i) for i in range(4)], (e.r32(sp), e.r32(sp + 4)), e.r32(WIN), e.r32(SCAT), rf(PANR)))


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

# ---- Window, Scatter, Pan Rnd: each grain, on its knob's own curve
TABLE = list(struct.unpack("<97i", stock[0x080EB2A0 - BASE:0x080EB2A0 - BASE + 97 * 4]))


def grain3(win, scat, pan):
    e.w32(WIN, win)
    e.w32(SCAT, scat)
    wf(PANR, pan)
    start()
    got = seen[0][3:6]
    pan32 = struct.unpack("<f", struct.pack("<f", pan))[0]
    back = (e.r32(WIN), e.r32(SCAT), rf(PANR)) == (win, scat, pan32)
    return got[0], got[1], round(got[2], 4), back


fresh()
win_half = int(1824000 * 0.5 ** 3)              # the Window knob at 50 %
check("no slots: Window, Scatter, Pan Rnd reach the grain as they are", grain3(win_half, TABLE[48], 0.3) == (win_half, TABLE[48], 0.3, True))
slots((0.25, 0x5B, 0xD), (-0.25, 0x17E, 0xD), (0.5, 0x17F, 0xD))
wf(VOICE + 0x88, 1.0)
w, sc, pr, back = grain3(win_half, TABLE[48], 0.3)
check(f"VEL 1: Window knob 50 % + 25 % -> 75 %, on the cube ({w} vs {int(1824000 * 0.75 ** 3)})", abs(w - 1824000 * 0.75 ** 3) < 200, w)
check(f"...Scatter step 48 - 25 % of 96 -> step 24 ({sc} = table {TABLE[24]})", sc == TABLE[24], sc)
check("...Pan Rnd 0.3 + 0.5 = 0.8; and all three put back after the grain", pr == 0.8 and back, (pr, back))
w, sc, pr, back = grain3(0, TABLE[0], 0.9)
check("from the bottom: Window 0 + 25 % -> 25 % on the cube, Scatter step 0 - 25 % stays 0, Pan Rnd clamped at 1",
      abs(w - 1824000 * 0.25 ** 3) < 50 and sc == TABLE[0] and pr == 1.0 and back, (w, sc, pr))
slots((1.0, 0x5B, 5), (1.0, 0x17E, 5), (-1.0, 0x17F, 5))
lfo_value(9, 0, 1.0)
w, sc, pr, back = grain3(win_half, TABLE[48], 0.3)
check("LFO2 at +1, all +100 %: Window and Scatter at their tops, Pan Rnd (-100 %) at 0",
      w == 1824000 and sc == TABLE[96] and pr == 0.0, (w, sc, pr))
e.uc.mem_write(PAD + 0x589, b"\x00")
check("a pad that is not granular: none of the three moved", grain3(win_half, TABLE[48], 0.3) == (win_half, TABLE[48], 0.3, True))

# ---- Scan and Pitch Rnd: our knobs, read from the app's pad store once a block
APPPADS = 0x24020088 + 0x1840
SAMPLE = 0x2403A000


def knobs(scan, pitchrnd, q=9, mode=0, lvl=0):
    arr = 0x2403B000 + q * 0x40
    e.uc.mem_write(arr, struct.pack("<HHIHHIHHIHHI", 0x1CA, 0, scan, 0x1CB, 0, pitchrnd, 0x1CD, 0, mode, 0x1CE, 0, lvl))
    store = APPPADS + (q >> 2) * 0xF0 + (q & 3) * 0x30
    e.w32(store + 4, arr)
    e.uc.mem_write(store + 10, struct.pack("<H", 4))
    e.call("gran_pad_process", PAD, CTX)       # reads them for the next grains


rates = []


def grain_rate():
    rates.append(rf(e.r32(e.uc.reg_read(UC_ARM_REG_SP) + 4) + 0x24))


def start_at(head, fixed=False, fixpos=0, rate=1.0):
    """A grain start; returns (playhead, fixed position) as the stock grain start saw them, and the grain's rate after."""
    e.uc.mem_write(VOICE + 0x10, struct.pack("<q", head))
    e.uc.mem_write(PAD + 0x5B5, b"\x01" if fixed else b"\x00")
    e.w32(PAD + 0x5B8, fixpos)
    wf(GRAIN + 0x24, rate)
    looked.clear()
    e.w32(STACK, 0x5A)
    e.w32(STACK + 4, GRAIN)
    e.call("gran_grain_start", PAD, NOW, VOICE, 1)
    back = struct.unpack("<q", e.uc.mem_read(VOICE + 0x10, 8))[0] == head and e.r32(PAD + 0x5B8) == fixpos
    return looked[0][0], looked[0][1], round(rf(GRAIN + 0x24), 4), back


GRAIN = 0x2403C000
looked = []
e.stub(0x08057AB0, lambda: looked.append((struct.unpack("<q", e.uc.mem_read(VOICE + 0x10, 8))[0], e.r32(PAD + 0x5B8))))
e.stub(0x080636F0, lambda: None, value=100000)              # the sample: 100000 frames
e.stub(0x080596B0, value=1)
e.stub(0x08059158)
e.w32(CTX, NOW)
fresh()
e.w32(VOICE + 0xC, SAMPLE)
knobs(0, 0)
check("Scan 0, Pitch Rnd 0: the grain reads at the playhead, at its own rate, and the playhead is not touched",
      start_at(40000) == (40000, 0, 1.0, True), start_at(40000))
knobs(250, 0)
check("Scan 25 %: a quarter of the sample further on (40000 -> 65000), playhead put back", start_at(40000) == (65000, 0, 1.0, True), start_at(40000))
check("...wrapping round the end (90000 -> 15000)", start_at(90000)[0] == 15000, start_at(90000))
check("...on a fixed point (per mille): 900 -> 150, put back after", start_at(0, True, 900)[1:2] == (150,) and start_at(0, True, 900)[3], start_at(0, True, 900))
slots((0.5, 0x1CA, 5))
lfo_value(9, 0, 1.0)
check("Scan 25 % + LFO2 1 x 50 %: 75 % on (10000 -> 85000)", start_at(10000)[0] == 85000, start_at(10000))
lfo_value(9, 0, -1.0)
check("...LFO2 at -1: 25 % - 50 % = -25 %, wrapping back (40000 -> 15000)", start_at(40000)[0] == 15000, start_at(40000))
slots()
knobs(0, 1000)
r = [start_at(40000)[2] for _ in range(200)]
check(f"Pitch Rnd 100 %: every grain its own rate, between half and double ({min(r):.3f} .. {max(r):.3f})",
      0.5 <= min(r) < 0.6 and 1.8 < max(r) <= 2.0 and len(set(r)) > 150, (min(r), max(r)))
knobs(0, 83)
r = [start_at(40000, rate=1.5)[2] for _ in range(100)]
check(f"Pitch Rnd 8.3 %: about a semitone either way, around the grain's own rate 1.5 ({min(r):.3f} .. {max(r):.3f})",
      1.5 * 2 ** (-0.083) - 0.002 <= min(r) < 1.48 and 1.52 < max(r) <= 1.5 * 2 ** 0.083 + 0.002, (min(r), max(r)))
knobs(0, 0)
slots((0.5, 0x1CB, 5))
lfo_value(9, 0, 1.0)
r = [start_at(40000)[2] for _ in range(50)]
check("Pitch Rnd as a destination: knob 0 + LFO2 x 50 % -> up to half an octave", 2 ** -0.5 - 0.002 <= min(r) and max(r) <= 2 ** 0.5 + 0.002 and len(set(r)) > 40, (min(r), max(r)))
slots()
semis = lambda r: round(12 * math.log2(r), 2)


def spread(mode, reach, n=400):
    knobs(0, reach, mode=mode)
    return sorted({semis(start_at(40000)[2]) for _ in range(n)})


check(f"Pitch Mode Semi, reach 100 %: whole semitones only, -12 .. +12 ({len(spread(1, 1000))} steps)",
      spread(1, 1000) == [float(k) for k in range(-12, 13)], spread(1, 1000))
check("Pitch Mode Oct: -12, 0, +12", spread(2, 1000) == [-12.0, 0.0, 12.0], spread(2, 1000))
check("Pitch Mode 5th+Oct: -12, -7, 0, +7, +12", spread(3, 1000) == [-12.0, -7.0, 0.0, 7.0, 12.0], spread(3, 1000))
check("Pitch Mode Major: 0, 4, 7, 12 either way", spread(4, 1000) == [-12.0, -7.0, -4.0, 0.0, 4.0, 7.0, 12.0], spread(4, 1000))
check("Pitch Mode Minor: 0, 3, 7, 12 either way", spread(5, 1000) == [-12.0, -7.0, -3.0, 0.0, 3.0, 7.0, 12.0], spread(5, 1000))
check("Pitch Mode Pent: 0, 3, 5, 7, 10, 12 either way",
      spread(6, 1000) == [-12.0, -10.0, -7.0, -5.0, -3.0, 0.0, 3.0, 5.0, 7.0, 10.0, 12.0], spread(6, 1000))
check("Pitch Mode Shimmr: up an octave or not at all", spread(7, 1000) == [0.0, 12.0], spread(7, 1000))
check("Oct with a reach of 40 % (under half an octave): no grain jumps", spread(2, 400) == [0.0], spread(2, 400))
knobs(0, 1000, mode=2)
hits = [semis(start_at(40000)[2]) for _ in range(2000)]
share = hits.count(0.0) / len(hits)
check(f"Oct at 100 %: about half the grains as they are ({share:.0%}), the rest an octave either way", 0.45 < share < 0.55, share)
knobs(0, 1000, mode=9)
check("a Pitch Mode past the list's end reads as Free", len(spread(9, 1000, 100)) > 90)

# Lvl Rnd: the grain's spare word, then the renderer's pan gains
LEVEL = GRAIN + 0x3C


def level_word(lvl):
    knobs(0, 0, lvl=lvl)
    start_at(40000)
    w = e.r32(LEVEL) & 0xFFFFFFFF
    return w >> 16, (w & 0xFFFF) / 32768


check("Lvl Rnd 0: every grain tagged at full level", all(level_word(0) == (0x4C56, 32767 / 32768) for _ in range(20)))
lv = [level_word(1000)[1] for _ in range(300)]
check(f"Lvl Rnd 100 %: each grain its own level, silence to full ({min(lv):.3f} .. {max(lv):.3f})", min(lv) < 0.05 and max(lv) > 0.95, (min(lv), max(lv)))
lv = [level_word(250)[1] for _ in range(300)]
check(f"Lvl Rnd 25 %: never below 75 % ({min(lv):.3f})", 0.74 < min(lv) and max(lv) > 0.97, min(lv))
knobs(0, 0, lvl=0)
slots((1.0, 0x1CE, 5))
lfo_value(9, 0, 0.5)
lv = []
for _ in range(200):
    start_at(40000)
    lv.append((e.r32(LEVEL) & 0xFFFF) / 32768)
check(f"Lvl Rnd as a destination: knob 0 + LFO2 0.5 x 100 % -> levels between 50 % and full ({min(lv):.3f} .. {max(lv):.3f})", 0.49 < min(lv) < 0.6 and max(lv) > 0.95, (min(lv), max(lv)))
slots()


def pan_gain(sym, stock_fn, word, gain=0.8):
    e.stub(stock_fn, lambda: e.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", gain))[0]))
    e.w32(LEVEL, word)
    e.uc.reg_write(UC_ARM_REG_R4, GRAIN)        # the renderer's grain register
    e.call(sym)
    return round(struct.unpack("<f", struct.pack("<I", e.uc.reg_read(UC_ARM_REG_S0) & 0xFFFFFFFF))[0], 4)


check("left pan gain 0.8, grain level 0.5: 0.4", pan_gain("gran_gain_l", 0x08061730, 0x4C564000) == 0.4)
check("right pan gain 0.8, grain level 0.25: 0.2", pan_gain("gran_gain_r", 0x08061778, 0x4C562000) == 0.2)
check("a grain without the tag plays at its pan gain", pan_gain("gran_gain_l", 0x08061730, 0x12344000) == 0.8)

knobs(250, 1000, q=9, mode=2, lvl=1000)
e.uc.mem_write(PAD + 0x589, b"\x00")
check("not a granular pad: no Scan, no detune", start_at(40000) == (40000, 0, 1.0, True))
e.stub(0x08057AB0, grain_start)

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
DEPTH = GRAN + 136 + 16 * 10 * 3 * EXT


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

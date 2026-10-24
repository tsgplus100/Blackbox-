"""Clip pads: Speed (src/stretch.c) under Unicorn.

Real code runs for the three wrappers and the store lookups. Stubbed: the clip-length worker (FUN_08064a94), its
tick -> frame conversion (FUN_08070420) and the class B pad's block (FUN_08067fa4), each recording what it saw.
NOT checked: the real FUN_08064a94 end to end (it needs a loaded sample), how a clip sounds at another Speed, that the
Pos page shows the knob.
Stretch (stretch_read): the real engine over a source the stubbed fetches serve from a numpy array; the stock reader
it stands in for is not run (what it would have used is worked out here with its arithmetic). NOT checked: the sound
on the unit, CPU time per block.
"""
import struct
import sys

import numpy as np
from unicorn.arm_const import UC_ARM_REG_R0 as ARG0, UC_ARM_REG_S0, UC_ARM_REG_SP

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


def branch_target(at):
    h1, h2 = struct.unpack("<HH", img[at - BASE:at - BASE + 4])
    s = (h1 >> 10) & 1
    i1, i2 = 1 - (((h2 >> 13) & 1) ^ s), 1 - (((h2 >> 11) & 1) ^ s)
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    return at + 4 + off - (s << 25), bool(h2 & 0x4000)


def words(buf, addr, n):
    return list(struct.unpack(f"<{n}H", buf[addr - BASE:addr - BASE + 2 * n]))


# ---- the image
for at in (0x08066E9E, 0x08066FAC, 0x080679CE, 0x08068312, 0x0806838A, 0x0806840C, 0x08068632, 0x080686A8):
    check(f"bl FUN_08064a94 @{at:#x} -> clip_duration", branch_target(at) == (e.sym["clip_duration"], True))
check("the tail call @0x08067b38 stays a tail call, to clip_duration", branch_target(0x08067B38) == (e.sym["clip_duration"], False))
check("both tick conversions in FUN_08064a94 -> clip_ticks",
      branch_target(0x08064B9E) == (e.sym["clip_ticks"], True) and branch_target(0x08064E54) == (e.sym["clip_ticks"], True))
check("the class B pad's block -> clip_process", branch_target(0x08068C6A) == (e.sym["clip_process"], True))
for name, page in (("Clip Pos page", 0x080EF990), ("second-copy Clip Pos page", 0x080EF288)):
    check(f"{name}: Loop Mode, Beat Count, Quant Size, Sync, then Speed",
          words(stock, page, 5) == [0x8D, 0xD2, 0x47, 0x94, 0] and words(img, page, 6) == [0x8D, 0xD2, 0x47, 0x94, 0x1CF, 0], words(img, page, 6))

# ---- memory as master.c leaves it
e.uc.mem_map(0x38800000, 0x1000)
e.uc.mem_map(0x58024000, 0x1000)
e.uc.mem_map(0xC0000000, 0x90000)
e.w32(0x38800F70, 0xC0000000)
e.w32(0x38800F74, 0xC0000000 ^ 0x5052534D)
ST = 0xC0000000 + 0x56800 + 0x2D100 + 0xF00
APPPADS = 0x24020088 + 0x1840
PAD, CTX, NOW, OUT, TICKS = 0x24030000, 0x24031000, 0x24031100, 0x24031200, 0x24031300
e.uc.mem_write(PAD, bytes(0x100))
e.w32(PAD + 0x18, 0x0102)                     # row 1, col 2: pad 7
e.w32(PAD + 0x24, 0x24032000)                 # a sample is there
e.w32(CTX, NOW)
Q = 6


def speed(v):
    """Pad 7's store: Speed v, or no Speed at all (None: a preset from before it)."""
    arr = 0x24033000
    if v is None:
        e.uc.mem_write(arr, struct.pack("<HHI", 0x93, 0, 0))
    else:
        e.uc.mem_write(arr, struct.pack("<HHIHHI", 0x93, 0, 0, 0x1CF, 0, v))
    store = APPPADS + (Q >> 2) * 0xF0 + (Q & 3) * 0x30
    e.w32(store + 4, arr)
    e.uc.mem_write(store + 10, struct.pack("<H", 1 if v is None else 2))


seen = []
e.stub(0x08064A94, lambda: seen.append((e.arg(0), e.arg(1), e.r8(ST + 4 + 16))))
conv = []
e.stub(0x08070420, lambda: conv.append(struct.unpack("<q", e.uc.mem_read(e.arg(1), 8))[0]))
blocks = []
e.stub(0x08067FA4, lambda: blocks.append((e.arg(0), e.arg(1))), value=1)


def ticks(t, now):
    e.uc.mem_write(ST + 4 + 16, bytes([now]))
    e.uc.mem_write(TICKS, struct.pack("<q", t))
    conv.clear()
    e.call("clip_ticks", OUT, TICKS)
    return conv[0]


speed(5)
seen.clear()
e.call("clip_duration", PAD, NOW)
check("clip_duration: the worker runs with this pad's Speed (x1) announced, and its arguments as they were",
      seen == [(PAD, NOW, 6)] and e.r8(ST + 4 + 16) == 0, seen)
SP = ["x1/4", "x1/3", "x1/2", "x2/3", "x3/4", "x1", "x3/2", "x2", "x3", "x4"]
want = {0: 4 * 3840, 1: 3 * 3840, 2: 2 * 3840, 3: 5760, 4: 5120, 5: 3840, 6: 2560, 7: 1920, 8: 1280, 9: 960}
got = {v: ticks(3840, v + 1) for v in range(10)}
check("ticks of a 4-beat clip (3840) by Speed: x1/4 16 beats ... x1 4 ... x4 1 beat", got == want, got)
check("no Speed announced (a tick conversion outside FUN_08064a94): left alone", ticks(3840, 0) == 3840)
speed(None)
seen.clear()
e.call("clip_duration", PAD, NOW)
check("a store without Speed (an older preset) counts as x1, not stock's 0 (x1/4)", seen[0][2] == 6, seen)
speed(2)
e.uc.mem_write(ST + 4 + Q, b"\x06")            # last worked out at x1
seen.clear()
blocks.clear()
e.call("clip_process", PAD, CTX)
check("Speed turned to x1/2: the block reruns the clip length with it, then the stock block", seen == [(PAD, NOW, 3)] and blocks == [(PAD, CTX)], (seen, blocks))
seen.clear()
e.call("clip_process", PAD, CTX)
check("...once", seen == [], seen)
e.w32(PAD + 0x24, 0)
speed(7)
seen.clear()
e.call("clip_process", PAD, CTX)
check("no sample loaded: nothing to rerun", seen == [], seen)

# ---- Stretch
check("Clip LFO pages: Waveform, Rate, Depth, then LFO 2's Wave, Rate, Depth, Trig, Offset (both copies)",
      all(words(img, p, 8) == [8, 9, 0xB, 0x1A9, 0x1AA, 0x1C8, 0x1AB, 0x1AC] for p in (0x080EF9D8, 0x080EF2D0)))
check("Clip page 3 (Strch): Mode, Grain, Jitter, Freeze, LFO 3 Wave, Rate, Depth, Trig (both copies)",
      all(words(img, p, 8) == [0x192, 0x193, 0x195, 0x196, 0x1AD, 0x1AE, 0x1C9, 0x1AF] for p in (0x080EFA20, 0x080EF318)))
check("Slicer page 3 keeps LFO+", words(img, 0x080EF7E0 + 3 * 0x48, 8) == list(range(0x1A9, 0x1B1)))

SRC, SCR, OUTB, USED, FRAC, RES = 0x24040000, 0x24034000, 0x24036000, 0x24031400, 0x24031404, 0x24031408
SCAP, SL, SR, OL, OR = 600, 0x24034100, 0x24035100, 0x24036100, 0x24037100
LAYER = PAD + 0x260
e.uc.mem_write(PAD, bytes(0x800))
e.w32(PAD + 0x18, 0x0102)
e.w32(PAD + 0x24, SRC)
source = {"l": np.zeros(1), "r": np.zeros(1)}
stereo = [0]
e.stub(0x080636F0, fn=lambda: e.uc.reg_write(ARG0, len(source["l"])))
e.stub(0x08063790, fn=lambda: e.uc.reg_write(ARG0, stereo[0]))


def serve(arr, dst, n, pos):
    assert pos >= 0 and pos + n <= len(arr), (pos, n, len(arr))
    e.uc.mem_write(dst, np.asarray(arr[pos:pos + n], np.float32).tobytes())


fetched = []
e.stub(0x08063634, lambda: (fetched.append((e.arg(3), e.arg(2))), serve(source["l"], e.arg(1), e.arg(2), e.arg(3))))
e.stub(0x08063608, lambda: (serve(source["l"], e.arg(1), e.arg(3), e.r32(e.uc.reg_read(UC_ARM_REG_SP))),
                            serve(source["r"], e.arg(2), e.arg(3), e.r32(e.uc.reg_read(UC_ARM_REG_SP)))))
e.stub(0x0804D8E8, fn=lambda: e.uc.reg_write(ARG0, SCAP))
e.stub(0x0804D934, fn=lambda: e.uc.reg_write(ARG0, SL if e.arg(0) == SCR else OL))
e.stub(0x0804DA0C, lambda: (e.w32(e.arg(1), SL if e.arg(0) == SCR else OL), e.w32(e.arg(2), SR if e.arg(0) == SCR else OR)))


def settings(**kv):
    ids_ = {"speed": 0x1CF, "mode": 0x192, "grain": 0x193, "jitter": 0x195, "freeze": 0x196}
    arr = 0x24033000
    blob = b"".join(struct.pack("<HHI", ids_[k], 0, v) for k, v in kv.items())
    e.uc.mem_write(arr, blob)
    store = APPPADS + (Q >> 2) * 0xF0 + (Q & 3) * 0x30
    e.w32(store + 4, arr)
    e.uc.mem_write(store + 10, struct.pack("<H", len(kv)))


def read(rate, pos, n, frac=0.0, tempo=1.0, layer=LAYER):
    e.uc.mem_write(layer + 0x18, struct.pack("<f", tempo))
    e.uc.mem_write(layer + 0x1C, struct.pack("<f", frac))
    e.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", rate))[0])
    e.uc.mem_write(STACK, struct.pack("<IIII", layer + 0x1C, SCR, OUTB, RES))
    e.call("stretch_read", PAD, pos, n, USED)
    r = e.uc.reg_read(ARG0)
    r = r - (1 << 32) if r & 0x80000000 else r
    out = np.frombuffer(bytes(e.uc.mem_read(OL, 4 * n)), np.float32).copy()
    outr = np.frombuffer(bytes(e.uc.mem_read(OR, 4 * n)), np.float32).copy()
    f = struct.unpack("<f", e.uc.mem_read(layer + 0x1C, 4))[0]
    return r, e.r32(USED), f, out, outr


def stock_advance(rate, frac, n):
    f, idx = np.float32(frac), 0
    for _ in range(n):
        adv = np.float32(np.float32(rate) + f)
        st = int(adv)
        idx += st
        f = np.float32(adv - np.float32(st))
    return idx, float(f)


def play(rate, tempo, blocks, n=128, pos=1000, layer=LAYER):
    """blocks of n frames, the position advancing as stock's would; the output and the positions"""
    outs, frac, poss = [], 0.0, []
    for _ in range(blocks):
        r, used, frac2, out, _r = read(rate, pos, n, frac, tempo, layer)
        assert r == 1, r
        want = stock_advance(rate, frac, n)
        poss.append((used, frac2, want))
        outs.append(out)
        pos += used
        frac = frac2
    return np.concatenate(outs), poss, pos


settings(mode=0)
source["l"] = np.ones(200000, np.float32)
check("Mode Repitch: not stretch_read's to read (-1, the reader goes on as before)", read(1.0, 1000, 128)[0] == -1)
settings()
check("a store without Mode (an older preset): Repitch", read(1.0, 1000, 128)[0] == -1)

settings(mode=1, grain=400, jitter=0)
out, poss, _ = play(0.5, 0.5, 40)
check("Stretch: the frames used and the fraction are exactly stock's for that rate (playhead, Sync, drift untouched)",
      all(u == w[0] and abs(f - w[1]) < 1e-6 for u, f, w in poss), poss[:3])
check("a constant source comes out constant: the first frame at full level (a fresh start), Hann pairs summing to 1",
      abs(out[0] - 1.0) < 0.01 and np.max(np.abs(out - 1.0)) < 0.01, (out[:4], np.max(np.abs(out - 1.0))))

fs, hz = 48000.0, 441.0
t = np.arange(400000)
source["l"] = np.sin(2 * np.pi * hz * t / fs).astype(np.float32)


def freq(x):
    """the spectrum's peak, interpolated (zero crossings miscount where grains overlap out of phase)"""
    m = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8 * len(x)))
    k = int(np.argmax(m))
    a, b, c = m[k - 1], m[k], m[k + 1]
    return (k + 0.5 * (a - c) / (a - 2 * b + c)) * fs / (8 * len(x))


settings(mode=1, grain=400, jitter=0)
out, poss, end = play(0.5, 0.5, 60, pos=2000)
check("x1/2 (tempo factor 0.5, pitch 0): the pitch stays 441 Hz, not stock's octave down", abs(freq(out[2000:]) - hz) < 6, freq(out[2000:]))
check("...while the playhead moves at half speed (60 blocks of 128 = 3840 source frames)", end - 2000 == 3840, end)
sp = np.abs(np.fft.rfft(out[2000:] * np.hanning(len(out) - 2000))) ** 2
fb = np.fft.rfftfreq(len(out) - 2000, 1 / fs)
pure = float(sp[np.abs(fb - hz) < 30].sum() / sp.sum())
check("...a clean tone: 95 % of the energy within 30 Hz of 441 (WSOLA keeps the grains in phase)", pure > 0.95, pure)
rms = float(np.sqrt(np.mean(out[2000:] ** 2)))
check("...at the source's level (RMS 0.707, within 10 %)", 0.64 < rms < 0.78, rms)
out, poss, end = play(2.0, 2.0, 30, pos=2000, layer=PAD + 0x670)
check("x2 on the other layer: pitch kept, playhead twice as fast", abs(freq(out[1000:]) - hz) < 6 and end - 2000 == 7680, (freq(out[1000:]), end))
out, poss, end = play(1.0, 0.5, 60, pos=2000)
check("x1/2 with the pitch up an octave (rate 1.0 / tempo 0.5): 882 Hz", abs(freq(out[2000:]) - 2 * hz) < 12, freq(out[2000:]))

source["l"] = np.arange(400000, dtype=np.float32)
settings(mode=1, grain=400, jitter=0, freeze=1)
out, poss, end = play(1.0, 1.0, 50, pos=5000)
check("Freeze: the playhead runs on (6400 frames) but the grains keep reading from where it froze",
      end - 5000 == 6400 and out[-128:].max() < 5000 + 3000, (end, out[-128:].max()))
settings(mode=1, grain=400, jitter=0, freeze=0)
out, poss, end = play(1.0, 1.0, 10, pos=end)
check("...Freeze off: back with the playhead", abs(out[-1] - (end - 1)) < 2500, (out[-1], end))

stereo[0] = 1
source["l"] = np.ones(200000, np.float32)
source["r"] = -np.ones(200000, np.float32)
settings(mode=1, grain=1000, jitter=1000)
r, used, f, outl, outr = read(0.75, 3000, 128, 0.0, 0.75)
check("a stereo clip: both channels, each its own (left +1, right -1 out)", r == 1 and abs(outl - 1).max() < 0.01 and abs(outr + 1).max() < 0.01, (outl[:3], outr[:3]))
stereo[0] = 0
source["l"] = np.ones(5000, np.float32)
settings(mode=1, grain=400)
check("past the source's end (+0xff), as stock: 0", read(1.0, 5000 + 0x100, 128)[0] == 0)
r, used, f, out, _r = read(1.0, 4990, 128)
check("near the end: frames past it are silence, nothing fetched beyond it", r == 1 and out[5] > 0.5 and abs(out[-1]) < 1e-6, out[[5, -1]])

# ---- Grain / Jitter as destinations
ST2 = 0xC0000000 + 0x56800 + 0x2E100
UNTIL = ST2 + 8 + (Q * 2) * 84 + 12                  # pad 7's first layer: frames to its next grain


def fresh_until(**kv):
    settings(mode=1, **kv)
    source["l"] = np.ones(200000, np.float32)
    read(1.0, 77777, 128)                            # a jump: a fresh start, then the first grain at once
    return e.r32(UNTIL)


check("Grain 0 %: 10 ms grains, the next due half a grain (240 frames) after the first", fresh_until(grain=0) == 240 - 128, e.r32(UNTIL))
e.w32(PAD, 0x080D0890)                               # a class B pad
CC = 0x24031500
e.uc.mem_write(CC, struct.pack("<If", 0, 1.0))      # a CC at full
e.stub(0x08063DF0)
e.uc.reg_write(UC_ARM_REG_S0, struct.unpack("<I", struct.pack("<f", 1.0))[0])
e.call("gran_attach_b", PAD, CC, 0x193, 1)
check("a CC on Grain at 100 % (class B vtable +0x40 -> gran_attach_b -> stretch_attach): 200 ms grains", fresh_until(grain=0) == 4800 - 128, e.r32(UNTIL))
e.uc.mem_write(CC, struct.pack("<If", 0, 0.5))
check("...at half: Grain 50 %, 10 + 190 x 0.25 = 57.5 ms", fresh_until(grain=0) == 1380 - 128, e.r32(UNTIL))
e.stub(0x08076080)
e.call("gran_reset_b", PAD + 0x440)
check("the pad's reset (a preset load) forgets it", fresh_until(grain=0) == 240 - 128, e.r32(UNTIL))
CMD = 0x24031600
setups = []
e.stub(0x08067018, lambda: setups.append(e.arg(1)))
e.uc.mem_write(CMD, struct.pack("<IIIIIHh", 0, 0, 0, 0x193, 2, 1, 1000))   # target Grain, slot 2, source ENV, 100 %
e.call("env_mod_setup_b", PAD, CMD)
e.uc.mem_write(PAD + 0x260 + 0x258 + 0x24 + 4, struct.pack("<f", 1.0))  # the first layer's envelope at full
check("ENV on Grain through the class B slot setup (env_mod_setup_b -> stretch_slot, not stock's): the layer's own envelope",
      setups == [] and fresh_until(grain=0) == 4800 - 128, (setups, e.r32(UNTIL)))
e.uc.mem_write(CMD, struct.pack("<IIIIIHh", 0, 0, 0, 0x193, 2, 0xD, 1000))   # the slot now VEL, which stretch.c cannot read
e.call("env_mod_setup_b", PAD, CMD)
check("...the same slot set to a source it cannot read: emptied", fresh_until(grain=0) == 240 - 128, e.r32(UNTIL))
e.uc.mem_write(CMD, struct.pack("<IIIIIHh", 0, 0, 0, 0x5C, 0, 0xD, 500))
e.call("env_mod_setup_b", PAD, CMD)
check("VEL on another target: stock's setup, as before", setups == [CMD], setups)

# ---- cost
from unicorn import UC_HOOK_CODE
source["l"] = np.sin(2 * np.pi * hz * np.arange(400000) / fs).astype(np.float32)
settings(mode=1, grain=400, jitter=0)
cnt = [0]
h = e.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s_, _: cnt.__setitem__(0, cnt[0] + 1))
per = []
pos, frac = 3000, 0.0
for b in range(24):
    cnt[0] = 0
    r, used, frac, _o, _r = read(0.5, pos, 128, frac, 0.5)
    pos += used
    per.append(cnt[0])
e.uc.hook_del(h)
print(f"     cost: {min(per[1:])} .. {max(per[1:])} instructions per 128-frame mono block (a grain's start, WSOLA, is the peak)")

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

"""Clip pads: Speed (src/stretch.c) under Unicorn.

Real code runs for the three wrappers and the store lookups. Stubbed: the clip-length worker (FUN_08064a94), its
tick -> frame conversion (FUN_08070420) and the class B pad's block (FUN_08067fa4), each recording what it saw.
NOT checked: the real FUN_08064a94 end to end (it needs a loaded sample), how a clip sounds at another Speed, that the
Pos page shows the knob.
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

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

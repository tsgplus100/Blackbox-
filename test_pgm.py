"""PGM Out (src/pgm.c) under Unicorn.

Real code runs for pgm_tick, the settings lookup (FUN_08093e9c) over a global settings store built here, and
master.c's block lookup. Stubbed: stock's MIDI send (FUN_08044a0e, recorded: the 5-byte message and both flags).
NOT checked: the jacks and the USB host really putting it out (stock's own path, as for its clock), the Tools > MIDI
page showing the two rows, a synth answering.
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


def words(buf, addr, n):
    return list(struct.unpack(f"<{n}H", buf[addr - BASE:addr - BASE + 2 * n]))


check("Tools > MIDI page: stock's six rows, then PGM Out and PGM Ch",
      words(stock, 0x080EEDA8, 7) == [0x76, 0xE2, 0x79, 0xD3, 0x71, 0x7B, 0]
      and words(img, 0x080EEDA8, 9) == [0x76, 0xE2, 0x79, 0xD3, 0x71, 0x7B, 0x1F0, 0x194, 0], words(img, 0x080EEDA8, 9))

e.uc.mem_map(0x38800000, 0x1000)
e.uc.mem_map(0x58024000, 0x1000)
e.uc.mem_map(0xC0000000, 0x90000)
e.w32(0x38800F70, 0xC0000000)
e.w32(0x38800F74, 0xC0000000 ^ 0x5052534D)
STORE, ARR = 0x24020088 + 0x8C90, 0x24070000
sent = []
e.stub(0x08044A0E, lambda: sent.append((e.arg(0), bytes(e.uc.mem_read(e.arg(1), 5)), e.arg(2), e.arg(3))))


def settings(prog=None, ch=None):
    entries = [(0x9C, 77)] + ([(0x1F0, prog)] if prog is not None else []) + ([(0x194, ch)] if ch is not None else [])
    e.uc.mem_write(ARR, b"".join(struct.pack("<HHI", k, 0, v) for k, v in entries))
    e.w32(STORE + 4, ARR)
    e.uc.mem_write(STORE + 10, struct.pack("<H", len(entries)))


def tick():
    sent.clear()
    e.call("pgm_tick")
    return list(sent)


settings(5, 3)
check("after power-on (a fresh state): the first tick sends program 5 on channel 3 = C2 04, to the jacks and USB",
      tick() == [(0x24002E88, bytes([0xC2, 0x04, 0, 0, 2]), 1, 1)], sent)
check("...once: the next ticks send nothing", tick() == [] and tick() == [])
settings(6, 3)
check("PGM Out turned to 6: C2 05", tick() == [(0x24002E88, bytes([0xC2, 0x05, 0, 0, 2]), 1, 1)], sent)
settings(6, 16)
check("PGM Ch turned to 16: the same program again, on channel 16 (CF 05)", tick() == [(0x24002E88, bytes([0xCF, 0x05, 0, 0, 2]), 1, 1)], sent)
settings(128, 1)
check("program 128 on channel 1: C0 7F", tick() == [(0x24002E88, bytes([0xC0, 0x7F, 0, 0, 2]), 1, 1)], sent)
settings(0, 1)
check("PGM Out 0 (off): nothing sent", tick() == [])
settings(128, 1)
check("...and back to 128 from off: sent again", len(tick()) == 1)
settings()
check("a project from before PGM Out (no entries): nothing sent", tick() == [])
settings(128, 1)
check("...and loading one with the same values as last sent: nothing new", tick() == [])
e.uc.mem_write(0xC0000000 + 0x56800 + 0x2D100 + 0xF80, bytes(8))    # master_alloc at boot leaves the block dirty or clean
check("a new power-on (the state's magic gone): sent again", len(tick()) == 1)

print(f"\n{fails} failure(s)" if fails else "\nall passed")
sys.exit(1 if fails else 0)

# blackbox-mod

An unofficial feature mod for the **original 1010music Blackbox** (not the Blackbox 2), built on stock firmware 3.1.9.

> **Not affiliated with, endorsed by, or supported by 1010music.** This repository does not contain 1010music's
> firmware. You supply your own copy, downloaded from 1010music, and patch it yourself. Use at your own risk: this is
> tested on a small number of units, it may misbehave on yours, and running modified firmware may affect your warranty. Don't ask
> 1010music for support on a modded unit; flash stock first.

**Get new builds by email:** sign up at <https://justinjoe.com/blackbox-mod> and I'll send a note when a new build is
out (new FX, fixes). That's all the list is for.

## This fork: GRAINBOX 01 (granular modulation, LFO Depth, Clip Speed and Stretch)

A fork of JOEBOX 1 that opens up Granular pads to modulation and gives LFO 2 / 3 a Depth. TOOLS shows `GRAINBOX` (the screen holds eight characters; the number is in the patch's name). Builds up to
JBGRAN11 were named JBGRANn.
Everything in JOEBOX 1 is still there.

- **Grain Size and Density as modulation destinations.** Their MOD page opens like any other knob's. Every source
  works: VEL, KEY, LFO, LFO2, LFO3, ENV, the MIDI ones (PTCH, MODW, MVOL, MPAN, CC) and the duck shapes (EXP1, EXP2,
  PUMP, LINR). 100 % is the knob's whole range.
  Grain Size is read as each grain starts, so every grain keeps the size it was born with. Density moves once per
  engine block (5.3 ms) the same way turning its knob does; per-note sources come from the pad's first playing voice.
- **Window, Scatter and Pan Rnd as modulation destinations** (JBGRAN 5), with the same sources, read as each grain
  starts and moved along each knob's own curve (Window's cube, Scatter's 97 steps). Window is the random spread of
  each grain's read position; Pan Rnd its random place in the stereo field; Scatter is not random: it delays every
  grain of a cycle but the first, and only while Density is under 50 % (above that there is no gap and the engine
  ignores it).
- **Scan and Pitch Rnd** (JBGRAN 6), knobs of the mod's own, both modulation destinations: Scan moves where each
  grain reads, 0..100 % of the sample, wrapping round it (an LFO on it sweeps the grains through the sample; with
  Speed at 0, Scan alone says where they read). Pitch Rnd detunes each grain at random, up to an octave either way
  at 100 % (8 % is about a semitone).
- **Pitch Mode and Lvl Rnd** (JBGRAN 7). Pitch Mode snaps Pitch Rnd's detune to a set: Free (as before), Semi, Oct,
  5th+Oct, Major, Minor, Pent (minor pentatonic), Shimmr (an octave up or nothing). Pitch Rnd stays the reach: Oct
  at 100 % leaves about half the grains as they are and throws the rest an octave either way; under 50 % nothing
  reaches the octave. Lvl Rnd gives each grain its own random level, down to silence at 100 % (a destination too).
- **Power-on screen** (JBGRAN 8): SYEN, in italic, built of the screen font's `#` over six lines (312 x 96
  pixels), instead of "blackbox / by 1010music / 3.1.9". Error messages (no card, a file missing) still show over
  its lower lines. `src/splash.c`.
- **Munchi's engine in bank 2** (JBGRAN 9): the delay itself moved, unchanged, into the second flash bank
  (`src/munchi_dsp.cpp`), which frees ~6.4 KB of bank 1. Munchi now needs `BBEXTRA.BIN` like Prism and Confetti:
  without the matching one it reads `---` and plays the stock delay.
- **Clip Speed** (JBGRAN10): `Speed` on a Clip pad's Pos tab, after Sync: x1/4, x1/3, x1/2, x2/3, x3/4, x1, x3/2,
  x2, x3, x4. The clip's length on the grid (Beat Count, or Auto) is divided by it, so x1/2 takes twice as many beats
  and stays in sync. In Mode Repitch the clip plays that the stock way, by varispeed (x1/2 is an octave down, like
  tape); Stretch keeps the pitch (below). A preset from before Speed plays at x1. `src/stretch.c`.
- **Clip Stretch** (JBGRAN11; working from GRAINBOX 01, JBGRAN11's never engaged on a unit): a Clip pad's fourth
  tab is now `Strch` (Slicer pads keep LFO+): `Mode` (Repitch, Stretch, Texture), `Grain` (10..200 ms, 40 % = 40 ms), `Jitter`, `Freeze`, then LFO 3's Wave, Rate, Depth, Trig. In Stretch
  the playhead, Sync, loop points and handovers are exactly stock's; what you hear is grains read from the playhead
  at the pitch alone (Pitch and its modulation still apply), so x1/2 is twice as long at the same pitch, and a clip
  at another tempo than its own keeps its key too. Each grain is a Hann window, half overlapping the last, and its
  start is moved (within 10 ms) to where the source best continues the grain before (WSOLA), so tones stay in tune
  and do not buzz; a note or a handover starts at full level, so attacks stay sharp. Short grains suit drums, long
  ones pads and voices. Jitter moves each grain's start by up to half a grain at random (a smear); Freeze holds the
  point grains read from while the clip runs on in time. Grain and Jitter are modulation destinations: LFO2, LFO3,
  ENV, CC and the duck shapes (the sources Clip pads have). Clip LFO tab: like Granular, LFO 1's Waveform, Rate,
  Depth, then LFO 2's five. A preset from before Mode plays Repitch. `Texture` (GRAINBOX 01) is the same without the
  lining up: grains start where they fall, so Grain and Jitter are heard as grain (a cloud, a buzz at short sizes).
  Reverse playback stays stock (Repitch).
- **Granular pad pages.** LFO tab: LFO 1's Waveform, Rate, Depth (its Beat Sync and Trig are off the page and keep
  their values), then all of LFO 2: `2 Wave`, `2 Rate`, `2 Depth`, `2 Trig`, `2 Offset`. Gran tab: the six grain
  knobs, then `Pitch Rnd`, `Pitch Mode`. Pos tab: its six, then `Scan`, `Lvl Rnd`. Conf tab: `Insert` and `Input` under Saturation (the per-pad insert effect
  and the live input, as on the other pads: Granular pads run the same pad block, so they already took them; only
  the rows were missing). Eight knobs a page is all the screen has, so LFO 3 has no knobs
  on these pads; as a source it runs on its defaults (Random, 1/4, Retrig).
- **LFO 2 / 3 Depth** (`2 Depth`, `3 Depth`, 0..100 %, default 100 % = as before): on the LFO tab after the stock
  LFO's knobs (Granular pads: 2 Depth only, on the LFO tab). Both are modulation destinations too, so a CC can ride an LFO's
  depth. On Sample, Multisample and Granular pads every source reaches them; on Clip and Slicer pads only CC and the
  duck shapes do (those pads keep no slot list). A preset from before Depth existed plays at full depth.

Install as below, with the patch for this build: `python3 apply.py path/to/BLACKBOX.bin docs/blackbox-mod-grainbox-01.json`
gives `BLACKBOX.bin` and `BBEXTRA.BIN`; both go on the card. JB1 GRAN and JBGRAN10 ran on a unit; Stretch
(GRAINBOX 01) has only run in the emulator so far. Bank 1 has ~2 KB left. Keep your stock file (and JOEBOX 1's two
files) to go back. Code: `src/gran.c`, `src/lfo.c`, `src/stretch.c`, `patches/gran.py`, `patches/stretch.py`,
`test_gran.py`, `test_lfo.py`, `test_stretch.py`.

## What it adds (JOEBOX 1)

Releases have names now. JOEBOX 1 is the one after 3.1.n, and TOOLS shows it as the version.

**Updated 2026-10-17, same name.** The first JOEBOX 1 got some units stuck restarting at the logo. This build fixes
that (two of those units have confirmed it boots now). It also fixes USB audio not showing up when the compressor is
on Limit, and the insert models have their own names (Pebble, Electra, Jet). If you installed JOEBOX 1 before, patch
again and put both files on the card the same way.

New since 3.1.n:

- **Live input on a pad**: an "Input" row on a pad's Conf tab (Off, In 1, In 2, In 1+2). The audio input plays
  through that pad, so it gets the pad's insert, its reverb and delay sends, its level and pan, and the master FX.
  Muting the pad mutes it.
- **An insert effect per pad**: "Insert" on the Conf tab, INFO opens its knobs. Phaser (five models), Flanger
  (four models) or Gate. Sample, Multisample, Clip and Slicer pads.
- **LFO 2 and LFO 3 per pad**, on a new "LFO+" tab: twelve shapes (the stock nine plus two exponential ramps and
  a smooth random), tempo-synced rates from 32 bars to 1/32, Free / Retrig / Once, and a start Offset. They appear
  as LFO2 and LFO3 in the modulation Source list.
- **ENV and KEY as modulation sources**: the pad's own envelope, and key tracking.
- **Master FX slot** on TOOLS: VHS (wow, flutter, saturation, dropouts, noise) or Prism, a four-block multi-effect
  (drive, motion, space, texture; twenty effects). INFO on the row opens the knobs.
- **Delay types**: Motion (the stock delay with tremolo, filter, duck or swell on the repeats), Relapse (a memory
  echo) and Confetti (a granular micro-looper), next to Delay and Munchi.
- **Smash**, a three-band compressor, in the compressor list, and a **master clipper** after the compressor
  (Clean or Diode).
- **Fidelity**: the S950 mode rebuilt from the machine's schematic, S950 Lo and SP 45 added, and the machine modes
  now work on Clip and Slicer pads.
- **Record pre-roll**: TOOLS, Rec, Pre-roll (1, 2, 4 or 8 bars). The loop plays that long before the recording
  starts, so a resampled loop holds its own tails.
- **Rotate a sequence**: in the piano roll's Event editor the top-right knob shifts the whole layer a step at a time.
- **MUTE and SOLO on the Pads screen.**
- **USB on the power jack**: plugged into a computer the Blackbox is a class-compliant USB MIDI device and sends
  its three stereo outputs as six channels of 24-bit 48 kHz audio.
- **Load readout on TOOLS**: average / peak, for example `62/75%`. Over about 100% peak the engine is out of time
  and you will hear it.
- **Fixed**: the naming keyboard's 9 key (3.1.n typed "n").

From 3.1.n and earlier:

- **Solo** in the mixer: MIX cycles Mixer → Mute → Solo. Tap pads to solo them (yellow).
- **Slicer knobs**: on the waveform screen, bottom-left = slice Start, bottom-right = slice End, top-right = Zoom.
- **Pad-1 ducker**: four modulation Sources (EXP1, EXP2, PUMP, LINR) that fire when pad 1 plays. Put your kick
  on pad 1, set a negative Amount on another pad's Level, and you have sidechain pumping. About 0.65 dB per 1%.
- **Chords on the Keys screen**: top-right knob picks a shape (Tri, 7th, 9th, Su2, Su4, 6th, Ad9, Pwr, Oct, Opn, Shl,
  Qrt, m7, m9, Mj7). In-scale shapes follow the Keys Scale/Root. Chords record into sequences.
- **Note conditions**: the piano roll's PLAY list gains 1:2 … 8:8 ("play the Ath of every B loops").
- **Fidelity** (was Interp): sample-rate crunch plus machine modes SP1200, SP-12, S950, MPC60 and SP Raw, with
  drop-sample pitching.
- **Filter**: 24 dB/oct state-variable filter; drive comes in as Res goes past noon.
- **Saturation** (was Overdrive): soft saturation in place of the hard clip.
- **Master compressor models**: Stock, Glue, Punch, Opto, Squash, Limit, plus a Comp Thresh setting.
- **Reverb Type**: Plate (stock) or Room.
- **Munchi**, a port of the CHOMPI TEMPO granular delay, as a delay type.
- **Sequencer fix**: a note added just ahead of the playhead plays on that pass.

### Known issues

- This has run on very few units. If yours does something this list doesn't mention, I want to hear about it.
- The Blackbox only has so much CPU, and the mod lets you spend all of it. Room and Prism are the expensive ones.
  Watch the load readout on TOOLS.
- LFO 2 / 3, ENV, the insert and Input are not on Granular pads.
- A note placed very close ahead of the playhead is still sometimes silent.
- Chords need the pad out of Mono Poly Mode.
- Presets saved on an older mod build can come back with a neighbouring Fidelity or delay Type, because those
  lists gained entries. Set them again and save.
- USB on the power jack doesn't work on every unit. On some, that jack's USB data side is dead with any firmware,
  stock included (1010music never used it for data). The Blackbox boots and plays fine, you just don't get USB audio
  and MIDI. If your computer never sees the Blackbox over that jack, it's the unit, not the mod.
- The machine Fidelity modes (SP1200, SP-12, MPC60, SP Raw, SP 45) can come out grittier on one hit than the next.
  Fixed in the next build.

## Install

1. Download **blackbox 3.1.9** from <https://1010music.com/downloads> and unzip it. You need the `BLACKBOX.bin` inside.
2. Patch it, either way:
   - **In your browser:** <https://j3threejay.github.io/blackbox-mod/>. Your file never leaves your computer.
   - **With Python 3:** `python3 apply.py path/to/BLACKBOX.bin` → `out/blackbox-mod-<version>/`
3. Keep the stock `BLACKBOX.bin` somewhere safe. That file is your way back.
4. Copy what the patcher gives you to the **root** of the Blackbox's microSD card. Newer builds are **two files,
   `BLACKBOX.bin` and `BBEXTRA.BIN`, and both have to be there** (the browser patcher hands you a zip with both).
5. Install it the way you install any 1010music firmware update: hold BACK + INFO while powering on, and let go as
   soon as the install screen shows.
6. On a two-file build the Blackbox **restarts itself once**, a second or two into the first boot. That is the
   second file being installed. Leave the card in and the power on until it is back up.
7. TOOLS should show `JOEBOX 1`.

### The second file

Part of the mod (Prism, Confetti and the per-pad insert effects) is too big to fit beside 1010music's firmware. The
chip has a second block of flash that 1010music's installer never touches, so the mod keeps that code there and
installs it itself from `BBEXTRA.BIN` the first time it starts. The file holds this project's own code and nothing of
1010music's. You can leave it on the card.

- **`!` in front of the load figures on TOOLS** (for example `!62/75%`) means the second part is not installed or
  does not match this build. Everything else works; those three effects are switched off.
- **`---` in the Insert, Master FX or delay Type lists** is the same thing seen from the menus: the effect that
  belongs there is not installed. A preset that uses one keeps its setting and gets the effect back once it is.
- To fix either: put the `BBEXTRA.BIN` **from the same download** as your `BLACKBOX.bin` in the root of the card and
  power the Blackbox off and on. The two files are a matched pair; one from a different build is ignored.
- If the second part cannot be written after two tries, the mod stops trying and leaves those effects off rather
  than wearing the flash. Installing any build (with its own `BBEXTRA.BIN`) starts the count again.

**To go back to stock:** put the stock `BLACKBOX.bin` on the card and install it the same way. The second part
stays in the chip, unused: stock firmware never looks at it, and it does not touch the unit's calibration.

The patcher checks your file's SHA-256 before it writes anything
(`281ae303d32e5eb52adca7817a648a34e4bd3848017f26673dd9df3905f1341d`) and checks the result afterwards. It only
works on 3.1.9.

## Build from source

Needs `arm-none-eabi-gcc` and Python 3. Put your stock image at `firmware/BLACKBOX-3.1.9.bin` (see
`firmware/README.md`).

```
RELEASE=1 ./build.sh
python3 patch.py solo slice duck chord cond filter cpu od comp seqfix fx2 munchi master fault cave
```

That writes `out/<patchsets>/BLACKBOX.bin` and `out/BBEXTRA.BIN`, byte-identical to the release.
`python3 make_patch.py <image> "JOEBOX 1" --extra out/BBEXTRA.BIN` turns the pair into the release patch in `docs/`.
Without `RELEASE=1` you get a test build: a letter for a version, and a raw memory peek / poke over USB for
development. That one can write anywhere in the machine, so it is not in a release.

How it works: the stock image is left as it is. New code (`src/`) is compiled and appended after it, and a handful of
call sites and table entries (`patches/`) are redirected to the new code.

`./check.sh` builds, patches and runs every suite (`test_*.py`) under Unicorn (`pip install unicorn capstone numpy`).
Several of them hold the firmware's DSP against a build of the same C for the computer (`host/build.sh`, written
for macOS). They test the new functions, not a full boot. The first power-on of any build is the real test.

`ghidra/`, `disasm.py`, `findbl.py`, `findref.py` are the helpers used to find things in your own copy of the image.

## What is and isn't in this repository

In it: original source code, patch definitions (addresses and replacement bytes), tools, and MIT-licensed third-party
DSP with its notices ([THIRD_PARTY.md](THIRD_PARTY.md)).

Not in it, and please don't add it in issues, pull requests or forks: 1010music's firmware, patched firmware images,
decompiled or disassembled listings of the firmware, and 1010music's manuals or artwork.

## License

MIT for the original work here ([LICENSE](LICENSE)). "1010music" and "Blackbox" are trademarks of 1010music LLC, used
only to say what this mod is for.

If you are from 1010music and have a concern about anything here, open an issue or email justin.joe.dev@gmail.com and
it will be dealt with promptly.

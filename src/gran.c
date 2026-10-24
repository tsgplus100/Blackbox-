/*
 * Granular pads: Grain Size and Density as modulation destinations, and LFO 2 / 3 on the granular pad pages.
 * Also LFO 2 / 3 Depth (lfo.c's knobs 0x1c8 / 0x1c9) as modulation destinations, on every pad; and (JBGRAN 5)
 * Window, Scatter and Pan Rnd, the three other grain knobs a grain reads as it starts; and (JBGRAN 6) two knobs of
 * our own on the Granular Pos page, both destinations as well:
 *   Scan       0x1ca, 0..100 % of the sample: moves where a grain reads, wrapping round the sample. Moved per grain,
 *              so an LFO on it sweeps the grains through the sample (with Speed at 0 the playhead stands still and
 *              Scan alone says where they read).
 *   Pitch Rnd  0x1cb, 0..100 % = up to an octave either way: each grain plays at its own random detune.
 *   Pitch Mode 0x1cd (JBGRAN 7), a list: Free (any detune), or the detune snapped to the nearest step of a set:
 *              Semi, Oct, 5th+Oct, Major, Minor, Pent (minor pentatonic), Shimmr (octave up only); GRAINBOX 01 adds
 *              6th+Oct, m7+Oct, M7+Oct, 9th+Oct, 4th+5th, 5th+9th, 2 Oct, 2Oct+5, Maj7, Min7, Add9, 5ths (stacked
 *              fifths: 7, 14, 21). Pitch Rnd stays the reach, up to the set's top step (an octave for the first
 *              eight, Free included; 14 .. 24 semitones for those reaching past it), so with Oct at 100 % half the
 *              grains play as they are and half jump an octave.
 *   Lvl Rnd    0x1ce (JBGRAN 7): each grain at its own random level, down to silence at 100 %. Kept in the grain's
 *              spare word +0x3c (gain q15, tag "LV" in the top half) and applied where the grain's pan gains are
 *              worked out (gran_thunk.S, both calls in FUN_08057db8).
 * The engine never sees those two knobs (stock's pad ignores the ids): gran_pad_process reads them from the app's
 * pad store once a block and keeps them here.
 * Original 1010music Blackbox, firmware 3.1.9.
 *
 * A granular pad is a class A pad (the Sample pad's engine) with byte pad +0x589 set (mode 0x8b == 3). Its voices
 * play up to eight grains each (voice +0x13c: 0x40 bytes a grain); FUN_08057ab0 starts one, reading the pad's settings
 * as it is at that moment:
 *   pad +0x590  grain size in samples (knob 0x17c: 1200 + knob * 47744, floored to a multiple of 840; 0x57 = synced)
 *   pad +0x5a0  density, 0..1 (knob 0x180); FUN_08059158 turns it into a grain count (+0x58c) and a gap (+0x5a4)
 *   pad +0x594  window, samples (knob 0x5b: 1824000 * knob^3): each grain's read position moves by a random amount
 *               within it, centred
 *   pad +0x598  scatter, samples (knob 0x17e: the table at 0x080eb2a0, 97 steps, 0..39317): added to the start time of
 *               every grain but a cycle's first, and only while there is a gap (density under 50 %)
 *   pad +0x59c  pan random, 0..1 (knob 0x17f)
 * and where it reads: voice +0x10 (64-bit), the voice's playhead, or with pad +0x5b5 set (param 0x188 >= 0) a fixed
 * point, pad +0x5b8 per mille of the sample (FUN_080636f0(voice +0xc) frames long). The grain's rate is grain +0x24
 * (1.0 = as the voice plays), its envelope a Hann window across its whole length (the table at 0x080d26ac).
 * Stock modulates none of the grain knobs but Speed (0x5d): the voice attach (FUN_0805623c) has no parameter object
 * for them, and the pad screen only offers the MOD page for the 28 parameters in its list at 0x080f12bc.
 *
 * The pad's slot list (pad +0x4ec, envmod.c) keeps every VEL / KEY / LFO / LFO2 / LFO3 / ENV slot whatever its
 * target, so a slot on Grain Size or Density is already there; it just has nothing to act on. Here:
 *   Grain Size  gran_grain_start wraps every call of FUN_08057ab0 (respawn, voice start, density change): the size is
 *               moved by the sum of the slots, for that voice, while the grain is set up, then put back. Each grain
 *               keeps the size it started with. Window, Scatter and Pan Rnd the same way, each moved on its knob's
 *               own curve (the cube for Window, the table's steps for Scatter).
 *   Density     per pad, once per engine block (gran_pad_process wraps the pad's block, FUN_080596b0 @0x0805bb5a):
 *               the slots move the knob's value and FUN_08059158 is run, the same as turning the knob. Per-voice
 *               sources (VEL, KEY, LFO, ENV) are read from the pad's first playing voice.
 * Sources, all with Amount 100 % = the whole knob range:
 *   VEL KEY LFO LFO2 LFO3 ENV   the pad's slot list, per voice (the pad-level ones the same for every voice)
 *   PTCH MODW MVOL MPAN         the pad's MIDI objects (pad +0x13c / 0x124 / 0x12c / 0x134). Stock attaches these
 *                               straight to a parameter object and drops the slot; env_mod_setup keeps the slot in the
 *                               list for our two targets (gran_listed), the way it does for ENV.
 *   CC, EXP1..LINR              engine-wide sources, attached through the pad's vtable +0x40 (FUN_0805511c, which
 *                               has nothing for our targets). gran_attach keeps them per pad, three slots a target;
 *                               the pad's reset (cmd 0x40, a preset load) empties them (gran_reset).
 * LFO 2 / 3 Depth: lfo_tick (lfo.c) asks gran_depth for the sum on each. The slot-list part is worked out by the
 * class A pad's block (Sample, Multisample, Granular; per-voice sources from the first playing voice) and used once.
 * Clip and Slicer pads (class B) have no slot list: there only CC and EXP1..LINR reach Depth, through their own
 * vtable +0x40 (FUN_08063df0 @0x080d08d0, gran_attach_b) and reset (gran_reset_b).
 */
#include <stdint.h>

#pragma GCC optimize("Os", "no-tree-loop-distribute-patterns")

#define FN(addr) ((addr) | 1u)
typedef void (*grain_start_fn)(uint8_t *pad, void *now, uint8_t *voice, int first, int x, uint8_t *grain);
typedef int (*pad_process_fn)(uint8_t *pad, void **ctx);
typedef void (*density_fn)(uint8_t *pad, void *now);
typedef void (*attach_fn)(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount);
typedef void (*reset_fn)(uint8_t *obj);
typedef float (*powf_fn)(float x, float y);
typedef int (*length_fn)(const void *sample);
typedef int (*setting_fn)(const void *store, unsigned param);
#define VT_A 0x080d06c8u         /* class A pad's vtable */
#define VT_B 0x080d0890u         /* class B pad's vtable */
#define fw_grain_start ((grain_start_fn)FN(0x08057ab0))
#define fw_pad_process ((pad_process_fn)FN(0x080596b0))
#define fw_density     ((density_fn)FN(0x08059158))
#define fw_attach      ((attach_fn)FN(0x0805511c))
#define fw_attach_b    ((attach_fn)FN(0x08063df0))
#define fw_reset_obj   ((reset_fn)FN(0x08076080))
#define fw_powf        ((powf_fn)FN(0x080c7e8c))       /* the one FUN_08060848 turns the Window knob with */
#define SCATTER_TABLE  ((const int32_t *)0x080eb2a0u)   /* 97 steps, rising */
#define fw_length      ((length_fn)FN(0x080636f0))     /* a sample's length in frames (0x10000000: not known) */
#define fw_setting     ((setting_fn)FN(0x08093e9c))
#define APP_PADS       (0x24020088u + 0x1840u)         /* app pad stores: + row * 0xf0 + col * 0x30 */

#define T_SIZE    0x17c          /* Grain Size (percent knob, "grainsizeperc") */
#define T_DENSITY 0x180          /* Density ("graindensity") */
#define T_DEPTH   0x1c8          /* LFO 2 Depth; LFO 3's is 0x1c9 (lfo.c) */
#define T_WINDOW  0x5b           /* Window ("gainssrcwin") */
#define T_SCATTER 0x17e          /* Scatter ("grainscat") */
#define T_PANRND  0x17f          /* Pan Rnd ("grainpanrnd") */
#define T_SCAN    0x1ca          /* Scan ("grainscan"), ours */
#define T_PITCHRND 0x1cb         /* Pitch Rnd ("grainpitchrnd"), ours */
#define T_PMODE   0x1cd          /* Pitch Mode ("grainpitchmode"), ours; a list, not a destination */
#define T_LVLRND  0x1ce          /* Lvl Rnd ("grainlvlrnd"), ours */
#define TARGETS   10             /* in target_index's order */
#define GRAIN_LEVEL 0x3c         /* the grain's spare word: q15 gain | 0x4c56 << 16 */

#define PAD_VOICES   0x2c        /* voice pointers, count at +0x6c; a voice is playing while its first byte is set */
#define PAD_NVOICES  0x6c
#define PAD_LIST     0x4ec       /* envmod.c: slots of 12 bytes, count at +0x54c, at most 8 */
#define PAD_COUNT    0x54c
#define PAD_GRANULAR 0x589
#define PAD_SIZE     0x590
#define PAD_DENSITY  0x5a0
#define PAD_WINDOW   0x594
#define PAD_SCATTER  0x598
#define PAD_PANRND   0x59c
#define WINDOW_SPAN  1824000.0f  /* 38 s at 48 kHz: the Window knob's top, before the cube */
#define PAD_FIXED    0x5b5       /* byte: grains read at a fixed point (pad +0x5b8, per mille) instead of the playhead */
#define PAD_FIXEDPOS 0x5b8
#define GRAIN_RATE   0x24

#define SIZE_SPAN    47744       /* the Grain Size knob's whole range, in samples */
#define SIZE_TOP     48944
#define SIZE_STEP    840

struct entry {
    float amount;
    uint16_t target, source;
    uint8_t slot, pad[3];
};

void *lfo_source(const uint8_t *pad, int k);     /* lfo.c */
uint8_t *master_block(void);                     /* master.c */

struct ext {
    const uint8_t *source;       /* value at +4; 0 = slot empty */
    int16_t amount;              /* per mille, as the slot command carries it */
} __attribute__((packed));
struct gran_state {
    uint32_t magic;
    uint32_t on;                 /* bit per pad: its density is being moved */
    float knob[16];              /* the value the knob (or a preset) set */
    float wrote[16];             /* the value written here last, to tell the knob's own changes from ours */
    struct ext ext[16][TARGETS][3];  /* CC and engine-wide sources: pad, target (as target_index), slot */
    float depth[16][2];          /* LFO 2 / 3 Depth from the slot list, for lfo_tick's next look; used once */
    float scan[16], pitchrnd[16], lvlrnd[16];   /* our knobs, 0..1, read once a block */
    uint8_t pmode[16];
    uint32_t rng;
};
#define GRAN_MAGIC  0x47524e36u  /* "GRN6" */
#define GRAN_OFFSET (0x56800u + 0x2d100u)                /* master.c's block, behind comp.c's clipper: 0x1000 of its own */
_Static_assert(sizeof(struct gran_state) <= 0xf00, "master.c gives gran.c 0x1000 bytes; stretch.c has the last 0x100");

static struct gran_state *gran_state(void)
{
    uint8_t *mem = master_block();
    if (!mem)
        return 0;
    struct gran_state *s = (struct gran_state *)(mem + GRAN_OFFSET);
    if (s->magic != GRAN_MAGIC) {
        for (unsigned i = 0; i < sizeof *s / 4; i++)
            ((volatile uint32_t *)s)[i] = 0;
        s->magic = GRAN_MAGIC;
    }
    return s;
}

static unsigned pad_index(const uint8_t *pad)
{
    uint32_t id = *(const uint32_t *)(pad + 0x18);
    return ((id >> 8) & 3) * 4 + (id & 3);
}

/* 0..9 for our targets (Size, Density, LFO 2 / 3 Depth, Window, Scatter, Pan Rnd, Scan, Pitch Rnd, Lvl Rnd), else -1 */
static int target_index(unsigned target)
{
    switch (target) {
    case T_SIZE:      return 0;
    case T_DENSITY:   return 1;
    case T_DEPTH:     return 2;
    case T_DEPTH + 1: return 3;
    case T_WINDOW:    return 4;
    case T_SCATTER:   return 5;
    case T_PANRND:    return 6;
    case T_SCAN:      return 7;
    case T_PITCHRND:  return 8;
    case T_LVLRND:    return 9;
    default:          return -1;
    }
}

/* The MOD page's parameter list: stock's 28 (0x080f12bc), then ours. */
const uint16_t gran_mod_targets[40] = {
    4, 0x62, 0x5c, 0x8f, 0x90, 0x91, 0x92, 0x4e, 0xa2, 0xc8, 0x11, 0x33, 0x32, 0x38, 0x37, 0x3a,
    0x5d, 0xb, 9, 0xa, 0x3c, 0x3e, 0x40, 0x32, 0x33, 0x38, 0x37, 0x3a,
    T_SIZE, T_DENSITY, T_DEPTH, T_DEPTH + 1, T_WINDOW, T_SCATTER, T_PANRND, T_SCAN, T_PITCHRND, T_LVLRND,
    0x193, 0x195,                /* Clip Stretch's Grain and Jitter (stretch.c) */
};

/* A slot's source, as envmod.c and FUN_0805623c find it: an object whose value is the float at +4. */
static const float *source(const uint8_t *pad, const uint8_t *voice, unsigned code)
{
    const uint8_t *p;
    switch (code) {
    case 5:
    case 6:
        p = lfo_source(pad, (int)code - 5);
        break;
    case 1:    p = voice ? voice + 0x4c : 0;  break;     /* ENV: the voice's amp envelope */
    case 4:    p = voice ? voice + 0x520 : 0; break;     /* the voice's LFO */
    case 0xd:  p = voice ? voice + 0x84 : 0;  break;     /* VEL */
    case 0xe:  p = voice ? voice + 0x8c : 0;  break;     /* KEY */
    case 0x19: p = pad + 0x13c; break;                   /* PTCH */
    case 0x1a: p = pad + 0x124; break;                   /* MODW */
    case 0x1c: p = pad + 0x12c; break;                   /* MVOL */
    case 0x1d: p = pad + 0x134; break;                   /* MPAN */
    default:   p = 0;
    }
    return p ? (const float *)(p + 4) : 0;
}

/* Sum over a pad's CC / engine-wide slots on target `t` (target_index); 0 if none. */
static int ext_sum(const struct gran_state *s, unsigned q, int t, float *sum)
{
    const struct ext *x = s->ext[q][t];
    int routed = 0;
    for (int k = 0; k < 3; k++)
        if (x[k].source) {
            routed = 1;
            *sum += (float)x[k].amount * 0.001f * *(const float *)(x[k].source + 4);
        }
    return routed;
}

/* Sum of amount * value over the pad's slots on `target` (one of ours); 0 if none is routed there. `s`: gran_state(),
   looked up once by the caller (it may be 0: then only the slot list counts). */
static int mod_sum(const struct gran_state *s, const uint8_t *pad, const uint8_t *voice, unsigned target, float *sum)
{
    const struct entry *e = (const struct entry *)(pad + PAD_LIST);
    uint32_t n = *(const uint32_t *)(pad + PAD_COUNT);
    int routed = 0;
    float m = 0.0f;
    for (uint32_t i = 0; i < n && i < 8; i++) {
        if (e[i].target != target)
            continue;
        routed = 1;
        const float *v = source(pad, voice, e[i].source);
        if (v)
            m += e[i].amount * *v;
    }
    if (s && target - T_DEPTH >= 2u)                         /* Depth's CC part: gran_depth, for every pad class */
        routed |= ext_sum(s, pad_index(pad), target_index(target), &m);
    *sum = m;
    return routed;
}

/* The pad's first playing voice, or 0 */
static uint8_t *first_voice(uint8_t *pad)
{
    int32_t nv = *(const int32_t *)(pad + PAD_NVOICES);
    for (int32_t i = 0; i < nv && i < 16; i++) {
        uint8_t *v = ((uint8_t **)(pad + PAD_VOICES))[i];
        if (v && *v)
            return v;
    }
    return 0;
}

/* ---- Grain Size: every grain start ---- */

/* Which of our targets (bits by target_index) have anything on them for this pad: one pass over the slot list and
   the CC slots, so a grain with nothing routed costs only this. */
static unsigned grain_routed(const struct gran_state *s, const uint8_t *pad)
{
    const struct entry *e = (const struct entry *)(pad + PAD_LIST);
    uint32_t n = *(const uint32_t *)(pad + PAD_COUNT);
    unsigned bits = 0;
    for (uint32_t i = 0; i < n && i < 8; i++) {
        int t = target_index(e[i].target);
        if (t >= 0)
            bits |= 1u << t;
    }
    if (s) {
        const struct ext *x = &s->ext[pad_index(pad)][0][0];
        for (int k = 0; k < TARGETS * 3; k++)
            if (x[k].source)
                bits |= 1u << (k / 3);
    }
    return bits;
}

static float clamp01(float v)
{
    return v < 0.0f ? 0.0f : v > 1.0f ? 1.0f : v;
}

static float random(struct gran_state *s)                /* -1 .. 1 */
{
    s->rng = s->rng * 1664525u + 1013904223u;
    return (float)(int32_t)s->rng * (1.0f / 2147483648.0f);
}

/* Pitch Mode's sets: bit k = k semitones (0..24) is a step; the same steps downwards, but for Shimmr (up only).
   New sets go at the end: a preset stores the index. */
#define S(k) (1u << (k))
#define PMODES 20
static const char *const pmode_names[PMODES] = {
    "Free", "Semi", "Oct", "5th+Oct", "Major", "Minor", "Pent", "Shimmr",
    "6th+Oct", "m7+Oct", "M7+Oct", "9th+Oct", "4th+5th", "5th+9th", "2 Oct", "2Oct+5", "Maj7", "Min7", "Add9", "5ths",
};
static const uint32_t pmode_steps[PMODES] = {
    0, 0x1fff, S(0) | S(12), S(0) | S(7) | S(12), S(0) | S(4) | S(7) | S(12), S(0) | S(3) | S(7) | S(12),
    S(0) | S(3) | S(5) | S(7) | S(10) | S(12), S(0) | S(12),
    S(0) | S(9) | S(12), S(0) | S(10) | S(12), S(0) | S(11) | S(12), S(0) | S(12) | S(14),
    S(0) | S(5) | S(7) | S(12), S(0) | S(7) | S(14), S(0) | S(12) | S(24), S(0) | S(7) | S(12) | S(19) | S(24),
    S(0) | S(4) | S(7) | S(11) | S(12), S(0) | S(3) | S(7) | S(10) | S(12), S(0) | S(4) | S(7) | S(12) | S(14),
    S(0) | S(7) | S(14) | S(21),
};

/* how far Pitch Rnd reaches at 100 % for a set: its top step, an octave at least */
static float reach(unsigned mode)
{
    uint32_t v = pmode_steps[mode];
    int top = v ? 31 - __builtin_clz(v) : 12;
    return (float)(top < 12 ? 12 : top);
}
#define SHIMMER 7

/* The step of the mode's set nearest to `semis` (-12..12) */
static float snap(float semis, unsigned mode)
{
    float a = semis < 0.0f ? -semis : semis, best = 0.0f, gap = 99.0f;
    for (int k = 0; k <= 24; k++)
        if (pmode_steps[mode] >> k & 1) {
            float d = a - (float)k;
            d = d < 0.0f ? -d : d;
            if (d < gap) {
                gap = d;
                best = (float)k;
            }
        }
    return semis < 0.0f && mode != SHIMMER ? -best : best;
}

/* Replaces bl FUN_08057ab0 @0x08057fba, 0x08058b8a, 0x0805961e, 0x08059692. */
void gran_grain_start(uint8_t *pad, void *now, uint8_t *voice, int first, int x, uint8_t *grain)
{
    struct gran_state *s;
    unsigned routed;
    int32_t *size = (int32_t *)(pad + PAD_SIZE), knob = *size;
    int32_t *window = (int32_t *)(pad + PAD_WINDOW), win = *window;
    int32_t *scatter = (int32_t *)(pad + PAD_SCATTER), scat = *scatter;
    float *panrnd = (float *)(pad + PAD_PANRND), pan = *panrnd;
    int64_t *head = (int64_t *)(voice + 0x10), playhead = *head;
    int32_t *fixed = (int32_t *)(pad + PAD_FIXEDPOS), fixpos = *fixed;
    float m, detune = 0.0f, level = 0.0f;
    unsigned mode = 0;
    s = pad[PAD_GRANULAR] ? gran_state() : 0;
    if (s) {
        unsigned q = pad_index(pad);
        routed = grain_routed(s, pad);
        float scan = s->scan[q];
        if ((routed & 1 << 7) && mod_sum(s, pad, voice, T_SCAN, &m))
            scan += m;
        scan -= (float)(int)scan;                        /* wraps round the sample, either way */
        if (scan < 0.0f)
            scan += 1.0f;
        if (scan != 0.0f) {
            if (pad[PAD_FIXED]) {
                int32_t f = fixpos + (int32_t)(scan * 1000.0f);
                *fixed = f >= 1000 ? f - 1000 : f;
            } else {
                int32_t len = fw_length(*(void *const *)(voice + 0xc));
                if (len > 0 && len < 0x10000000) {
                    int64_t h = playhead + (int32_t)(scan * (float)len);   /* len < 2^28: fits */
                    *head = h >= len ? h - len : h;
                }
            }
        }
        detune = s->pitchrnd[q];
        if ((routed & 1 << 8) && mod_sum(s, pad, voice, T_PITCHRND, &m))
            detune = clamp01(detune + m);
        mode = s->pmode[q];
        level = s->lvlrnd[q];
        if ((routed & 1 << 9) && mod_sum(s, pad, voice, T_LVLRND, &m))
            level = clamp01(level + m);
    } else {
        routed = 0;
    }
    if (routed) {
        if ((routed & 1) && mod_sum(s, pad, voice, T_SIZE, &m) && m != 0.0f) {
            int32_t top = knob > SIZE_TOP ? knob : SIZE_TOP;  /* a synced size may be longer than the knob goes */
            int32_t s = knob + (int32_t)(m * (float)SIZE_SPAN);
            s = s > top ? top : s;
            s = s / SIZE_STEP * SIZE_STEP;
            *size = s < SIZE_STEP ? SIZE_STEP : s;
        }
        if ((routed & 1 << 4) && mod_sum(s, pad, voice, T_WINDOW, &m) && m != 0.0f) {
            float k = win > 0 ? fw_powf((float)win * (1.0f / WINDOW_SPAN), 1.0f / 3.0f) : 0.0f;
            k = clamp01(k + m);
            *window = (int32_t)(WINDOW_SPAN * k * k * k);
        }
        if ((routed & 1 << 5) && mod_sum(s, pad, voice, T_SCATTER, &m) && m != 0.0f) {
            int i = 0;
            while (i < 96 && SCATTER_TABLE[i + 1] <= scat)
                i++;                                     /* the knob's step */
            i += (int)(m * 96.0f + (m < 0.0f ? -0.5f : 0.5f));
            *scatter = SCATTER_TABLE[i < 0 ? 0 : i > 96 ? 96 : i];
        }
        if ((routed & 1 << 6) && mod_sum(s, pad, voice, T_PANRND, &m) && m != 0.0f)
            *panrnd = clamp01(pan + m);
    }
    fw_grain_start(pad, now, voice, first, x, grain);
    *size = knob;
    *window = win;
    *scatter = scat;
    *panrnd = pan;
    *head = playhead;
    *fixed = fixpos;
    if (!s)
        return;
    if (detune > 0.0f) {                                /* up to the set's reach either way at 100 % */
        float semis = random(s) * reach(mode) * detune;
        if (mode)
            semis = snap(semis, mode);
        if (semis != 0.0f) {
            /* at most 8x (stock's own cap on the clip reader), or what stock set if that is more: the renderer
               fetches n x rate + 8 frames clamped to its buffer, but its kernel reads n x rate whatever it got */
            float *rate = (float *)(grain + GRAIN_RATE), r = *rate * fw_powf(2.0f, semis * (1.0f / 12.0f));
            float cap = *rate > 8.0f ? *rate : 8.0f;
            *rate = r > cap ? cap : r;
        }
    }
    float u = 0.5f + 0.5f * random(s);                  /* 0..1 */
    *(uint32_t *)(grain + GRAIN_LEVEL) = 0x4c560000u | (uint32_t)(32767.0f * (1.0f - level * u));
}

/* ---- Scan and Pitch Rnd: the knobs, once per block ---- */

static void knobs(const uint8_t *pad)
{
    struct gran_state *s = gran_state();
    if (!s)
        return;
    unsigned q = pad_index(pad);
    const void *store = (const void *)(APP_PADS + (q >> 2) * 0xf0u + (q & 3) * 0x30u);
    s->scan[q] = (float)fw_setting(store, T_SCAN) * 0.001f;          /* missing (an older preset): 0, which is off */
    s->pitchrnd[q] = (float)fw_setting(store, T_PITCHRND) * 0.001f;
    s->lvlrnd[q] = (float)fw_setting(store, T_LVLRND) * 0.001f;
    unsigned mode = (unsigned)fw_setting(store, T_PMODE);
    s->pmode[q] = (uint8_t)(mode < PMODES ? mode : 0);
}

/* Registered with the pad parameters (lfo.c's lfo_register) and given their defaults (lfo_defaults). */
typedef void (*register_num_fn)(void *table, int param, int type, const char *label, int min, int max, const char *xml);
typedef void (*store_add_fn)(void *store, int param, int value);

typedef void (*register_list_fn)(void *table, int param, const char *label, const char *const *names, int count,
                                 const char *xml);

void gran_register(void *table)
{
    ((register_num_fn)FN(0x0808c12c))(table, T_SCAN, 8, "Scan:", 0, 1000, "grainscan");
    ((register_num_fn)FN(0x0808c12c))(table, T_PITCHRND, 8, "Pitch Rnd:", 0, 1000, "grainpitchrnd");
    ((register_list_fn)FN(0x0808c0d8))(table, T_PMODE, "Pitch Mode:", pmode_names, PMODES, "grainpitchmode");
    ((register_num_fn)FN(0x0808c12c))(table, T_LVLRND, 8, "Lvl Rnd:", 0, 1000, "grainlvlrnd");
}

void gran_defaults(void *store)
{
    ((store_add_fn)FN(0x08093ef6))(store, T_SCAN, 0);
    ((store_add_fn)FN(0x08093ef6))(store, T_PITCHRND, 0);
    ((store_add_fn)FN(0x08093ef6))(store, T_PMODE, 0);
    ((store_add_fn)FN(0x08093ef6))(store, T_LVLRND, 0);
}

/* ---- Density: once per block ---- */

static void density(uint8_t *pad, void *now)
{
    struct gran_state *s = gran_state();
    if (!s)
        return;
    unsigned q = pad_index(pad);
    uint32_t bit = 1u << q;
    float *d = (float *)(pad + PAD_DENSITY), m;
    int routed = mod_sum(s, pad, first_voice(pad), T_DENSITY, &m);
    if (!(s->on & bit)) {
        if (!routed)
            return;
        s->on |= bit;
        s->knob[q] = s->wrote[q] = *d;
    } else if (*d != s->wrote[q]) {
        s->knob[q] = *d;                                 /* the knob or a preset moved it */
    }
    float want = s->knob[q];
    if (!routed)
        s->on &= ~bit;                                   /* routing gone: put the knob's value back */
    else
        want += m;
    want = clamp01(want);
    float diff = want - *d;
    if (diff < 0.002f && diff > -0.002f && routed)
        return;
    if (diff == 0.0f)
        return;
    *d = s->wrote[q] = want;
    fw_density(pad, now);
}

/* ---- LFO 2 / 3 Depth ---- */

/* A class A pad's slots on the two Depths, for lfo_tick's next look. */
static void depth_slots(uint8_t *pad)
{
    struct gran_state *s = gran_state();
    const struct entry *e = (const struct entry *)(pad + PAD_LIST);
    uint32_t n = *(const uint32_t *)(pad + PAD_COUNT), i;
    if (!s)
        return;
    for (i = 0; i < n && i < 8; i++)
        if ((unsigned)(e[i].target - T_DEPTH) < 2u)
            break;
    if (i == n || i == 8)
        return;                                          /* nothing on either: the cheap way out */
    uint8_t *voice = first_voice(pad);
    unsigned q = pad_index(pad);
    for (int k = 0; k < 2; k++)
        mod_sum(s, pad, voice, T_DEPTH + (unsigned)k, &s->depth[q][k]);
}

/* lfo.c, once per engine block for each LFO in use: what the slots add to its Depth knob (0..1 = the knob's range). */
float gran_depth(unsigned q, int k)
{
    struct gran_state *s = gran_state();
    if (!s || q > 15u)
        return 0.0f;
    float m = s->depth[q][k];
    s->depth[q][k] = 0.0f;
    ext_sum(s, q, 2 + k, &m);
    return m;
}

/* Replaces bl FUN_080596b0 @0x0805bb5a: a class A pad's block. */
int gran_pad_process(uint8_t *pad, void **ctx)
{
    if (pad[PAD_GRANULAR]) {
        knobs(pad);
        density(pad, ctx[0]);
    }
    depth_slots(pad);
    return fw_pad_process(pad, ctx);
}

/* ---- the other ways in ---- */

/* envmod.c's env_mod_setup: keep a PTCH / MODW / MVOL / MPAN slot on our targets in the pad's list. */
int gran_listed(unsigned target, unsigned source)
{
    return target_index(target) >= 0 && (source == 0x19 || source == 0x1a || source == 0x1c || source == 0x1d);
}

static void keep(const uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    struct gran_state *s;
    int t = target_index(target);
    if (t >= 0 && slot < 3 && (s = gran_state()) != 0) {
        struct ext *x = &s->ext[pad_index(pad)][t][slot];
        x->source = source;
        x->amount = (int16_t)(amount * 1000.0f + (amount < 0.0f ? -0.5f : 0.5f));
    }
}

/* Replaces the class A pad's vtable +0x40 (FUN_0805511c @0x080d0708): CC and engine-wide sources on a parameter. */
void gran_attach(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    keep(pad, source, target, slot, amount);
    fw_attach(pad, source, target, slot, amount);
}

void stretch_attach(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount);
void stretch_forget(const uint8_t *pad);         /* stretch.c: Clip Stretch's Grain / Jitter */

/* Replaces the class B pad's vtable +0x40 (FUN_08063df0 @0x080d08d0). */
void gran_attach_b(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    keep(pad, source, target, slot, amount);
    stretch_attach(pad, source, target, slot, amount);
    fw_attach_b(pad, source, target, slot, amount);
}

/* `pad` if it is a pad of the class whose vtable is `vt`: empty its CC slots. */
static void forget(const uint8_t *pad, uint32_t vt)
{
    struct gran_state *s = gran_state();
    if (s && *(const uint32_t *)pad == vt) {
        struct ext *x = &s->ext[pad_index(pad)][0][0];
        for (int k = 0; k < TARGETS * 3; k++)
            x[k].source = 0;
    }
}

/* Replaces bl FUN_08076080 @0x08059e28, in the class A pad's reset (cmd 0x40), which hands it pad +0x2f4. */
void gran_reset(uint8_t *obj)
{
    forget(obj - 0x2f4, VT_A);
    fw_reset_obj(obj);
}

/* Replaces bl FUN_08076080 @0x08068556, in the class B pad's reset: once per playing layer, with layer +0x1d4, the
   first layer being pad +0x26c. Only the first call's object sits 0x440 into a pad (checked by its vtable). */
void gran_reset_b(uint8_t *obj)
{
    forget(obj - 0x440, VT_B);
    if (*(const uint32_t *)(obj - 0x440) == VT_B)
        stretch_forget(obj - 0x440);
    fw_reset_obj(obj);
}

/*
 * Granular pads: Grain Size and Density as modulation destinations, and LFO 2 / 3 on the granular pad pages.
 * Also LFO 2 / 3 Depth (lfo.c's knobs 0x1c8 / 0x1c9) as modulation destinations, on every pad.
 * Original 1010music Blackbox, firmware 3.1.9.
 *
 * A granular pad is a class A pad (the Sample pad's engine) with byte pad +0x589 set (mode 0x8b == 3). Its voices
 * play up to eight grains each (voice +0x13c: 0x40 bytes a grain); FUN_08057ab0 starts one, reading the pad's settings
 * as it is at that moment:
 *   pad +0x590  grain size in samples (knob 0x17c: 1200 + knob * 47744, floored to a multiple of 840; 0x57 = synced)
 *   pad +0x5a0  density, 0..1 (knob 0x180); FUN_08059158 turns it into a grain count (+0x58c) and a gap (+0x5a4)
 * Stock modulates none of the grain knobs but Speed (0x5d): the voice attach (FUN_0805623c) has no parameter object
 * for them, and the pad screen only offers the MOD page for the 28 parameters in its list at 0x080f12bc.
 *
 * The pad's slot list (pad +0x4ec, envmod.c) keeps every VEL / KEY / LFO / LFO2 / LFO3 / ENV slot whatever its
 * target, so a slot on Grain Size or Density is already there; it just has nothing to act on. Here:
 *   Grain Size  gran_grain_start wraps every call of FUN_08057ab0 (respawn, voice start, density change): the size is
 *               moved by the sum of the slots, for that voice, while the grain is set up, then put back. Each grain
 *               keeps the size it started with.
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
#define VT_A 0x080d06c8u         /* class A pad's vtable */
#define VT_B 0x080d0890u         /* class B pad's vtable */
#define fw_grain_start ((grain_start_fn)FN(0x08057ab0))
#define fw_pad_process ((pad_process_fn)FN(0x080596b0))
#define fw_density     ((density_fn)FN(0x08059158))
#define fw_attach      ((attach_fn)FN(0x0805511c))
#define fw_attach_b    ((attach_fn)FN(0x08063df0))
#define fw_reset_obj   ((reset_fn)FN(0x08076080))

#define T_SIZE    0x17c          /* Grain Size (percent knob, "grainsizeperc") */
#define T_DENSITY 0x180          /* Density ("graindensity") */
#define T_DEPTH   0x1c8          /* LFO 2 Depth; LFO 3's is 0x1c9 (lfo.c) */
#define TARGETS   4              /* Grain Size, Density, LFO 2 Depth, LFO 3 Depth */

#define PAD_VOICES   0x2c        /* voice pointers, count at +0x6c; a voice is playing while its first byte is set */
#define PAD_NVOICES  0x6c
#define PAD_LIST     0x4ec       /* envmod.c: slots of 12 bytes, count at +0x54c, at most 8 */
#define PAD_COUNT    0x54c
#define PAD_GRANULAR 0x589
#define PAD_SIZE     0x590
#define PAD_DENSITY  0x5a0

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
    float amount;
};
struct gran_state {
    uint32_t magic;
    uint32_t on;                 /* bit per pad: its density is being moved */
    float knob[16];              /* the value the knob (or a preset) set */
    float wrote[16];             /* the value written here last, to tell the knob's own changes from ours */
    struct ext ext[16][TARGETS][3];  /* CC and engine-wide sources: pad, target (as target_index), slot */
    float depth[16][2];          /* LFO 2 / 3 Depth from the slot list, for lfo_tick's next look; used once */
};
#define GRAN_MAGIC  0x47524e33u  /* "GRN3" */
#define GRAN_OFFSET (0x56800u + 0x800u)                  /* in lfo.c's 0x1000 bytes, behind its state */
_Static_assert(sizeof(struct gran_state) <= 0x800, "lfo.c's block has 0x800 bytes for gran.c");

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

/* 0..3 for our targets, -1 for anything else */
static int target_index(unsigned target)
{
    return target == T_SIZE ? 0 : target == T_DENSITY ? 1 : target - T_DEPTH < 2u ? 2 + (int)(target - T_DEPTH) : -1;
}

/* The MOD page's parameter list: stock's 28 (0x080f12bc), then Grain Size, Density, LFO 2 / 3 Depth. */
const uint16_t gran_mod_targets[32] = {
    4, 0x62, 0x5c, 0x8f, 0x90, 0x91, 0x92, 0x4e, 0xa2, 0xc8, 0x11, 0x33, 0x32, 0x38, 0x37, 0x3a,
    0x5d, 0xb, 9, 0xa, 0x3c, 0x3e, 0x40, 0x32, 0x33, 0x38, 0x37, 0x3a,
    T_SIZE, T_DENSITY, T_DEPTH, T_DEPTH + 1,
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
            *sum += x[k].amount * *(const float *)(x[k].source + 4);
        }
    return routed;
}

/* Sum of amount * value over the pad's slots on `target` (one of ours); 0 if none is routed there. */
static int mod_sum(const uint8_t *pad, const uint8_t *voice, unsigned target, float *sum)
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
    struct gran_state *s = gran_state();
    if (s && target != T_DEPTH && target != T_DEPTH + 1)     /* Depth's CC part: gran_depth, for every pad class */
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

/* Replaces bl FUN_08057ab0 @0x08057fba, 0x08058b8a, 0x0805961e, 0x08059692. */
void gran_grain_start(uint8_t *pad, void *now, uint8_t *voice, int first, int x, uint8_t *grain)
{
    int32_t *size = (int32_t *)(pad + PAD_SIZE), knob = *size;
    float m;
    if (pad[PAD_GRANULAR] && mod_sum(pad, voice, T_SIZE, &m) && m != 0.0f) {
        int32_t top = knob > SIZE_TOP ? knob : SIZE_TOP;  /* a synced size may be longer than the knob goes */
        int32_t s = knob + (int32_t)(m * (float)SIZE_SPAN);
        s = s > top ? top : s;
        s = s / SIZE_STEP * SIZE_STEP;
        *size = s < SIZE_STEP ? SIZE_STEP : s;
    }
    fw_grain_start(pad, now, voice, first, x, grain);
    *size = knob;
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
    int routed = mod_sum(pad, first_voice(pad), T_DENSITY, &m);
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
    want = want < 0.0f ? 0.0f : want > 1.0f ? 1.0f : want;
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
        mod_sum(pad, voice, T_DEPTH + (unsigned)k, &s->depth[q][k]);
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
    if (pad[PAD_GRANULAR])
        density(pad, ctx[0]);
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
        x->amount = amount;
    }
}

/* Replaces the class A pad's vtable +0x40 (FUN_0805511c @0x080d0708): CC and engine-wide sources on a parameter. */
void gran_attach(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    keep(pad, source, target, slot, amount);
    fw_attach(pad, source, target, slot, amount);
}

/* Replaces the class B pad's vtable +0x40 (FUN_08063df0 @0x080d08d0). */
void gran_attach_b(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    keep(pad, source, target, slot, amount);
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
    fw_reset_obj(obj);
}

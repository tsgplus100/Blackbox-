/*
 * Granular pads: Grain Size and Density as modulation destinations, and LFO 2 / 3 on the granular pad pages.
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
 * Amount: 100 % is the whole knob range. MIDI and duck sources (PTCH, MODW, MVOL, MPAN, CC, EXP1..LINR) are not in
 * the slot list and do nothing on these two.
 */
#include <stdint.h>

#pragma GCC optimize("Os", "no-tree-loop-distribute-patterns")

#define FN(addr) ((addr) | 1u)
typedef void (*grain_start_fn)(uint8_t *pad, void *now, uint8_t *voice, int first, int x, uint8_t *grain);
typedef int (*pad_process_fn)(uint8_t *pad, void **ctx);
typedef void (*density_fn)(uint8_t *pad, void *now);
#define fw_grain_start ((grain_start_fn)FN(0x08057ab0))
#define fw_pad_process ((pad_process_fn)FN(0x080596b0))
#define fw_density     ((density_fn)FN(0x08059158))

#define T_SIZE    0x17c          /* Grain Size (percent knob, "grainsizeperc") */
#define T_DENSITY 0x180          /* Density ("graindensity") */

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

/* The MOD page's parameter list: stock's 28 (0x080f12bc), then Grain Size and Density. */
const uint16_t gran_mod_targets[30] = {
    4, 0x62, 0x5c, 0x8f, 0x90, 0x91, 0x92, 0x4e, 0xa2, 0xc8, 0x11, 0x33, 0x32, 0x38, 0x37, 0x3a,
    0x5d, 0xb, 9, 0xa, 0x3c, 0x3e, 0x40, 0x32, 0x33, 0x38, 0x37, 0x3a,
    T_SIZE, T_DENSITY,
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
    default:   p = 0;
    }
    return p ? (const float *)(p + 4) : 0;
}

/* Sum of amount * value over the pad's slots on `target`; 0 if none is routed there. */
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
    *sum = m;
    return routed;
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

struct gran_state {
    uint32_t magic;
    uint32_t on;                 /* bit per pad: its density is being moved */
    float knob[16];              /* the value the knob (or a preset) set */
    float wrote[16];             /* the value written here last, to tell the knob's own changes from ours */
};
#define GRAN_MAGIC  0x4752414eu  /* "GRAN" */
#define GRAN_OFFSET (0x56800u + 0x800u)                  /* in lfo.c's 0x1000 bytes, behind its state */

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

static void density(uint8_t *pad, void *now)
{
    struct gran_state *s = gran_state();
    if (!s)
        return;
    uint32_t id = *(const uint32_t *)(pad + 0x18), q = ((id >> 8) & 3) * 4 + (id & 3), bit = 1u << q;
    uint8_t *voice = 0;
    int32_t nv = *(const int32_t *)(pad + PAD_NVOICES);
    for (int32_t i = 0; i < nv && i < 16; i++) {
        uint8_t *v = ((uint8_t **)(pad + PAD_VOICES))[i];
        if (v && *v) {
            voice = v;
            break;
        }
    }
    float *d = (float *)(pad + PAD_DENSITY), m;
    int routed = mod_sum(pad, voice, T_DENSITY, &m);
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

/* Replaces bl FUN_080596b0 @0x0805bb5a: a class A pad's block. */
int gran_pad_process(uint8_t *pad, void **ctx)
{
    if (pad[PAD_GRANULAR])
        density(pad, ctx[0]);
    return fw_pad_process(pad, ctx);
}

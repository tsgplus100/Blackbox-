/*
 * Clip pads: Speed (JBGRAN 10), the clip's length on the grid times 1 / Speed. Original 1010music Blackbox, 3.1.9.
 *
 * A Clip pad (class B) fits its sample to the tempo by varispeed: FUN_08064a94 works the clip's length out in ticks
 * (960 a beat: Beat Count x 960, or from the sample when Beat Count is Auto), turns it into frames at the tempo with
 * FUN_08070420 (the calls @0x08064b9e and @0x08064e54) and derives the read rate and the Sync slices from that. Each
 * block the layer reads at pitch x that rate (FUN_08066454), and a drift of more than 4 frames hands over to the
 * other layer with a crossfade.
 * Speed scales the ticks those two calls are handed, so everything stock derives from them follows: x1/2 makes the
 * clip twice as long on the grid, still in sync. Stock plays that by varispeed (an octave down, like tape); the stretch
 * engine (to come) keeps the pitch.
 *   clip_duration  wraps every call of FUN_08064a94 and says which pad it is for (its Speed, from the app's store)
 *   clip_ticks     wraps the two tick conversions: ticks x den / num
 *   clip_process   wraps the class B pad's block (bl FUN_08067fa4 @0x08068c6a): a changed Speed reruns FUN_08064a94,
 *                  the way stock does when Sync changes
 */
#include <stdint.h>

#pragma GCC optimize("Os")

#define FN(addr) ((addr) | 1u)
typedef void (*duration_fn)(uint8_t *pad, void *ctx);
typedef void (*ticks_fn)(uint32_t *out, int64_t *ticks, float bpm, float fs);
typedef int (*process_fn)(uint8_t *pad, void **ctx);
typedef void (*register_list_fn)(void *table, int param, const char *label, const char *const *names, int count,
                                 const char *xml);
typedef void (*store_add_fn)(void *store, int param, int value);
#define fw_duration ((duration_fn)FN(0x08064a94))
#define fw_ticks    ((ticks_fn)FN(0x08070420))
#define fw_process  ((process_fn)FN(0x08067fa4))
#define APP_PADS    (0x24020088u + 0x1840u)         /* app pad stores: + row * 0xf0 + col * 0x30 */

#define P_SPEED  0x1cf
#define SPEEDS   10
#define SPEED_1X 5
static const char *const speed_names[SPEEDS] = {"x1/4", "x1/3", "x1/2", "x2/3", "x3/4", "x1", "x3/2", "x2", "x3", "x4"};
static const uint8_t speed_num[SPEEDS] = {1, 1, 1, 2, 3, 1, 3, 2, 3, 4};
static const uint8_t speed_den[SPEEDS] = {4, 3, 2, 3, 4, 1, 2, 1, 1, 1};

uint8_t *master_block(void);     /* master.c */
#define CLIP_OFFSET (0x56800u + 0x2d100u + 0xf00u)   /* the last 0x100 of gran.c's 0x1000 (gran.c asserts it stays clear) */
struct clip_state {
    uint32_t magic;
    uint8_t seen[16];            /* per pad: the Speed its length was last worked out with, + 1 (0: never) */
    uint8_t now;                 /* the Speed FUN_08064a94 is running with right now, + 1 (0: none) */
};
#define CLIP_MAGIC 0x434c5331u   /* "CLS1" */

static struct clip_state *clip_state(void)
{
    uint8_t *mem = master_block();
    if (!mem)
        return 0;
    struct clip_state *s = (struct clip_state *)(mem + CLIP_OFFSET);
    if (s->magic != CLIP_MAGIC) {
        for (unsigned i = 0; i < sizeof *s / 4; i++)
            ((volatile uint32_t *)s)[i] = 0;
        s->magic = CLIP_MAGIC;
    }
    return s;
}

static unsigned pad_index(const uint8_t *pad)
{
    uint32_t id = *(const uint32_t *)(pad + 0x18);
    return ((id >> 8) & 3) * 4 + (id & 3);
}

/* The pad's Speed; x1 when its store has none (a preset from before Speed: stock's lookup would answer 0, x1/4). */
static unsigned speed_of(const uint8_t *pad)
{
    unsigned q = pad_index(pad);
    const uint8_t *st = (const uint8_t *)(APP_PADS + (q >> 2) * 0xf0u + (q & 3) * 0x30u);
    const uint8_t *e = *(const uint8_t *const *)(st + 4);
    for (unsigned i = 0, n = *(const uint16_t *)(st + 10); i < n; i++, e += 8)
        if (*(const uint16_t *)e == P_SPEED) {
            unsigned v = *(const uint32_t *)(e + 4);
            return v < SPEEDS ? v : SPEED_1X;
        }
    return SPEED_1X;
}

/* Replaces every bl / b.w FUN_08064a94 (9 sites). */
void clip_duration(uint8_t *pad, void *ctx)
{
    struct clip_state *s = clip_state();
    unsigned v = speed_of(pad);
    if (s) {
        s->now = (uint8_t)(v + 1);
        s->seen[pad_index(pad)] = (uint8_t)(v + 1);
    }
    fw_duration(pad, ctx);
    if (s)
        s->now = 0;
}

/* Replaces bl FUN_08070420 @0x08064b9e and @0x08064e54, inside FUN_08064a94: the clip's ticks, before they become frames. */
void clip_ticks(uint32_t *out, int64_t *ticks, float bpm, float fs)
{
    struct clip_state *s = clip_state();
    if (s && s->now && s->now != SPEED_1X + 1 && *ticks > 0 && *ticks < (1 << 28)) {
        unsigned v = s->now - 1u;
        *ticks = (int64_t)((uint32_t)*ticks * speed_den[v] / speed_num[v]);
    }
    fw_ticks(out, ticks, bpm, fs);
}

/* Replaces bl FUN_08067fa4 @0x08068c6a: a class B pad's block. */
int clip_process(uint8_t *pad, void **ctx)
{
    struct clip_state *s = clip_state();
    if (s && *(const void *const *)(pad + 0x24)) {        /* a sample loaded (FUN_08064a94 returns at once without) */
        unsigned v = speed_of(pad);
        if (s->seen[pad_index(pad)] != v + 1)
            clip_duration(pad, ctx[0]);
    }
    return fw_process(pad, ctx);
}

void stretch_register(void *table)
{
    ((register_list_fn)FN(0x0808c0d8))(table, P_SPEED, "Speed:", speed_names, SPEEDS, "clipspeed");
}

void stretch_defaults(void *store)
{
    ((store_add_fn)FN(0x08093ef6))(store, P_SPEED, SPEED_1X);
}

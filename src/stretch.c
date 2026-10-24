/*
 * Clip pads: Speed (JBGRAN 10), the clip's length on the grid times 1 / Speed. Original 1010music Blackbox, 3.1.9.
 *
 * A Clip pad (class B) fits its sample to the tempo by varispeed: FUN_08064a94 works the clip's length out in ticks
 * (960 a beat: Beat Count x 960, or from the sample when Beat Count is Auto), turns it into frames at the tempo with
 * FUN_08070420 (the calls @0x08064b9e and @0x08064e54) and derives the read rate and the Sync slices from that. Each
 * block the layer reads at pitch x that rate (FUN_08066454), and a drift of more than 4 frames hands over to the
 * other layer with a crossfade.
 * Speed scales the ticks those two calls are handed, so everything stock derives from them follows: x1/2 makes the
 * clip twice as long on the grid, still in sync. Stock plays that by varispeed (an octave down, like tape).
 *
 * Stretch (JBGRAN 11): Mode "Stretch" keeps the pitch instead. The layer's read rate is 2^(pitch / 12 + mod) x layer
 * +0x18 (the tempo factor, FUN_08066454); the clip reader (FUN_080662e4, reached through filter.c's clip_read) goes
 * on reporting the frames that rate uses, so the playhead, Sync, loop points and the drift check are stock's. What
 * comes out is grains instead: each a Hann window Grain long, half overlapping the last, reading from where the
 * playhead was when it started at the pitch rate alone (rate / tempo factor). Each grain's start is moved, within
 * 10 ms, to where the source best continues the grain before it (WSOLA: the cross-correlation's peak, coarse then
 * fine), so the waveform runs on in phase instead of jumping at every grain (plain overlap-add detunes and buzzes). A
 * fresh start (a note, a resync, a handover) begins at full level, mid-window, so attacks stay sharp. Jitter moves each grain's start by up to half a
 * grain either way; Freeze holds the point grains start from while the playhead (and the grid) runs on.
 * Grain and Jitter are modulation destinations (gran.c's MOD-page list): LFO 2 / 3 and ENV through the class B slot
 * setup (envmod.c's env_mod_setup_b hands them over: stretch_slot), CC and EXP1..LINR through the pad's vtable +0x40
 * (gran.c's gran_attach_b: stretch_attach). Amount 100 % = the whole knob. The pad's reset forgets them (as gran.c).
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
typedef int (*src_int_fn)(void *src);
typedef void (*fetch_fn)(void *src, float *dst, int n, int32_t pos, int zero);
typedef void (*fetch2_fn)(void *src, float *left, float *right, int n, int32_t pos);
typedef int (*buf_int_fn)(void *buf);
typedef float *(*buf_mono_fn)(void *buf);
typedef int (*buf_chans_fn)(void *buf, float **left, float **right);
typedef void (*register_num_fn)(void *table, int param, int type, const char *label, int min, int max, const char *xml);
#define fw_src_len    ((src_int_fn)FN(0x080636f0))
#define fw_src_stereo ((src_int_fn)FN(0x08063790))
#define fw_fetch      ((fetch_fn)FN(0x08063634))
#define fw_fetch2     ((fetch2_fn)FN(0x08063608))
#define fw_buf_frames ((buf_int_fn)FN(0x0804d8e8))
#define fw_buf_mono   ((buf_mono_fn)FN(0x0804d934))
#define fw_buf_pair   ((buf_chans_fn)FN(0x0804da0c))
#define APP_PADS    (0x24020088u + 0x1840u)         /* app pad stores: + row * 0xf0 + col * 0x30 */

#define P_SPEED  0x1cf
#define SPEEDS   10
#define SPEED_1X 5
static const char *const speed_names[SPEEDS] = {"x1/4", "x1/3", "x1/2", "x2/3", "x3/4", "x1", "x3/2", "x2", "x3", "x4"};
static const uint8_t speed_num[SPEEDS] = {1, 1, 1, 2, 3, 1, 3, 2, 3, 4};
static const uint8_t speed_den[SPEEDS] = {4, 3, 2, 3, 4, 1, 2, 1, 1, 1};

/* Stretch's knobs: ids no table entry of stock's (or the mod's) has */
#define P_MODE   0x192           /* Repitch (stock), Stretch */
#define P_GRAIN  0x193           /* 0..100 %: 10 .. 200 ms, on a square (40 % = 40 ms) */
#define P_JITTER 0x195           /* 0..100 %: a grain's start moves up to half a grain either way */
#define P_FREEZE 0x196           /* Off, On */
static const char *const mode_names[2] = {"Repitch", "Stretch"};
static const char *const freeze_names[2] = {"Off", "On"};

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

/* A setting from the pad's store; `missing` when it has none (a preset from before it: stock's lookup would answer 0) */
static unsigned setting_or(const uint8_t *pad, unsigned param, unsigned missing)
{
    unsigned q = pad_index(pad);
    const uint8_t *st = (const uint8_t *)(APP_PADS + (q >> 2) * 0xf0u + (q & 3) * 0x30u);
    const uint8_t *e = *(const uint8_t *const *)(st + 4);
    for (unsigned i = 0, n = *(const uint16_t *)(st + 10); i < n; i++, e += 8)
        if (*(const uint16_t *)e == param)
            return *(const uint32_t *)(e + 4);
    return missing;
}

/* The pad's Speed; x1 when its store has none (stock's lookup would answer 0, x1/4). */
static unsigned speed_of(const uint8_t *pad)
{
    unsigned v = setting_or(pad, P_SPEED, SPEED_1X);
    return v < SPEEDS ? v : SPEED_1X;
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

/* ---- the stretch engine ---- */

#define STRETCH_OFFSET (0x56800u + 0x2e100u)   /* master.c's last 0x4000 */
#define STRETCH_MAGIC  0x53545232u             /* "STR2" */
#define GRAINS 4
#define SEEK   480                             /* WSOLA: how far a grain's start may move, frames */
#define MATCH  256                             /* ...and how much of the source it compares */
#define LAYER_A 0x260                          /* a class B pad's two layers (the second 0x410 on) */
#define LAYER_B 0x670
struct grain {
    int32_t ip;                  /* where it reads: source frame ip + fp */
    float fp;
    float x, dx;                 /* through its window, 0..1; dx 0: free */
};
struct slayer {
    int32_t next;                /* the position stock will hand over next if this layer plays on */
    int32_t fz_ip;               /* Freeze: where grains start */
    float fz_fp;
    int32_t until;               /* frames to the next grain */
    uint8_t live, frozen, last, pad0;              /* last: the grain started most recently */
    struct grain g[GRAINS];
};
struct smod {
    const uint8_t *ext;          /* CC / EXP: the source object (value at +4); 0: none */
    int16_t ext_amount, amount;  /* per mille */
    uint8_t code, pad0[3];       /* slot setup: 1 ENV, 5 LFO2, 6 LFO3; 0: none */
};
struct stretch_state {
    uint32_t magic;
    uint32_t rng;
    struct slayer layer[32];     /* pad * 2 + layer */
    struct smod mod[16][2][3];   /* pad, Grain / Jitter, slot */
    float want[MATCH];           /* WSOLA: how the last grain goes on */
    float seek[2 * SEEK + MATCH];                  /* ...and the source around where the next one would start */
    float right[2 * SEEK + MATCH];                 /* a stereo source's right channel: fetched, not compared */
};
_Static_assert(sizeof(struct stretch_state) <= 0x4000, "stretch.c's state outgrew master.c's 0x4000");

static struct stretch_state *stretch_state(void)
{
    uint8_t *mem = master_block();
    if (!mem)
        return 0;
    struct stretch_state *s = (struct stretch_state *)(mem + STRETCH_OFFSET);
    if (s->magic != STRETCH_MAGIC) {
        for (unsigned i = 0; i < sizeof *s / 4; i++)
            ((volatile uint32_t *)s)[i] = 0;
        s->magic = STRETCH_MAGIC;
        s->rng = 0x5eed1234u;
    }
    return s;
}

void *lfo_source(const uint8_t *pad, int k);     /* lfo.c */

/* Grain 0, Jitter 1, else -1 */
static int mod_target(unsigned target)
{
    return target == P_GRAIN ? 0 : target == P_JITTER ? 1 : -1;
}

/* envmod.c's env_mod_setup_b, for a slot on Grain or Jitter (whatever its source; one it cannot read empties it) */
void stretch_slot(uint8_t *pad, unsigned target, unsigned code, unsigned slot, float amount)
{
    struct stretch_state *s = stretch_state();
    int t = mod_target(target);
    if (!s || t < 0 || slot > 2u)
        return;
    struct smod *m = &s->mod[pad_index(pad)][t][slot];
    m->code = (uint8_t)(code == 1 || code == 5 || code == 6 ? code : 0);
    if (m->code)
        m->ext = 0;              /* the slot was CC / EXP until now */
    m->amount = (int16_t)(amount * 1000.0f + (amount < 0.0f ? -0.5f : 0.5f));
}

/* gran.c's gran_attach_b: CC and engine-wide sources */
void stretch_attach(uint8_t *pad, const uint8_t *source, unsigned target, unsigned slot, float amount)
{
    struct stretch_state *s = stretch_state();
    int t = mod_target(target);
    if (!s || t < 0 || slot > 2u)
        return;
    struct smod *m = &s->mod[pad_index(pad)][t][slot];
    m->ext = source;
    m->code = 0;
    m->ext_amount = (int16_t)(amount * 1000.0f + (amount < 0.0f ? -0.5f : 0.5f));
}

/* gran.c's gran_reset_b: the pad's reset (a preset load) */
void stretch_forget(const uint8_t *pad)
{
    struct stretch_state *s = stretch_state();
    if (!s)
        return;
    struct smod *m = &s->mod[pad_index(pad)][0][0];
    for (int k = 0; k < 6; k++)
        m[k].ext = 0, m[k].code = 0;
}

/* the knob (0..1) moved by its slots, for this layer, clamped */
static float modulated(struct stretch_state *s, uint8_t *pad, int layer_b, int t, float v)
{
    const struct smod *m = s->mod[pad_index(pad)][t];
    for (int k = 0; k < 3; k++) {
        const uint8_t *src = m[k].ext;
        int amount = m[k].ext_amount;
        if (m[k].code) {
            amount = m[k].amount;
            src = m[k].code == 1 ? pad + 0x260 + 0x258 + 0x24 + (layer_b ? 0x410 : 0)   /* the layer's envelope */
                                 : (const uint8_t *)lfo_source(pad, m[k].code - 5);
        }
        if (src)
            v += (float)amount * 0.001f * *(const float *)(src + 4);
    }
    return v < 0.0f ? 0.0f : v > 1.0f ? 1.0f : v;
}

/* -1 .. 1 */
static float rnd(struct stretch_state *s)
{
    s->rng = s->rng * 1664525u + 1013904223u;
    return (float)(int32_t)s->rng * (1.0f / 2147483648.0f);
}

/* sin^2(pi x), 0 <= x <= 1: Bhaskara's sine, squared (two of them half a window apart sum to 1 within 0.3 %) */
static float hann(float x)
{
    float y = x * (1.0f - x), v = 16.0f * y / (5.0f - 4.0f * y);
    return v * v;
}

/* four-point Hermite between s[1] and s[2] */
static float hermite(const float *s, float t)
{
    float c1 = 0.5f * (s[2] - s[0]);
    float c2 = s[0] - 2.5f * s[1] + 2.0f * s[2] - 0.5f * s[3];
    float c3 = 0.5f * (s[3] - s[0]) + 1.5f * (s[1] - s[2]);
    return ((c3 * t + c2) * t + c1) * t + s[1];
}

/* `count` frames of the source from `start`, silence outside it */
static void fetch(void *src, int stereo, float *l, float *r, int32_t start, int count, int32_t len)
{
    int lead = start < 0 ? (-start < count ? -start : count) : 0;
    int32_t over = start + count - len;
    int tail = over > 0 ? (over < count - lead ? (int)over : count - lead) : 0, mid = count - lead - tail;
    for (int i = 0; i < lead; i++)
        l[i] = stereo ? (r[i] = 0.0f) : 0.0f;
    for (int i = lead + mid; i < count; i++)
        l[i] = stereo ? (r[i] = 0.0f) : 0.0f;
    if (mid > 0) {
        if (stereo)
            fw_fetch2(src, l + lead, r + lead, mid, start + lead);
        else
            fw_fetch(src, l + lead, mid, start + lead, 0);
    }
}

/* add `len` frames of grain g, from its window point onwards, into ol / orr; buffers sl / sr hold `cap` frames */
static void render(struct grain *g, float pitch, void *src, int stereo, int32_t srclen, float *sl, float *sr, int cap,
                   float *ol, float *orr, int len)
{
    while (len > 0 && g->dx > 0.0f) {
        int seg = (int)((float)(cap - 5) / pitch) + 1;
        if (seg > len)
            seg = len;
        int left = (int)((1.0f - g->x) / g->dx) + 1;          /* frames to the window's end */
        if (seg > left)
            seg = left;
        int count = (int)(g->fp + pitch * (float)(seg - 1)) + 4;
        if (count > cap)
            count = cap;
        fetch(src, stereo, sl, sr, g->ip - 1, count, srclen);
        float p = g->fp, x = g->x, lim = (float)(count - 3);
        for (int i = 0; i < seg; i++) {
            if (p >= lim)
                p = lim - 0.001f;
            int j = (int)p;
            float w = hann(x > 1.0f ? 1.0f : x), t = p - (float)j;
            ol[i] += w * hermite(sl + j, t);
            if (stereo)
                orr[i] += w * hermite(sr + j, t);
            p += pitch;
            x += g->dx;
        }
        int adv = (int)p;
        g->ip += adv;
        g->fp = p - (float)adv;
        g->x = x;
        if (x >= 1.0f)
            g->dx = 0.0f;
        ol += seg;
        if (stereo)
            orr += seg;
        len -= seg;
    }
}

/* sum of a[k] b[k], every `step`th k */
static float dot(const float *a, const float *b, int n, int step)
{
    float acc = 0.0f;
    for (int k = 0; k < n; k += step)
        acc += a[k] * b[k];
    return acc;
}

/* WSOLA: the move within +-SEEK that makes the source from ip line up best with how the last grain goes on */
static int32_t align(struct stretch_state *s, struct slayer *ly, void *src, int stereo, int32_t srclen, int32_t ip)
{
    const struct grain *p = &ly->g[ly->last];
    if (p->dx <= 0.0f)
        return 0;
    fetch(src, stereo, s->want, s->right, p->ip, MATCH, srclen);   /* the left channel is enough to line up on */
    fetch(src, stereo, s->seek, s->right, ip - SEEK, 2 * SEEK + MATCH, srclen);
    float e = 0.0f;                                /* the candidate window's energy, every 8th frame, slid along */
    for (int k = 0; k < MATCH; k += 8)
        e += s->seek[k] * s->seek[k];
    int best = SEEK;
    float bs = -1e30f;
    for (int d = 0; d <= 2 * SEEK; d += 8) {       /* coarse: every 8th start, every 8th frame */
        float c = dot(s->want, s->seek + d, MATCH, 8), score = c * c / (e + 1e-9f);
        if (c > 0.0f && score > bs) {
            bs = score;
            best = d;
        }
        if (d + 8 <= 2 * SEEK) {
            float o = s->seek[d], n = s->seek[d + MATCH];
            e += n * n - o * o;
            e = e < 0.0f ? 0.0f : e;
        }
    }
    int lo = best - 7 < 0 ? 0 : best - 7, hi = best + 7 > 2 * SEEK ? 2 * SEEK : best + 7, fine = best;
    float fb = -1e30f;
    for (int d = lo; d <= hi; d++) {               /* fine: every start near it, every other frame */
        float c = dot(s->want, s->seek + d, MATCH, 2);
        if (c > fb) {
            fb = c;
            fine = d;
        }
    }
    return fine - SEEK;
}

static void spawn(struct stretch_state *s, struct slayer *ly, int32_t ip, float fp, float glen, float jitter,
                  float pitch, float x, void *src, int stereo, int32_t srclen)
{
    float off = fp + rnd(s) * jitter * 0.5f * glen * pitch;
    int32_t io = (int32_t)off - (off < 0.0f);
    ip += io;
    if (x == 0.0f)
        ip += align(s, ly, src, stereo, srclen, ip);
    int k = 0;
    while (k < GRAINS - 1 && ly->g[k].dx > 0.0f)
        k++;
    struct grain *g = &ly->g[k];
    g->ip = ip;
    g->fp = off - (float)io;
    g->x = x;
    g->dx = 1.0f / glen;
    ly->last = (uint8_t)k;
}

/*
 * Called by filter.c's clip_read (which replaces the clip reader FUN_080662e4 @0x08066622) before anything else.
 * -1: Repitch, not this one's to read. Otherwise as FUN_080662e4: 0 past the source's end, 1 with n frames in out.
 */
int stretch_read(float rate, uint8_t *pad, int32_t pos, int n, int *used, float *frac, void *scratch, void *out,
                 void **result)
{
    if (!(rate > 0.0f) || setting_or(pad, P_MODE, 0) != 1)
        return -1;
    void *src = *(void **)(pad + 0x24);
    uint8_t *layer = (uint8_t *)frac - 0x1c;
    struct stretch_state *s = stretch_state();
    if (!s || !src || (layer != pad + LAYER_A && layer != pad + LAYER_B))
        return -1;
    int32_t srclen = fw_src_len(src);
    if (srclen + 0xff < pos)
        return 0;
    float tempo = *(const float *)(layer + 0x18);
    float pitch = tempo > 0.01f ? rate / tempo : rate;
    pitch = pitch < 0.0625f ? 0.0625f : pitch > 8.0f ? 8.0f : pitch;
    int lb = layer == pad + LAYER_B;
    unsigned k = setting_or(pad, P_GRAIN, 400);
    float kg = modulated(s, pad, lb, 0, (float)(k > 1000 ? 1000 : k) * 0.001f);
    float glen = 48.0f * (10.0f + 190.0f * kg * kg);         /* frames */
    k = setting_or(pad, P_JITTER, 0);
    float jitter = modulated(s, pad, lb, 1, (float)(k > 1000 ? 1000 : k) * 0.001f);
    int freeze = setting_or(pad, P_FREEZE, 0) == 1;
    struct slayer *ly = &s->layer[pad_index(pad) * 2 + lb];

    /* the frames stock's reader would use, its own arithmetic (FUN_080603ec) */
    float f0 = *frac, f = f0;
    int idx = 0;
    for (int i = 0; i < n; i++) {
        float adv = rate + f;
        int step = (int)adv;
        idx += step;
        f = adv - (float)step;
    }

    if (!ly->live || ly->next != pos) {                     /* a fresh start: grains from here, the first at full level */
        for (int g = 0; g < GRAINS; g++)
            ly->g[g].dx = 0.0f;
        ly->live = 1;
        ly->frozen = 0;
        ly->until = 0;
        spawn(s, ly, pos, f0, glen, 0.0f, pitch, 0.5f, src, 0, srclen);    /* as if it began half a grain ago: the next one is due now */
    }
    if (freeze && !ly->frozen) {
        ly->fz_ip = pos;
        ly->fz_fp = f0;
    }
    ly->frozen = (uint8_t)freeze;

    float *sl = 0, *sr = 0, *ol = 0, *orr = 0;
    int stereo = fw_src_stereo(src) != 0;
    if (stereo) {
        fw_buf_pair(scratch, &sl, &sr);
        fw_buf_pair(out, &ol, &orr);
    } else {
        sl = fw_buf_mono(scratch);
        ol = fw_buf_mono(out);
    }
    int cap = fw_buf_frames(scratch);
    for (int i = 0; i < n; i++) {
        ol[i] = 0.0f;
        if (stereo)
            orr[i] = 0.0f;
    }
    if (cap >= 16) {
        int i = 0;
        while (i < n) {
            if (ly->until <= 0) {
                float a = f0 + rate * (float)i;
                int32_t ai = (int32_t)a;
                if (ly->frozen)
                    spawn(s, ly, ly->fz_ip, ly->fz_fp, glen, jitter, pitch, 0.0f, src, stereo, srclen);
                else
                    spawn(s, ly, pos + ai, a - (float)ai, glen, jitter, pitch, 0.0f, src, stereo, srclen);
                ly->until += (int32_t)(glen * 0.5f);
                if (ly->until <= 0)
                    ly->until = 1;
            }
            int seg = n - i < ly->until ? n - i : (int)ly->until;
            for (int g = 0; g < GRAINS; g++)
                render(&ly->g[g], pitch, src, stereo, srclen, sl, sr, cap, ol + i, stereo ? orr + i : 0, seg);
            ly->until -= seg;
            i += seg;
        }
    }
    ly->next = pos + idx;
    *used = idx;
    *frac = f;
    *result = out;
    return 1;
}

void stretch_register(void *table)
{
    ((register_list_fn)FN(0x0808c0d8))(table, P_SPEED, "Speed:", speed_names, SPEEDS, "clipspeed");
    ((register_list_fn)FN(0x0808c0d8))(table, P_MODE, "Mode:", mode_names, 2, "clipmode");
    ((register_num_fn)FN(0x0808c12c))(table, P_GRAIN, 8, "Grain:", 0, 1000, "clipgrain");
    ((register_num_fn)FN(0x0808c12c))(table, P_JITTER, 8, "Jitter:", 0, 1000, "clipjitter");
    ((register_list_fn)FN(0x0808c0d8))(table, P_FREEZE, "Freeze:", freeze_names, 2, "clipfreeze");
}

void stretch_defaults(void *store)
{
    ((store_add_fn)FN(0x08093ef6))(store, P_SPEED, SPEED_1X);
    ((store_add_fn)FN(0x08093ef6))(store, P_MODE, 0);
    ((store_add_fn)FN(0x08093ef6))(store, P_GRAIN, 400);
    ((store_add_fn)FN(0x08093ef6))(store, P_JITTER, 0);
    ((store_add_fn)FN(0x08093ef6))(store, P_FREEZE, 0);
}

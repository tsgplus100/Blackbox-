/*
 * Munchi Delay's engine, in flash bank 2 (build.sh: BANK2_OBJS), moved out of munchi.cpp for room in bank 1 (JBGRAN 9).
 * The code is munchi.cpp's as it was: TEMPO's granular delay, reverb and ducker, run at 48 kHz on the stock delay's
 * three lines. LEAF ONLY: nothing in here may call bank 1 (test_bank2.py fails the build if it does); its two globals
 * (random state, Width) are fixed words of backup SRAM (munchi_port.h), its maths is inline.
 */
#include <stddef.h>
#include <stdint.h>
#include <new>
#include "munchi_dsp.h"

#pragma GCC optimize("Os", "no-tree-loop-distribute-patterns")

#include "munchi/tempo/granularDelay.h"
#include "munchi/tempo/reverb.h"
#include "munchi/tempo/SimpleCompressor.h"

#define MAGIC 0x4d554e31u                                 /* "MUN1" */
#define MAXN 128

static const float clock_mul[3] = {1.f, .5f, 2.f};
static const float width_mul[4] = {1.f, 0.f, 2.5f, 5.f};

struct Munchi {
    uint32_t magic;
    mbuf_t *live, *frozen;
    granularDelay delay;
    daisysp::Reverb reverb;
    SimpleCompressor comp;
    clockManager clock;
    float wet_amt, reverb_amt, reverb_amt_target, reverb_boost, reverb_boost_target;
    float pulse_phase;
    long pulses;
    int last_wand, last_random, last_feedback, last_freeze, last_duck;
    float clock_mul;
    float wl[MAXN], wr[MAXN];
};

static_assert(sizeof(Munchi) <= MUNCHI_STATE_BYTES, "Munchi's state must fit the stock delay's 2 s line");

static void zero(void *p, uint32_t bytes)
{
    uint32_t *w = (uint32_t *)p;
    for (uint32_t i = 0; i < bytes / 4; i++)
        w[i] = 0;
}

static Munchi *start(uint8_t *st, mbuf_t *live, mbuf_t *frozen, uint32_t frames)
{
    zero(live, frames * 4);
    zero(frozen, frames * 4);
    zero(st, sizeof(Munchi));
    Munchi *m = new (st) Munchi;            /* zeroed just above, as TEMPO's classes expect; default-initialised so the
                                               compiler calls no memset (that one is in bank 1) */
    m->live = live;
    m->frozen = frozen;
    m->reverb.Init(48000.f);
    m->reverb.SetAmount(0.f);
    m->reverb.SetInputGain(.3f);
    m->reverb.SetLowpass(1.f);
    m->comp.Init();
    m->delay.Init(m->live, m->frozen, frames, &m->clock, false);
    m->wet_amt = 1.f;
    m->last_wand = m->last_random = m->last_feedback = m->last_freeze = m->last_duck = -1;
    m->clock_mul = 1.f;
    if (!MUNCHI_RNG)
        MUNCHI_RNG = 0x2545f491u;
    m->magic = MAGIC;
    return m;
}

/* FxEngine::setGranularMain / setGranularFeedback, as Munchi's wrapper has them */
static void set_main(Munchi *m, float val)
{
    m->delay.setMainControl(val);
    if (val > .55f) {
        float norm = (val - .55f) / (1.f - .55f);
        float r = chompi::fast_sqrt(norm);                     /* powf(norm, .5f) */
        m->reverb_amt_target = .25f + .65f * r;
        m->reverb_boost_target = val > .6f ? .3f : 0.f;
    } else {
        m->reverb_amt_target = 0.f;
        m->reverb_boost_target = 0.f;
    }
}

static void controls(Munchi *m, const struct munchi_params *p)
{
    int wand = p->wand, random = p->random, feedback = p->feedback, freeze = p->freeze, duck = p->duck;
    unsigned clock = (unsigned)p->clock, width = (unsigned)p->width;
    m->clock_mul = clock_mul[clock < 3 ? clock : 0];
    MUNCHI_SPREAD = width_mul[width < 4 ? width : 0];
    if (wand != m->last_wand)
        set_main(m, daisysp::fclamp(wand * .001f, 0.f, 1.f));
    if (random != m->last_random)
        m->delay.setAltControl(daisysp::fclamp(random * .001f, 0.f, 1.f));
    if (feedback != m->last_feedback || duck != m->last_duck) {
        float v = daisysp::fclamp(feedback * .001f, 0.f, 1.f);
        m->delay.setFeedback(v);
        float amount = duck == 1 ? 0.f : duck == 2 ? .5f : duck == 3 ? 1.f : (v > .6f ? (v - .6f) / (1.f - .6f) : 0.f);
        m->comp.setAmount(amount);
    }
    if (m->last_freeze >= 0 && freeze != m->last_freeze && freeze != m->delay.getBufferLock())
        m->delay.toggleBufferLock();
    m->last_wand = wand;
    m->last_random = random;
    m->last_feedback = feedback;
    m->last_freeze = freeze;
    m->last_duck = duck;
}

static void run_clock(Munchi *m, float bpm, int frames)
{
    if (!(bpm > 0.f))
        bpm = 120.f;
    bpm *= m->clock_mul;            /* note lengths that would not fit the 4 s buffer are clamped in granularDelay.h */
    m->clock.setBpm(bpm);
    m->pulse_phase += bpm * (24.f / 60.f) * (float)frames * (1.f / 48000.f);
    while (m->pulse_phase >= 1.f) {
        m->pulse_phase -= 1.f;
        m->delay.setClockPulse();
        if (++m->pulses % 12 == 0)
            m->delay.setClockEdge();
    }
}

static inline void process48(Munchi *m, float xl, float xr, float *ol, float *orr)
{
    fonepole(m->wet_amt, 1.f, .001f);
    fonepole(m->reverb_amt, m->reverb_amt_target, .001f);
    fonepole(m->reverb_boost, m->reverb_boost_target, .001f);
    float wl = xl * m->wet_amt, wr = xr * m->wet_amt;
    float dl = xl, dr = xr;                         /* the ducking sidechain: the send itself */
    float yl = 0.f, yr = 0.f;
    m->delay.write(wl, wr);
    m->delay.read(&yl, &yr);
    m->reverb.SetAmount(m->reverb_amt * m->reverb_amt * .8f);
    m->reverb.SetTime(m->reverb_amt);
    m->reverb.SetLowpass(m->reverb_amt * .55f + .4f);
    m->reverb.SetDiffusion(m->reverb_amt * .6f);
    yl += wl * m->reverb_boost;
    yr += wr * m->reverb_boost;
    m->reverb.Process(&yl, &yr);
    m->comp.Process(&yl, &yr, &dl, &dr);
    *ol = yl;
    *orr = yr;
}


extern "C" const float *munchi_block(uint8_t *state, mbuf_t *live, mbuf_t *frozen, uint32_t frames,
                                     const struct munchi_params *p, float bpm, const float *il, const float *ir, int n,
                                     int fresh, const float **right)
{
    Munchi *m = (Munchi *)state;
    if (fresh || m->magic != MAGIC || m->live != live || m->frozen != frozen)
        m = start(state, live, frozen, frames);
    if (n > MAXN)
        n = MAXN;
    controls(m, p);
    run_clock(m, bpm, n);
    for (int i = 0; i < n; i++)
        process48(m, il[i], ir[i], &m->wl[i], &m->wr[i]);
    *right = m->wr;
    return m->wl;
}

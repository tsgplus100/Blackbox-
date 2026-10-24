/*
 * Munchi's engine (munchi_dsp.cpp) lives in flash bank 2; munchi.cpp, in bank 1, owns the hooks, the settings and the
 * delay's three lines, and calls in here only while b2_live() says the payload up there is the one it was linked with.
 */
#pragma once
#include <stdint.h>
#include "munchi/munchi_port.h"

struct munchi_params {
    int wand, random, feedback, freeze, clock, width, duck;    /* the settings as the store has them */
};

#define MUNCHI_STATE_BYTES (96000u * 4u)   /* what the engine's state may take of the delay's 2 s line (asserted there) */

#ifdef __cplusplus
extern "C" {
#endif
/* One block: n frames of send in, the wet out. Starts the engine afresh when `fresh` is set or the state is not its own.
   Returns the left wet, *right the right one (both inside the state, n <= 128). */
const float *munchi_block(uint8_t *state, mbuf_t *live, mbuf_t *frozen, uint32_t frames, const struct munchi_params *p,
                          float bpm, const float *il, const float *ir, int n, int fresh, const float **right);
#ifdef __cplusplus
}
#endif

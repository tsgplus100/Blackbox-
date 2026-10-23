/*
 * Lvl Rnd (gran.c): the grain renderer (FUN_08057db8) works out the grain's left and right gains from its pan once a
 * block, with FUN_08061730 (bl @0x08057ea2) and FUN_08061778 (bl @0x08057eae); r4 is the grain there. These run the
 * original and scale its result by the grain's level, which gran_grain_start left in the grain's spare word +0x3c:
 * a q15 gain under the tag 0x4c56 ("LV"). A grain without the tag (one stock started some other way) plays as it is.
 */
    .syntax unified
    .thumb
    .text

    .macro pan_gain name, original
    .global \name
    .thumb_func
    .type \name, %function
\name:
    push    {r3, lr}
    ldr     r3, =\original + 1
    blx     r3                      @ s0 = the gain
    ldr     r3, [r4, #0x3c]
    lsrs    r2, r3, #16
    movw    r1, #0x4c56
    cmp     r2, r1
    bne     1f
    uxth    r3, r3
    vmov    s1, r3
    vcvt.f32.u32 s1, s1, #15        @ q15 -> 0..1
    vmul.f32 s0, s0, s1
1:  pop     {r3, pc}
    .ltorg
    .endm

    pan_gain gran_gain_l, 0x08061730
    pan_gain gran_gain_r, 0x08061778

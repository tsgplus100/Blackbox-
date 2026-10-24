/*
 * PGM Out: a program change to an external synth. Original 1010music Blackbox, firmware 3.1.9. GRAINBOX 03.
 *
 * Stock receives program changes (Tools > MIDI "PGM In") but never sends one. Two settings on Tools > MIDI, after
 * USB Dev Out (global, saved with the project as "midipgmout" / "midipgmch"):
 *   PGM Out  0 = off, 1..128 = program 1..128 (sent as 0..127)
 *   PGM Ch   1..16
 * Whenever either changes (turning the knob, or loading a project that holds other values) and once after power-on,
 * the program change goes out once, through stock's own MIDI send (FUN_08044a0e: the message to the MIDI Out jacks
 * and, flag set, into the "to USB" queue for the USB host jack, which usbdev.c also hands to a computer). Checked
 * once per engine block (5.3 ms) from duck_block's tick, the audio task stock sends its clock from.
 * State: the value last sent, in the spare end of gran.c's SDRAM block (beside stretch.c's clip state).
 */
#include <stdint.h>

#pragma GCC optimize("Os")

#define FN(addr) ((addr) | 1u)
typedef void (*register_num_fn)(void *table, int param, int type, const char *label, int min, int max, const char *xml);
typedef void (*store_add_fn)(void *store, int param, int value);
typedef int (*setting_fn)(const void *store, int param);
typedef void (*midi_send_fn)(void *manager, const uint8_t *msg, int to_jacks, int to_usb);
#define fw_register_num ((register_num_fn)FN(0x0808c12c))
#define fw_store_add    ((store_add_fn)FN(0x08093ef6))
#define fw_setting      ((setting_fn)FN(0x08093e9c))
#define fw_midi_send    ((midi_send_fn)FN(0x08044a0e))
#define MIDI_MANAGER    ((void *)0x24002e88u)
#define SETTINGS        ((const void *)(0x24020088u + 0x8c90u))   /* app: global settings store */
#define TYPE_INT        1

#define P_PGM_OUT 0x1f0          /* free in stock and the mod (checked by running the registration) */
#define P_PGM_CH  0x194

uint8_t *master_block(void);     /* master.c */
#define PGM_OFFSET (0x56800u + 0x2d100u + 0xf80u)  /* gran.c's block, past stretch.c's clip state at +0xf00 */
#define PGM_MAGIC  0x50474d31u   /* "PGM1" */
struct pgm_state {
    uint32_t magic;
    uint32_t sent;               /* channel << 8 | program, + 1; 0: nothing sent since power-on */
};

void pgm_register(void *table)
{
    fw_register_num(table, P_PGM_OUT, TYPE_INT, "PGM Out:", 0, 128, "midipgmout");
    fw_register_num(table, P_PGM_CH, TYPE_INT, "PGM Ch:", 1, 16, "midipgmch");
}

void pgm_defaults(void *store)
{
    fw_store_add(store, P_PGM_OUT, 0);
    fw_store_add(store, P_PGM_CH, 1);
}

/* duck_block's tick, once per engine block */
void pgm_tick(void)
{
    uint8_t *mem = master_block();
    if (!mem)
        return;
    struct pgm_state *s = (struct pgm_state *)(mem + PGM_OFFSET);
    if (s->magic != PGM_MAGIC) {
        s->magic = PGM_MAGIC;
        s->sent = 0;
    }
    unsigned prog = (unsigned)fw_setting(SETTINGS, P_PGM_OUT), ch = (unsigned)fw_setting(SETTINGS, P_PGM_CH);
    if (prog > 128u || ch - 1u > 15u)
        return;                  /* a project from before PGM Out: stock's lookup answers 0 for both */
    uint32_t now = (ch << 8 | prog) + 1u;
    if (now == s->sent)
        return;
    s->sent = now;
    if (!prog)
        return;
    uint8_t msg[5] = {(uint8_t)(0xc0u | (ch - 1u)), (uint8_t)(prog - 1u), 0, 0, 2};
    fw_midi_send(MIDI_MANAGER, msg, 1, 1);
}

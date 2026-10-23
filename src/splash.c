/*
 * The power-on screen (FUN_080c70b8 builds it: "blackbox", "by 1010music", three empty lines for its error messages,
 * and "3.1.9" in a corner; six text lines, 0x58 bytes apart from +0x34). Here it spells SYEN instead, in italic, out
 * of the screen font's '#' (6 x 8, drawn 2 x 2: 12 x 16 pixels a character): six lines of 16 pixels, one under the
 * other, 312 x 96 pixels in the middle of the screen. Lines go left-aligned from x = 4 (y counts up from the bottom).
 * The error messages (FUN_080c7024: no card, a file missing, ...) still write into lines 3 to 5 when they come.
 */
#include <stdint.h>

#pragma GCC optimize("Os")

#define FN(addr) ((addr) | 1u)
typedef int (*set_text_fn)(uint8_t *label, const char *text);
typedef void (*add_fn)(uint8_t *view, uint8_t *child);
#define fw_set_text ((set_text_fn)FN(0x080c3b98))
#define fw_add      ((add_fn)FN(0x080aec44))

static const char *const logo[6] = {
    "   ##### #   # ##### #   #",
    "   #     #   # #     ##  #",
    "  #####  ###  ####  # # #",
    "      #   #   #     #  ##",
    "     #   #   #     #   #",
    "#####   #   ##### #   #",
};

/* Replaces bl FUN_080aec44 @0x080c72b0, the screen's last step: adding the version line (r1) to it (r0). */
void splash_logo(uint8_t *view, uint8_t *version)
{
    for (int i = 0; i < 6; i++) {
        uint8_t *line = view + 0x34 + 0x58 * i;
        int32_t *rect = (int32_t *)(line + 4);          /* x, y, width, height */
        rect[0] = 4;
        rect[1] = 152 - 16 * i;
        rect[2] = 312;
        rect[3] = 16;
        line[0x51] = 1;                                 /* left-aligned */
        fw_set_text(line, logo[i]);
    }
    fw_add(view, version);
}

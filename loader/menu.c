/* T9 pre-game menu: START GAME / SETTINGS / CONTROLS, drawn by blitting
 * rects from the offline-generated sheet (menu_layout.h -- regenerate with
 * scripts/gen_menu_assets.py after any scripts/menu_def.py change). Pad 1
 * polled the same way main.c's boot-combo check does. Stateless: the record
 * starts at MENU_DEFAULT_RECORD every boot; the staged-EEPROM poke consuming
 * menu_game_record (unconditional since 2026-09-30) lives in main.c. */
#include <kos.h>
#include "menu.h"
#include "menu_layout.h"
#include "ctl_lib.h"

extern uint8 splash_bin[];
extern uint8 menu_sheet_bin[];
extern uint8 ctl_pad_bin[];
extern uint8 ctl_stick_bin[];
extern uint8 logo_bin[];        /* top-screen logo, logo_strip.pal8: 256 x
                                 * RGB565-LE palette (512 B) then 8bpp
                                 * indices, MENU_LOGO_W x MENU_LOGO_H.
                                 * Palettized because the raw RGB565 rect
                                 * blew the CDI 1792-sector loader region. */

unsigned char menu_game_record[16] = MENU_DEFAULT_RECORD;
/* Controls state is not here: it is the shared layout library ctl_lib
 * (ctl_lib.h, controls-library plan) -- per class (pad, stick) the stock
 * layouts plus CTL_N_CUSTOM user slots, and per (class, port) the selected
 * one. Session-only like the record above (.bss zero = every port on stock
 * layout 0). main.c stages ctl_pack() of each (class, port) as that port's
 * resolved SHIM_STATE_LAYOUT_WORD; the shim picks the class per poll. */

/* menu_sheet_bin = menu_sheet.pal8: 256 x RGB565-LE palette (512 B) then
 * MENU_SHEET_W x MENU_SHEET_H 8bpp indices. The palette lives in a static
 * copy (menu_run fills it): the blob section carries no alignment guarantee
 * and SH4 faults on a misaligned uint16 load (the draw_logo lesson). */
static uint16 sheet_pal[256];

static void blit(mrect_t src, int dx, int dy) {
    for (int row = 0; row < src.h; row++) {
        const uint8 *px = menu_sheet_bin + 512 + (src.y + row) * MENU_SHEET_W + src.x;
        uint16 *dst = vram_s + (dy + row) * 640 + dx;
        for (int x = 0; x < src.w; x++)
            dst[x] = sheet_pal[px[x]];
    }
}

static uint32 buttons(int nth) {            /* nth enumerated pad; none = 0 */
    maple_device_t *c = maple_enum_type(nth, MAPLE_FUNC_CONTROLLER);
    cont_state_t *st = c ? (cont_state_t *)maple_dev_status(c) : NULL;
    return st ? (uint32)st->buttons : 0;
}

/* One ~60 Hz poll; returns newly-pressed buttons (edge detect). A missing /
 * unplugged pad reads as 0 -- the menu just waits. `held` = pad 1's buttons
 * down after the poll (menu_run's START-release rule).
 * Retail soft-reset combo (KOS CONT_RESET_BUTTONS, dc/maple/controller.h)
 * HELD on either of the first two pads reboots the console: KOS arch_reboot,
 * the same reset-vector jump the shim's pad_reboot makes in-game. Held, not
 * edge -- five buttons rarely land in one frame. Lives here so it's live on
 * every menu screen. */
static uint32 held;
static uint32 edge(void) {
    uint32 cur = buttons(0);
#if LOADER_FAKE_START
    /* Emulator-leg knob (FAKESTART=MS, top Makefile): press START for ~100 ms,
     * LOADER_FAKE_START ms after the menu opens. The fork's FLYCAST_START_AT
     * counts TA frames only and never fires on this FB-only screen. Never ship. */
    { static uint64 t0; uint64 now = timer_ms_gettime64();
      if (!t0) t0 = now;
      else if (now - t0 > LOADER_FAKE_START && now - t0 < LOADER_FAKE_START + 100u) cur |= CONT_START; }
#endif
    if ((cur & CONT_RESET_BUTTONS) == CONT_RESET_BUTTONS ||
        (buttons(1) & CONT_RESET_BUTTONS) == CONT_RESET_BUTTONS)
        arch_reboot();
    uint32 e = cur & ~held;
    held = cur;
    thd_sleep(16);
    return e;
}

/* Full-screen clear only on screen entry. Redraws blit bg-padded cells
 * straight over the old ones (every cell in menu_layout.h is fixed-size),
 * so per-keypress repaints never touch the rest of the frame -- clearing
 * 640x480 in the live framebuffer on every input was a visible flicker. */
static void clear_bg(void) {
    for (int i = 0; i < 640 * 480; i++) vram_s[i] = MENU_BG_COLOR;
}

static void draw_top(int cur) {
    for (int i = 0; i < 3; i++)
        blit(MENU_TOP_LABEL[i][i == cur],
             MENU_TOP_DEST[i][0], MENU_TOP_DEST[i][1]);
    blit(MENU_TOP_FOOTER, MENU_TOP_FOOTER_X, MENU_TOP_FOOTER_Y);
}

static void draw_settings(int cur, const int *val) {
    blit(MENU_SET_TITLE, MENU_SET_TITLE_X, MENU_SET_TITLE_Y);
    for (int i = 0; i < MENU_N_SETTINGS; i++) {
        blit(MENU_SET_LABEL[i][i == cur], MENU_SET_LABEL_X, MENU_SET_ROW_Y(i));
        blit(MENU_SET_VALUE[i][val[i]],   MENU_SET_VALUE_X, MENU_SET_ROW_Y(i));
    }
    blit(MENU_SET_FOOTER, MENU_SET_FOOTER_X, MENU_SET_FOOTER_Y);
}

static void apply_row(int i, int v) {
    menu_game_record[MENU_SET_IDX[i]] = MENU_SET_BYTE[i][v];
    if (MENU_SET_IDX2[i] != 0xff)               /* two-byte rows (recon) */
        menu_game_record[MENU_SET_IDX2[i]] = MENU_SET_BYTE2[i][v];
}

static void settings_screen(void) {
    int val[MENU_N_SETTINGS], cur = 0;
    for (int i = 0; i < MENU_N_SETTINGS; i++) {   /* current record -> indices */
        val[i] = 0;
        for (int v = 0; v < MENU_SET_NVAL[i]; v++)
            if (MENU_SET_BYTE[i][v] == menu_game_record[MENU_SET_IDX[i]])
                val[i] = v;
    }
    clear_bg();
    draw_settings(cur, val);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_B) return;
        if (e & CONT_DPAD_UP)
            cur = (cur + MENU_N_SETTINGS - 1) % MENU_N_SETTINGS;
        if (e & CONT_DPAD_DOWN)
            cur = (cur + 1) % MENU_N_SETTINGS;
        if (e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) {
            int n = MENU_SET_NVAL[cur];
            val[cur] = (val[cur] + ((e & CONT_DPAD_RIGHT) ? 1 : n - 1)) % n;
            apply_row(cur, val[cur]);
        }
        if (e) draw_settings(cur, val);
    }
}

/* Controls page = layout selector over the shared library (controls-library
 * spec 2026-10-24). Four rows, class-major (menu_layout.h): P1 PAD, P2 PAD,
 * P1 STICK, P2 STICK. The art is the HIGHLIGHTED row's class page
 * (HKT-7700 pad / HKT-7300 stick) with that row's six functions as chips at
 * CTL_ANCHOR[cls]. Chips carry the page BG, so they sit seamlessly on the
 * art's cleared margins. Art memcpy only on entry / class change -- T9
 * flicker rule; row/label/footer changes re-blit fixed cells. */
static int ctl_cls(int row)  { return row / CTL_PORTS; }
static int ctl_port(int row) { return row % CTL_PORTS; }

static const uint8 *ctl_page_bin(int cls) {
    return cls ? ctl_stick_bin : ctl_pad_bin;
}

static const mrect_t *ctl_value_rect(int row) {
    const int cls = ctl_cls(row), port = ctl_port(row);
    const int s = ctl_slot(&ctl_lib, cls, port);
    return s < 0 ? &CTL_STOCK_VALUE[cls][ctl_lib.sel[cls][port]] : &CTL_CUSTOM_VALUE[s];
}

static void ctl_draw_labels(int row) {
    const int cls = ctl_cls(row);
    const unsigned char *f = ctl_funcs(&ctl_lib, cls, ctl_port(row));
    for (int i = 0; i < CTL_N_BUTTONS; i++)
        blit(CTL_WORD[f[i]], CTL_ANCHOR[cls][i][0], CTL_ANCHOR[cls][i][1]);
}

static void ctl_draw_rows(int cur) {
    for (int i = 0; i < CTL_N_ROWS; i++) {
        blit(CTL_ROW_LABEL[i][i == cur], CTL_ROW_LABEL_X, CTL_ROW_Y(i));
        blit(*ctl_value_rect(i), CTL_ROW_VALUE_X, CTL_ROW_Y(i));
    }
}

static void ctl_draw_footer(int which) {
    blit(CTL_FOOTER[which], CTL_FOOTER_X, CTL_FOOTER_Y);
}

/* Rows-page footer: a custom selection adds the edit / delete hints. */
static int ctl_rows_foot(int row) {
    return ctl_slot(&ctl_lib, ctl_cls(row), ctl_port(row)) < 0
         ? CTL_FOOT_ROWS_STOCK : CTL_FOOT_ROWS_CUSTOM;
}

static void ctl_draw_all(int cur) {
    memcpy(vram_s, ctl_page_bin(ctl_cls(cur)), 640 * 480 * 2);
    ctl_draw_labels(cur);
    ctl_draw_rows(cur);
    ctl_draw_footer(ctl_rows_foot(cur));
}

/* Same caps rule the shim applies (jvs.c jvs_pick_class): no analog axes
 * declared = arcade stick. function_data[0] is the controller function's raw
 * DEVINFO data word (KOS dc/maple.h:252 maple_devinfo_t; same word the shim
 * latches as devinfo_caps). First enumerated controller = the one driving
 * this menu (edge() uses the same lookup). */
static int stick_on_menu_pad(void) {
    maple_device_t *c = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
    return c && !(c->info.function_data[0] & 0x00000f00u);
}

/* UP/DOWN wrap across the four rows; LEFT/RIGHT cycle the row's selection
 * (stock ids, then the class's used slots; ctl_cycle). A (edit) and X
 * (delete) arrive with the editor. B returns to the top menu. */
static void controls_screen(void) {
    int cur = stick_on_menu_pad() ? CTL_PORTS : 0;   /* open on the device in hand */
    ctl_draw_all(cur);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_B) return;
        if (!(e & (CONT_DPAD_UP | CONT_DPAD_DOWN | CONT_DPAD_LEFT | CONT_DPAD_RIGHT)))
            continue;
        const int prev = cur;
        if (e & (CONT_DPAD_UP | CONT_DPAD_DOWN))
            cur = (cur + ((e & CONT_DPAD_DOWN) ? 1 : CTL_N_ROWS - 1)) % CTL_N_ROWS;
        if (e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT))
            ctl_cycle(&ctl_lib, ctl_cls(cur), ctl_port(cur), (e & CONT_DPAD_RIGHT) ? 1 : -1);
        if (ctl_cls(cur) != ctl_cls(prev)) { ctl_draw_all(cur); continue; }
        ctl_draw_labels(cur);
        ctl_draw_rows(cur);
        ctl_draw_footer(ctl_rows_foot(cur));
    }
}

/* Entry-only (with draw_top's block moved below it, per-keypress repaints
 * never touch the logo rows). Palette copied to the stack first: the blob
 * section carries no alignment guarantee, and SH4 faults on a misaligned
 * uint16 load. */
static void draw_logo(void) {
    uint16 pal[256];
    memcpy(pal, logo_bin, sizeof pal);
    const uint8 *px = logo_bin + sizeof pal;
    for (int y = 0; y < MENU_LOGO_H; y++) {
        uint16 *dst = vram_s + (MENU_LOGO_Y + y) * 640 + MENU_LOGO_X;
        for (int x = 0; x < MENU_LOGO_W; x++)
            *dst++ = pal[*px++];
    }
}

void menu_run(void) {
    int cur = 0;
    memcpy(sheet_pal, menu_sheet_bin, sizeof sheet_pal);
    clear_bg();
    draw_logo();
    draw_top(cur);
    for (;;) {
        uint32 e = edge();
        /* Start from anywhere -- on RELEASE: a START landing a frame before
         * A+B+X+Y must reboot (edge() sees the combo while we wait), not
         * start the game. */
        if (e & CONT_START) {
            while (held & CONT_START) edge();
            break;
        }
        if (e & CONT_DPAD_UP)   { cur = (cur + 2) % 3; draw_top(cur); }
        if (e & CONT_DPAD_DOWN) { cur = (cur + 1) % 3; draw_top(cur); }
        if (e & CONT_A) {
            if (cur == 0) break;
            if (cur == 1) settings_screen();
            else          controls_screen();
            clear_bg();                          /* sub-screen leftovers */
            draw_logo();
            draw_top(cur);
        }
    }
    memcpy(vram_s, splash_bin, 640 * 480 * 2);   /* today's load screen */
}

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

static void ctl_chip(int cls, int b, unsigned char id, int hi) {
    blit((hi ? CTL_WORD_HI : CTL_WORD)[id], CTL_ANCHOR[cls][b][0], CTL_ANCHOR[cls][b][1]);
}

static void ctl_draw_labels(int row) {
    const int cls = ctl_cls(row);
    const unsigned char *f = ctl_funcs(&ctl_lib, cls, ctl_port(row));
    for (int i = 0; i < CTL_N_BUTTONS; i++)
        ctl_chip(cls, i, f[i], 0);
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

/* Edit-mode cursor: a 2-px frame just OUTSIDE chip `b`'s cell, so re-blitting
 * the chip never clips it. On = MENU_HI_COLOR; off restores the page's own
 * pixels from ctl_page_bin(cls) (the page-pixel rule: whatever the page has
 * under the ring comes back; on both shipped pages that is plain BG under
 * every ring, checked 2026-10-25). The stick's right column has 1-px gaps
 * (C/B, B/A), so a frame covers a neighbour's padding row: frames go on
 * after the chips, and the old frame goes off (page = BG there) before the
 * new one goes on. The blob is read byte-wise (LE RGB565,
 * as bmp2rgb565.py wrote it): an objcopy'd blob has no alignment guarantee
 * and SH4 faults on a misaligned uint16 load (the draw_logo lesson). */
static void ctl_cursor(int cls, int b, int on) {
    const uint8 *bin = ctl_page_bin(cls);
    const int x0 = CTL_ANCHOR[cls][b][0] - 2, y0 = CTL_ANCHOR[cls][b][1] - 2;
    const int w = CTL_WORD[0].w + 4, h = CTL_WORD[0].h + 4;
    for (int y = y0; y < y0 + h; y++)
        for (int x = x0; x < x0 + w; x++) {
            if (y >= y0 + 2 && y < y0 + h - 2 && x >= x0 + 2 && x < x0 + w - 2)
                continue;                              /* inside: the chip itself */
            const int i = y * 640 + x;
            vram_s[i] = on ? MENU_HI_COLOR : (uint16)(bin[2 * i] | (bin[2 * i + 1] << 8));
        }
}

/* Chip editor (spec §3), on the layout row `row` shows. The d-pad moves the
 * frame to the neighbouring chip (CTL_EDIT_NAV, no wrap). A opens value mode:
 * the chip becomes an amber band and LEFT/RIGHT cycle a candidate through
 * every function word (B.O.S.S. and NONE included); A keeps it via ctl_keep
 * -- on a stock row the first changed keep forks the layout into the lowest
 * free slot and the row value flips to CUSTOM n -- B drops it. B outside
 * value mode returns; the caller restores the rows footer. Only the chip,
 * frame, rows and footer repaint. Same edge() poll: reset combo stays live. */
static void ctl_edit(int row) {
    const int cls = ctl_cls(row), port = ctl_port(row);
    int b = CTL_EDIT_FIRST[cls], editing = 0;
    unsigned char cand = 0;
    ctl_draw_footer(CTL_FOOT_EDIT);
    ctl_cursor(cls, b, 1);
    for (;;) {
        uint32 e = edge();
        if (editing) {
            if (e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) {
                cand = (unsigned char)((cand + ((e & CONT_DPAD_RIGHT) ? 1 : CTL_N_FUNC - 1)) % CTL_N_FUNC);
                ctl_chip(cls, b, cand, 1);
            }
            /* SAME / FULL change nothing; FULL cannot happen here (A on the
             * rows page refuses a stock row when no slot is free). */
            if ((e & CONT_A) && ctl_keep(&ctl_lib, cls, port, b, cand) == CTL_KEEP_FORKED)
                ctl_draw_rows(row);
            if (e & (CONT_A | CONT_B)) {
                editing = 0;
                ctl_chip(cls, b, ctl_funcs(&ctl_lib, cls, port)[b], 0);
                ctl_draw_footer(CTL_FOOT_EDIT);
            }
            continue;
        }
        if (e & CONT_B) { ctl_cursor(cls, b, 0); return; }
        if (e & CONT_A) {
            editing = 1;
            cand = ctl_funcs(&ctl_lib, cls, port)[b];
            ctl_chip(cls, b, cand, 1);
            ctl_draw_footer(CTL_FOOT_VALUE);
            continue;
        }
        int d = (e & CONT_DPAD_UP) ? 0 : (e & CONT_DPAD_DOWN) ? 1
              : (e & CONT_DPAD_LEFT) ? 2 : (e & CONT_DPAD_RIGHT) ? 3 : -1;
        if (d >= 0 && CTL_EDIT_NAV[cls][b][d] != CTL_NAV_NONE) {
            ctl_cursor(cls, b, 0);
            b = CTL_EDIT_NAV[cls][b][d];
            ctl_cursor(cls, b, 1);
        }
    }
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
 * (stock ids, then the class's used slots; ctl_cycle). A customizes (spec
 * §3): a stock row with no free slot in its class shows the FULL footer
 * until the next press (that press is then processed normally), otherwise
 * ctl_edit -- a full library never blocks a custom row. X on a custom row
 * asks DELETE? (spec §4); the next press answers and is consumed: X frees
 * the slot (every row on it falls back to stock 0), anything else cancels.
 * X on a stock row does nothing. B returns to the top menu. */
static void controls_screen(void) {
    int cur = stick_on_menu_pad() ? CTL_PORTS : 0;   /* open on the device in hand */
    int msg = 0, confirm = 0;
    ctl_draw_all(cur);
    for (;;) {
        uint32 e = edge();
        if (!e) continue;
        const int cls = ctl_cls(cur), slot = ctl_slot(&ctl_lib, cls, ctl_port(cur));
        if (confirm) {
            confirm = 0;
            if (e & CONT_X) { ctl_delete(&ctl_lib, cls, slot); ctl_draw_labels(cur); }
            ctl_draw_rows(cur);
            ctl_draw_footer(ctl_rows_foot(cur));
            continue;
        }
        if (msg) { msg = 0; ctl_draw_footer(ctl_rows_foot(cur)); }
        if (e & CONT_B) return;
        if (e & CONT_A) {
            if (slot < 0 && ctl_free_slot(&ctl_lib, cls) < 0) {
                ctl_draw_footer(CTL_FOOT_FULL);
                msg = 1;
            } else {
                ctl_edit(cur);
                ctl_draw_rows(cur);
                ctl_draw_footer(ctl_rows_foot(cur));
            }
            continue;
        }
        if ((e & CONT_X) && slot >= 0) {
            blit(CTL_DELETE_VALUE, CTL_ROW_VALUE_X, CTL_ROW_Y(cur));
            ctl_draw_footer(CTL_FOOT_CONFIRM);
            confirm = 1;
            continue;
        }
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

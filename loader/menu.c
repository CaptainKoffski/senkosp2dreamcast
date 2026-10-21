/* T9 pre-game menu: START GAME / SETTINGS / CONTROLS, drawn by blitting
 * rects from the offline-generated sheet (menu_layout.h -- regenerate with
 * scripts/gen_menu_assets.py after any scripts/menu_def.py change). Pad 1
 * polled the same way main.c's boot-combo check does. Stateless: the record
 * starts at MENU_DEFAULT_RECORD every boot; the staged-EEPROM poke consuming
 * menu_game_record (unconditional since 2026-09-30) lives in main.c. */
#include <kos.h>
#include "menu.h"
#include "menu_layout.h"

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
/* Controls-page selector state (spec 2026-09-27): per-port pad preset,
 * 0 = Tournament (default), 1 = Old. Session-only like the record above
 * (VMU save-all-settings will serialize it later); consumed by main.c's
 * SHIM_STATE staging write. Sticks ignore it (shim classifies from DEVINFO). */
unsigned char menu_pad_layout[2] = { 0, 0 };
/* CUSTOM layouts (tester ask 2026-10-15): per-port function ids (CTL_WORD /
 * menu_def.py FUNC_WORDS index) per pad button, A B X Y L R. Start as a copy
 * of CTL_CUSTOM_DEFAULT so a fresh CUSTOM row is never empty; ctl_edit()
 * changes them in place; main.c packs each port into its
 * SHIM_STATE_PAD_CUSTOM word (4 bits per button). Session-only, as above. */
unsigned char menu_custom[2][6] = { CTL_CUSTOM_DEFAULT, CTL_CUSTOM_DEFAULT };

static void blit(mrect_t src, int dx, int dy) {
    const uint16 *sheet = (const uint16 *)menu_sheet_bin;
    for (int row = 0; row < src.h; row++)
        memcpy(vram_s + (dy + row) * 640 + dx,
               sheet + (src.y + row) * MENU_SHEET_W + src.x, src.w * 2);
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

/* Controls page = layout selector (spec 2026-09-27). Three rows under the
 * diagram; the diagram previews the HIGHLIGHTED row (pad rows: that port's
 * preset on the HKT-7700 art; stick row: the fixed arcade layout on the
 * HKT-7300 art, labels baked into the page since its layout never changes).
 * Chips carry the page BG, so they sit seamlessly on the art's cleared
 * margins. Art memcpy only on entry / device-view change -- T9 flicker
 * rule; row/label changes re-blit fixed cells. */
static void ctl_draw_labels(int cur) {
    if (cur == 2) return;              /* stick page: fixed, fully baked */
    const unsigned char *f = (menu_pad_layout[cur] == CTL_PAD_CUSTOM)
        ? menu_custom[cur] : CTL_PAD_FUNC[menu_pad_layout[cur]];
    for (int i = 0; i < 6; i++)
        blit(CTL_WORD[f[i]], CTL_PAD_ANCHOR[i][0], CTL_PAD_ANCHOR[i][1]);
}

/* Edit-mode cursor: a 2-px frame just OUTSIDE chip `b`'s cell, so re-blitting
 * the chip never clips it. On = MENU_HI_COLOR; off restores the page's own
 * pixels from ctl_pad_bin -- a leader line ends at the chip's edge, right
 * under the frame, and a flat BG fill would nick it. The blob is read
 * byte-wise (LE RGB565, as bmp2rgb565.py wrote it): an objcopy'd blob has
 * no alignment guarantee and SH4 faults on a misaligned uint16 load (the
 * draw_logo lesson). */
static void ctl_cursor(int b, int on) {
    const int x0 = CTL_PAD_ANCHOR[b][0] - 2, y0 = CTL_PAD_ANCHOR[b][1] - 2;
    const int w = CTL_WORD[0].w + 4, h = CTL_WORD[0].h + 4;
    for (int y = y0; y < y0 + h; y++)
        for (int x = x0; x < x0 + w; x++) {
            if (y >= y0 + 2 && y < y0 + h - 2 && x >= x0 + 2 && x < x0 + w - 2)
                continue;                              /* inside: the chip itself */
            const int i = y * 640 + x;
            vram_s[i] = on ? MENU_HI_COLOR
                           : (uint16)(ctl_pad_bin[2 * i] | (ctl_pad_bin[2 * i + 1] << 8));
        }
}

/* CUSTOM editor (2026-10-15; cursor rework 2026-10-22): entered with A on a
 * pad row showing CUSTOM. The d-pad moves the cursor to the neighbouring
 * chip in that direction (CTL_EDIT_NAV: follows the page, no wrap -- RIGHT
 * on the L trigger lands on the R trigger). A opens value mode: the chip
 * becomes an amber band (CTL_WORD_HI) and LEFT/RIGHT cycle every function
 * word (B.O.S.S. and NONE included); A keeps the value, B restores the one
 * it had. B outside value mode returns to the rows. MOVE and START carry
 * no chip. Same edge() poll, so the reset combo stays live here too. */
static void ctl_chip(int port, int b, int hi) {
    const mrect_t *w = hi ? CTL_WORD_HI : CTL_WORD;
    blit(w[menu_custom[port][b]], CTL_PAD_ANCHOR[b][0], CTL_PAD_ANCHOR[b][1]);
}
static void ctl_edit(int port) {
    int b = CTL_EDIT_FIRST, editing = 0;
    unsigned char saved = 0;
    ctl_cursor(b, 1);
    for (;;) {
        uint32 e = edge();
        unsigned char *f = &menu_custom[port][b];
        if (editing) {
            if (e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) {
                *f = (unsigned char)((*f + ((e & CONT_DPAD_RIGHT) ? 1 : CTL_N_FUNC - 1)) % CTL_N_FUNC);
                ctl_chip(port, b, 1);
            }
            if (e & CONT_B) *f = saved;                       /* discard */
            if (e & (CONT_A | CONT_B)) { editing = 0; ctl_chip(port, b, 0); }
            continue;
        }
        if (e & CONT_B) { ctl_cursor(b, 0); return; }
        if (e & CONT_A) { saved = *f; editing = 1; ctl_chip(port, b, 1); continue; }
        int d = (e & CONT_DPAD_UP) ? 0 : (e & CONT_DPAD_DOWN) ? 1
              : (e & CONT_DPAD_LEFT) ? 2 : (e & CONT_DPAD_RIGHT) ? 3 : -1;
        if (d >= 0 && CTL_EDIT_NAV[b][d] != CTL_NAV_NONE) {
            ctl_cursor(b, 0);
            b = CTL_EDIT_NAV[b][d];
            ctl_cursor(b, 1);
        }
    }
}

static void ctl_draw_rows(int cur) {
    for (int i = 0; i < 3; i++)
        blit(CTL_ROW_LABEL[i][i == cur], CTL_ROW_LABEL_X, CTL_ROW_Y(i));
    blit(CTL_PAD_VALUE[menu_pad_layout[0]], CTL_ROW_VALUE_X, CTL_ROW_Y(0));
    blit(CTL_PAD_VALUE[menu_pad_layout[1]], CTL_ROW_VALUE_X, CTL_ROW_Y(1));
    blit(CTL_STICK_VALUE, CTL_ROW_VALUE_X, CTL_ROW_Y(2));
}

static void ctl_draw_all(int cur) {
    memcpy(vram_s, cur == 2 ? ctl_stick_bin : ctl_pad_bin, 640 * 480 * 2);
    ctl_draw_labels(cur);
    ctl_draw_rows(cur);
}

/* Same caps rule the shim applies (jvs.c jvs_pick_layout): no analog axes
 * declared = arcade stick. function_data[0] is the controller function's raw
 * DEVINFO data word (KOS dc/maple.h:252 maple_devinfo_t; same word the shim
 * latches as devinfo_caps). First enumerated controller = the one driving
 * this menu (edge() uses the same lookup). */
static int stick_on_menu_pad(void) {
    maple_device_t *c = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
    return c && !(c->info.function_data[0] & 0x00000f00u);
}

static void controls_screen(void) {
    int cur = stick_on_menu_pad() ? 2 : 0;   /* open on the device in hand */
    ctl_draw_all(cur);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_B) return;
        if (e & (CONT_DPAD_UP | CONT_DPAD_DOWN)) {
            int nxt = (cur + ((e & CONT_DPAD_DOWN) ? 1 : 2)) % 3;
            int devchg = (nxt == 2) != (cur == 2);
            cur = nxt;
            if (devchg) ctl_draw_all(cur);
            else { ctl_draw_labels(cur); ctl_draw_rows(cur); }
        }
        if ((e & (CONT_DPAD_LEFT | CONT_DPAD_RIGHT)) && cur < 2) {
            const int n = CTL_PAD_CUSTOM + 1;    /* Tournament, Old, Custom */
            menu_pad_layout[cur] = (unsigned char)
                ((menu_pad_layout[cur] + ((e & CONT_DPAD_RIGHT) ? 1 : n - 1)) % n);
            ctl_draw_labels(cur);
            ctl_draw_rows(cur);
        }
        if ((e & CONT_A) && cur < 2 && menu_pad_layout[cur] == CTL_PAD_CUSTOM)
            ctl_edit(cur);
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

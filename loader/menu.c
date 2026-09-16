/* T9 pre-game menu: START GAME / SETTINGS / CONTROLS, drawn by blitting
 * rects from the offline-generated sheet (menu_layout.h -- regenerate with
 * scripts/gen_menu_assets.py after any scripts/menu_def.py change). Pad 1
 * polled the same way main.c's boot-combo check does. Stateless: the record
 * starts at the baked defaults every boot; the staged-EEPROM poke consuming
 * menu_game_record/menu_dirty lives in main.c. */
#include <kos.h>
#include "menu.h"
#include "menu_layout.h"

extern uint8 splash_bin[];
extern uint8 menu_sheet_bin[];
extern uint8 controls_bin[];

unsigned char menu_game_record[16] = MENU_DEFAULT_RECORD;
int menu_dirty = 0;

static void blit(mrect_t src, int dx, int dy) {
    const uint16 *sheet = (const uint16 *)menu_sheet_bin;
    for (int row = 0; row < src.h; row++)
        memcpy(vram_s + (dy + row) * 640 + dx,
               sheet + (src.y + row) * MENU_SHEET_W + src.x, src.w * 2);
}

/* One ~60 Hz poll; returns newly-pressed buttons (edge detect). A missing /
 * unplugged pad reads as 0 -- the menu just waits. */
static uint32 edge(void) {
    static uint32 prev;
    maple_device_t *c = maple_enum_type(0, MAPLE_FUNC_CONTROLLER);
    cont_state_t *st = c ? (cont_state_t *)maple_dev_status(c) : NULL;
    uint32 cur = st ? (uint32)st->buttons : 0;
    uint32 e = cur & ~prev;
    prev = cur;
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
    menu_dirty = 1;
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

static void controls_screen(void) {
    memcpy(vram_s, controls_bin, 640 * 480 * 2);
    for (;;)
        if (edge() & CONT_B) return;
}

void menu_run(void) {
    int cur = 0;
    clear_bg();
    draw_top(cur);
    for (;;) {
        uint32 e = edge();
        if (e & CONT_START) break;               /* start from anywhere */
        if (e & CONT_DPAD_UP)   { cur = (cur + 2) % 3; draw_top(cur); }
        if (e & CONT_DPAD_DOWN) { cur = (cur + 1) % 3; draw_top(cur); }
        if (e & CONT_A) {
            if (cur == 0) break;
            if (cur == 1) settings_screen();
            else          controls_screen();
            clear_bg();                          /* sub-screen leftovers */
            draw_top(cur);
        }
    }
    memcpy(vram_s, splash_bin, 640 * 480 * 2);   /* today's load screen */
}

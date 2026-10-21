/* T9 pre-game menu (spec docs/superpowers/specs/2026-09-11-phase7-t9-pregame-menu-design.md). */
#ifndef MENU_H
#define MENU_H
extern unsigned char menu_game_record[16];   /* session record, defaults each boot */
extern unsigned char menu_pad_layout[2];  /* per-port PAD preset: 0 Tournament, 1 Old, 2 Custom */
extern unsigned char menu_custom[2][6];   /* per-port CUSTOM layout: function id per pad button, A B X Y L R */
void menu_run(void);   /* blocks until START GAME; repaints the splash on exit */
#endif

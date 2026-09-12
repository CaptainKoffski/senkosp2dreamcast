/* T9 pre-game menu (spec docs/superpowers/specs/2026-09-11-phase7-t9-pregame-menu-design.md). */
#ifndef MENU_H
#define MENU_H
extern unsigned char menu_game_record[16];   /* session record, defaults each boot */
extern int menu_dirty;                       /* 1 iff a setting was changed */
void menu_run(void);   /* blocks until START GAME; repaints the splash on exit */
#endif

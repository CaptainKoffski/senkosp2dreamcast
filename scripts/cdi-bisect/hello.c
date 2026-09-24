/* CDI-bisect control payload: proves the BIOS->IP->1ST_READ boot chain on
 * whatever medium carries it, with zero disc access of its own.  Draws a
 * magenta/green frame counter screen forever -- if you can see it, the boot
 * chain works.  docs/kb/tooling.md §CDI mastering, hardware round 2. */
#include <kos.h>

KOS_INIT_FLAGS(INIT_DEFAULT | INIT_NO_DCLOAD);

int main(int argc, char **argv) {
    int frame = 0;
    vid_set_mode(DM_640x480, PM_RGB565);
    for (;;) {
        uint16 *fb = vram_s;
        uint16 col = (frame & 32) ? 0xF81F : 0x07E0;   /* magenta / green */
        for (int y = 0; y < 480; y++)
            for (int x = 0; x < 640; x++)
                fb[y * 640 + x] = (y < 40 || y >= 440) ? col : 0x0000;
        bfont_draw_str(vram_s + 220 * 640 + 40, 640, 1,
                       "CDI BOOT CHAIN OK - senkosp bisect");
        frame++;
        vid_waitvbl();
    }
    return 0;
}

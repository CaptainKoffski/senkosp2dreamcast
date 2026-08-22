/* SCIF debug out. Baud/pin state inherited from the KOS boot (dbgio scif).
 * SHIM_SERIAL=0 (release default) compiles putc to a no-op so the shim never
 * touches the SCIF registers: serial-SD dongles (DreamShell isoldr) drive
 * their SD card over these pins. Debug builds: make DEFS=-DSHIM_SERIAL=1. */
#ifndef SHIM_SERIAL
#define SHIM_SERIAL 0
#endif
typedef volatile unsigned short vu16; typedef volatile unsigned char vu8;
#define SCFSR2  (*(vu16 *)0xffe80010)
#define SCFTDR2 (*(vu8  *)0xffe8000c)
void scif_putc(char c) {
#if SHIM_SERIAL
    /* Bounded TDFE wait (final review): this spin sits upstream of shim_die,
     * which prints serial BEFORE its VRAM paint -- if the game ever disabled
     * or misclocked SCIF TX, an unbounded wait here would turn the loud death
     * screen back into a silent black hang. ~1M spins >> one FIFO drain at
     * 115200 baud; on timeout the char is dropped (serial is diagnostics). */
    for (unsigned g = 0; !(SCFSR2 & 0x20); g++)
        if (g > 1000000u) return;       /* TDFE never came: drop the char */
    SCFTDR2 = (unsigned char)c;
    SCFSR2 &= (unsigned short)~0x60;/* clear TDFE|TEND */
#else
    (void)c;
#endif
}
void scif_puts(const char *s) { while (*s) { if (*s=='\n') scif_putc('\r'); scif_putc(*s++); } }
void scif_puthex(unsigned int v) {
    for (int i = 28; i >= 0; i -= 4) scif_putc("0123456789abcdef"[(v >> i) & 15]);
}

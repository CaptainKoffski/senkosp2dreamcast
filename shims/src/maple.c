/* Real DC Maple GetCondition on the port-A main controller, polled (no IRQ).
 * Same Maple DMA hardware the Naomi game already drives; the shim owns the bus
 * once the MIE builders are hooked, so this synchronous one-shot never collides.
 *
 * Frame + register layout verified against KOS
 * (kernel/arch/dreamcast/hardware/maple/maple_queue.c:50-63, dc/maple.h:139-174):
 *   word0 = length | (port<<16) | (last<<31)
 *   word1 = recv_buf phys (& MEM_AREA_CACHE_MASK)
 *   word2 = cmd | (maple_addr(port,unit)<<8) | ((port<<6)<<16) | (length<<24)
 *   word3.. = param words
 *   port A = 0, maple_addr(portA, main) = 0x20, GETCOND = 9,
 *   FUNC_CONTROLLER = 0x01000000, reply resp code DATATRF = 8.
 * TX/RX buffers live in shim home and are accessed via P2 (uncached): the DMA
 * writes RX in RAM, so the CPU must read it uncached to see fresh data. */
#include "shim_iface.h"
typedef unsigned int u32;

#define SB_MDSTAR (*(volatile u32 *)0xa05f6c04)   /* DMA start address */
#define SB_MDTSEL (*(volatile u32 *)0xa05f6c10)   /* trigger select (0 = SW) */
#define SB_MDEN   (*(volatile u32 *)0xa05f6c14)   /* DMA enable */
#define SB_MDST   (*(volatile u32 *)0xa05f6c18)   /* start / status */
#define SB_MSPEED (*(volatile u32 *)0xa05f6c80)   /* bus speed + timeout */
#define SB_MDAPRO (*(volatile u32 *)0xa05f6c8c)   /* DMA address protection */

/* Last reply header per port (rx[0]), for the HW input diagnostics: 0 = DMA
 * never wrote the buffer, 8 in low byte = DATATRF (healthy). .data init. */
u32 maple_hdr[2] = { 0xaaaa0000, 0xaaaa0001 };

/* HW round 13 ("Start dead on real HW, works in Flycast"): re-assert the bus
 * setup KOS programmed (maple_init_shutdown.c:156-159 — DMA_PROT covering all
 * 16 MB, 2 Mbps + 50000 timeout, software trigger, bus enabled) once before
 * our first transaction. Harmless when already set; heals anything that got
 * reset between KOS init and game runtime. .data flag per house style. */
static u32 bus_init_done = 0x10000;

/* HW round 14: GetCondition to port A consistently gets the no-response marker
 * (FFFFFFFF) on real HW despite a byte-perfect frame, while the same pad works
 * in openMenu -- and every normal flow (BIOS, KOS, menus) sends DEVICE REQUEST
 * (cmd 1, "who are you") before polling. Some pads (clones especially) stay
 * silent until probed. Send one DEVINFO per port at init; reply headers kept
 * for the on-screen diagnostics (healthy low byte = 5). */
u32 devinfo_hdr[2] = { 0xbbbb0000, 0xbbbb0001 };
static void probe_devinfo(unsigned int port) {
    volatile u32 *tx = P2(MAPLE_TX);
    volatile u32 *rx = P2(MAPLE_RX);
    unsigned int dst = (port << 6) | 0x20u;
    rx[0] = 0;
    tx[0] = 0x80000000u | (port << 16);                    /* last | port | 0 param words */
    tx[1] = MAPLE_RX & 0x1fffffff;
    tx[2] = ((port << 6) << 16) | (dst << 8) | 1u;         /* DEVICE REQUEST, len 0 */
    (void)tx[2]; (void)rx[0];                              /* write-buffer barrier */
    SB_MDTSEL = 0;
    SB_MDSTAR = MAPLE_TX & 0x1fffffff;
    SB_MDEN = 1;
    SB_MDST = 1;
    while (SB_MDST & 1) ;
    devinfo_hdr[port] = rx[0];
}

/* Returns the PRESSED mask (src/jvs.c dc_cond_to_pressed: buttons inverted,
 * analog stick folded into the D-pad bits, rtrig as CONT_RTRIG) for the given
 * DC Maple port (A=0, B=1), or 0 (= nothing pressed) if there is no controller
 * on that port / the reply failed -- so dc_to_jvs() reads idle and P2 stays
 * idle when only one pad is plugged in. (Task 12: Cleopatra returned the raw
 * ACTIVE-LOW word and inverted inside its own dc_to_jvs; this port's dc_to_jvs
 * was written in Task 6 to take an already-normalized pressed mask, and it has
 * a trigger bit Cleopatra's game had no use for. Normalizing here keeps ONE
 * contract instead of two, and it is the pure, host-tested function that owns
 * it.)
 * Port addressing (KOS maple_utils.c:47-52 maple_addr, maple_queue.c:49/55-56):
 * word0 dst_port field = port<<16 -- THIS selects the physical bus/port that
 * Flycast routes to (maple_if.cpp:198 bus=(header_1>>16)&3). word2 dst =
 * maple_addr(port,main)=(port<<6)|0x20 (A=0x20, B=0x60); Flycast getPort()
 * (maple_if.cpp:131-137) resolves either to unit 5 = main controller. src port
 * field = (port<<6)<<16. */
unsigned dc_cond_to_pressed(unsigned w2, unsigned w3);     /* src/jvs.c */
unsigned int maple_getcond(unsigned int port) {
    volatile u32 *tx = P2(MAPLE_TX);
    volatile u32 *rx = P2(MAPLE_RX);
    unsigned int dst = (port << 6) | 0x20u;                /* maple_addr(port, main): A=0x20 B=0x60 */
    if (bus_init_done & 0x10000u) {                        /* one-time bus re-assert (KOS values) */
        bus_init_done = 1;
        SB_MDAPRO = 0x6155404fu;                           /* window = whole 16 MB RAM */
        SB_MSPEED = 0xC3500000u;                           /* 2 Mbps | timeout 50000 */
        SB_MDTSEL = 0;
        SB_MDEN   = 1;
        probe_devinfo(0); probe_devinfo(1);                /* wake pads: DEVINFO before polls */
    }
    for (u32 attempt = 0; attempt < 2; attempt++) {        /* one retry on failed reply */
        rx[0] = 0;                                          /* clear old reply header */
        tx[0] = 0x80000000u | (port << 16) | 1u;           /* last | dst port | 1 param word */
        tx[1] = MAPLE_RX & 0x1fffffff;                     /* recv addr (phys) */
        tx[2] = (1u << 24) | ((port << 6) << 16) | (dst << 8) | 9u; /* len | src port | dst main | GETCOND */
        tx[3] = 0x01000000u;                               /* FUNC_CONTROLLER */
        /* SH4 write-buffer barrier (HW round 14: port-A replies = FFFFFFFF,
         * the Maple no-response marker -- the DMA fetched the descriptor
         * before these P2 stores drained to RAM, transmitting stale bytes;
         * instant-memory Flycast can't show it). An uncached read-back
         * serializes prior stores; volatile so -Os can't elide it. */
        (void)tx[3]; (void)rx[0];
        SB_MDTSEL = 0;
        SB_MDSTAR = MAPLE_TX & 0x1fffffff;
        SB_MDEN = 1;
        SB_MDST = 1;
        while (SB_MDST & 1) ;   /* ponytail: bare poll like gd.c; maple DMA always self-clears (HW timeout) */
        maple_hdr[port] = rx[0];                           /* diagnostics: raw reply header */
        if ((rx[0] & 0xff) == 8)
            return dc_cond_to_pressed(rx[2], rx[3]);       /* cont_cond_t, words 2-3 */
    }
    return 0;                                              /* not DATATRF -> no/failed reply */
}

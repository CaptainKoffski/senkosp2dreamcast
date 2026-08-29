// Report literal-pool constants that equal a watched MMIO register address,
// the instruction that loads each, and its containing function. These functions
// are the Phase 4 patch candidates: cart-read (cart/G1 blocks), input-decode &
// EEPROM (Maple block). Physical addresses; the game loads them via mov.l @(disp,pc).
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryAccessException;

public class FindMmioXrefs extends GhidraScript {
    // (label, lo, hi) inclusive physical ranges, 29-bit.
    private static final long[][] BLOCKS = {
        {0x005f7000L, 0x005f7014L}, // cart ROM-board regs
        {0x005f7400L, 0x005f74ffL}, // G1 GD-ROM DMA channel
        {0x005f6c00L, 0x005f6cffL}, // Maple bus controller
        // Phase 5 round-4: widened from FB_SOF-only (0 hits) to the whole CORE
        // render-config block INCLUDING the 0x5f8000 base itself — the game
        // reaches these regs via base+disp, so only the base constant pools.
        {0x005f8000L, 0x005f814fL}, // PVR CORE render config (ISP_FEED_CFG etc.)
        {0x00710000L, 0x0071ffffL}, // Naomi RTC (guts scan: 3 refs to trace)
        {0x1fe80000L, 0x1fe8ffffL}, // SH-4 SCIF (0xffe80000 & 0x1fffffff)
        {0x1fc00000L, 0x1fc000ffL}, // SH-4 WDT (WTCNT/WTCSR) — expect zero
    };
    private static final String[] LABELS = {"cart", "g1dma", "maple", "pvr_core", "rtc", "scif", "wdt"};

    @Override
    public void run() throws Exception {
        Listing lst = currentProgram.getListing();
        InstructionIterator it = lst.getInstructions(true);
        int hits = 0;
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            // SH-4 materializes MMIO addrs as pc-relative pool loads; the resolved
            // constant shows up as a scalar/reference operand Ghidra already computed.
            for (int op = 0; op < ins.getNumOperands(); op++) {
                Long v = operandValue(ins, op);
                if (v == null) continue;
                long phys = v & 0x1fffffffL;
                for (int b = 0; b < BLOCKS.length; b++) {
                    if (phys >= BLOCKS[b][0] && phys <= BLOCKS[b][1]) {
                        Function f = getFunctionContaining(ins.getAddress());
                        println(String.format("XREF block=%s const=0x%08x at=%s fn=%s@%s",
                                LABELS[b], phys, ins.getAddress(),
                                f == null ? "?" : f.getName(),
                                f == null ? "?" : f.getEntryPoint().toString()));
                        hits++;
                    }
                }
            }
        }
        // Also sweep defined data words (pool literals not yet attached to an operand).
        DataIterator di = lst.getDefinedData(true);
        while (di.hasNext() && !monitor.isCancelled()) {
            Data d = di.next();
            Long v = dataWord(d);
            if (v == null) continue;
            long phys = v & 0x1fffffffL;
            for (int b = 0; b < BLOCKS.length; b++)
                if (phys >= BLOCKS[b][0] && phys <= BLOCKS[b][1]) {
                    Function pf = getFunctionContaining(d.getAddress());
                    if (pf == null) {
                        for (ghidra.program.model.symbol.Reference ref :
                                 currentProgram.getReferenceManager().getReferencesTo(d.getAddress())) {
                            pf = getFunctionContaining(ref.getFromAddress());
                            if (pf != null) break;
                        }
                    }
                    println(String.format("POOL  block=%s const=0x%08x at=%s fn=%s@%s",
                            LABELS[b], phys, d.getAddress(),
                            pf == null ? "?" : pf.getName(),
                            pf == null ? "?" : pf.getEntryPoint().toString()));
                    hits++;
                }
        }
        println("TOTAL hits=" + hits);
        if (hits == 0) println("FAIL: no MMIO constants found — check analysis ran");
    }

    private Long operandValue(Instruction ins, int op) {
        Object[] r = ins.getOpObjects(op);
        for (Object o : r) {
            if (o instanceof ghidra.program.model.scalar.Scalar)
                return ((ghidra.program.model.scalar.Scalar) o).getUnsignedValue();
            if (o instanceof Address)
                return ((Address) o).getOffset();
        }
        return null;
    }

    private Long dataWord(Data d) {
        try {
            if (d.getLength() == 4 && d.isDefined()) {
                Object val = d.getValue();
                if (val instanceof ghidra.program.model.scalar.Scalar)
                    return ((ghidra.program.model.scalar.Scalar) val).getUnsignedValue();
                if (val instanceof Address)
                    return ((Address) val).getOffset();
                // fall back to raw bytes (little-endian)
                return (long) (d.getInt(0)) & 0xffffffffL;
            }
        } catch (MemoryAccessException e) { /* ponytail: unreadable word => skip, not fatal */ }
        return null;
    }
}

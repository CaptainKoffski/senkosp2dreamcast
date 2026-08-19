// Static half of naomi-vs-dreamcast §8-3: does any call/jump/pool constant
// resolve into BIOS ROM (phys 0x0..0x1fffff)? bsr/bra are pc-relative +-4KB and
// can't reach BIOS from 0x8c02xxxx, so only jsr/jmp @rN (target from a pool) and
// stray pool constants in BIOS range matter. Expected result: NONE.
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;  // ponytail: wildcard covers AddressIterator missing from brief
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class ScanBiosTargets extends GhidraScript {
    private static boolean inBios(long v) { long p = v & 0x1fffffffL; return p < 0x00200000L; }

    @Override
    public void run() throws Exception {
        int hits = 0;
        // (a) resolved flow references (Ghidra follows jmp @rN when the pool value is known)
        ReferenceManager rm = currentProgram.getReferenceManager();
        AddressIterator ai = rm.getReferenceSourceIterator(currentProgram.getMemory(), true);
        while (ai.hasNext() && !monitor.isCancelled()) {
            Address src = ai.next();
            for (Reference ref : rm.getReferencesFrom(src)) {
                if (ref.getReferenceType().isFlow() && inBios(ref.getToAddress().getOffset())) {
                    println(String.format("BIOSREF from=%s to=%s type=%s",
                            src, ref.getToAddress(), ref.getReferenceType()));
                    hits++;
                }
            }
        }
        // (b) any defined 32-bit pool word pointing into BIOS (a would-be call target)
        DataIterator di = currentProgram.getListing().getDefinedData(true);
        while (di.hasNext() && !monitor.isCancelled()) {
            Data d = di.next();
            if (d.getLength() == 4 && d.isDefined()) {
                try {
                    long w = ((long) d.getInt(0)) & 0xffffffffL;
                    long p = w & 0x1fffffffL;
                    boolean isBiosVA = ((w >= 0x80000000L && w <= 0x801fffffL)    // P1 cached BIOS (phys 0x0..0x1fffff)
                                    || (w >= 0xa0000000L && w <= 0xa01fffffL))    // P2 uncached BIOS
                                    && p != 0;                                    // drop 0x80000000/0xa0000000 exact masks
                    if (isBiosVA) {
                        println(String.format("POOLBIOS at=%s val=0x%08x", d.getAddress(), w));
                        hits++;
                    }
                } catch (Exception e) { /* skip unreadable */ }
            }
        }
        println(hits == 0 ? "RESULT: NONE — no BIOS-range targets found" : "RESULT: " + hits + " candidate(s) — inspect each");
    }
}

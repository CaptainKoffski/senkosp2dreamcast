// Map a hardcoded list of addresses to their containing Ghidra functions.
// Prints fn name, entry point, and body bounds (min..max).
// Also sweeps g1dma and maple MMIO blocks and reports every containing function,
// so we can see whether the dynamic-PC functions appear among the MMIO referencers.
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryAccessException;
import java.util.*;

public class WhichFunc extends GhidraScript {

    // Addresses to map: dynamic PCs (normalised to P1 0x8c...) + static candidates.
    // senkosp Task 9 (dynamic PCs are the logged pc MINUS 2 = the actual store;
    // the fork logs Sh4cntx.pc, which ReadNexOp has already advanced past the
    // executing instruction — core/hw/sh4/interpr/sh4_interpreter.cpp `ctx->pc = addr + 2`).
    private static final long[] ADDRS = {
        0x8c027f72L, // cart DMA kick: SB_GDST store — dynamic (logged pc 0x8c027f74)
        0x8c025446L, // Maple SB_MDST store — dynamic (logged pc 0x8c025448)
        0x8c03161cL, // Maple site B — dynamic (logged pc 0x0c03161e); NOT a store
        0x8c0664b4L, // cart_fn static candidate (FindMmioXrefs, Task 4)
        0x8c0665feL, // input/eeprom_fn static candidate 1
        0x8c066964L, // input/eeprom_fn static candidate 2
    };

    // MMIO blocks to sweep for cross-check.
    private static final long[][] BLOCKS = {
        {0x005f7400L, 0x005f74ffL}, // g1dma
        {0x005f6c00L, 0x005f6cffL}, // maple
    };
    private static final String[] LABELS = {"g1dma", "maple"};

    @Override
    public void run() throws Exception {
        println("=== WhichFunc: address → function map ===");
        for (long offset : ADDRS) {
            Address a = toAddr(offset);
            Function f = getFunctionContaining(a);
            if (f == null) {
                println(String.format("ADDR 0x%08x  fn=NULL  (not in any recognised function)", offset));
            } else {
                long lo = f.getBody().getMinAddress().getOffset();
                long hi = f.getBody().getMaxAddress().getOffset();
                println(String.format("ADDR 0x%08x  fn=%s  entry=0x%08x  body=0x%08x..0x%08x",
                        offset, f.getName(), f.getEntryPoint().getOffset(), lo, hi));
            }
        }

        println("");
        println("=== MMIO block → containing functions (all hits) ===");

        // Collect unique (block, fn-entry) pairs.
        // Key: blockLabel + "@" + fnEntry; value: fn name for display.
        Map<String, String> seen = new LinkedHashMap<>();

        Listing lst = currentProgram.getListing();

        // Instruction operands.
        InstructionIterator it = lst.getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            for (int op = 0; op < ins.getNumOperands(); op++) {
                Long v = operandValue(ins, op);
                if (v == null) continue;
                long phys = v & 0x1fffffffL;
                for (int b = 0; b < BLOCKS.length; b++) {
                    if (phys >= BLOCKS[b][0] && phys <= BLOCKS[b][1]) {
                        Function f = getFunctionContaining(ins.getAddress());
                        record(seen, LABELS[b], f, ins.getAddress());
                    }
                }
            }
        }

        // Pool literals (defined data words).
        DataIterator di = lst.getDefinedData(true);
        while (di.hasNext() && !monitor.isCancelled()) {
            Data d = di.next();
            Long v = dataWord(d);
            if (v == null) continue;
            long phys = v & 0x1fffffffL;
            for (int b = 0; b < BLOCKS.length; b++) {
                if (phys >= BLOCKS[b][0] && phys <= BLOCKS[b][1]) {
                    Function pf = getFunctionContaining(d.getAddress());
                    if (pf == null) {
                        for (ghidra.program.model.symbol.Reference ref :
                                currentProgram.getReferenceManager().getReferencesTo(d.getAddress())) {
                            pf = getFunctionContaining(ref.getFromAddress());
                            if (pf != null) break;
                        }
                    }
                    record(seen, LABELS[b], pf, d.getAddress());
                }
            }
        }

        for (Map.Entry<String, String> e : seen.entrySet())
            println("MMIO " + e.getKey() + " => " + e.getValue());

        println("=== done ===");
    }

    private void record(Map<String, String> seen, String block, Function f, Address site) {
        if (f == null) {
            String k = block + "@NULL_at_" + site;
            seen.put(k, "fn=NULL site=" + site);
            return;
        }
        long lo = f.getBody().getMinAddress().getOffset();
        long hi = f.getBody().getMaxAddress().getOffset();
        String k = block + "@" + f.getEntryPoint();
        seen.put(k, String.format("fn=%s entry=0x%08x body=0x%08x..0x%08x",
                f.getName(), f.getEntryPoint().getOffset(), lo, hi));
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
                return (long) (d.getInt(0)) & 0xffffffffL;
            }
        } catch (MemoryAccessException e) { /* ponytail: skip unreadable */ }
        return null;
    }
}

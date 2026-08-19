// Scan all 4-aligned 32-bit words whose value (masked to 29-bit phys) falls in
// [lo, hi); print each with its referencing instructions and their functions.
// Complements FindMmioXrefs (operand-level): this scans raw words so it catches
// pool literals whose value is a register address even when Ghidra never turned
// them into an operand. Usage:
//   scripts/ghidra/run.sh script ListPoolWords.java 0x005f7000 0x005f7800
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

public class ListPoolWords extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long lo = Long.decode(a[0]), hi = Long.decode(a[1]);
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (!b.isInitialized()) continue;
            Address addr = b.getStart();
            while (addr.compareTo(b.getEnd()) < 0) {
                if ((addr.getOffset() & 3) == 0) {
                    long v = 0xFFFFFFFFL & currentProgram.getMemory().getInt(addr);
                    long phys = v & 0x1FFFFFFFL;
                    if (phys >= lo && phys < hi) {
                        StringBuilder sb = new StringBuilder(
                            String.format("POOLWORD addr=%s val=%08x refs=", addr, v));
                        for (Reference r : getReferencesTo(addr)) {
                            Function f = getFunctionContaining(r.getFromAddress());
                            sb.append(String.format("%s(%s) ", r.getFromAddress(),
                                f == null ? "?" : f.getName()));
                        }
                        println(sb.toString());
                    }
                }
                addr = addr.add(4);
            }
        }
    }
}

// Print every reference Ghidra resolved to each target address, with the
// referencing instruction and its containing function. Usage:
//   scripts/ghidra/run.sh script FindRefsTo.java 0x8c0ca6dc [0x8c0308e8 ...]
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FindRefsTo extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (String s : getScriptArgs()) {
            Address tgt = toAddr(Long.decode(s));
            int n = 0;
            for (Reference r : getReferencesTo(tgt)) {
                n++;
                Address from = r.getFromAddress();
                Function f = getFunctionContaining(from);
                Instruction ins = getInstructionAt(from);
                println(String.format("REF to=%s from=%s fn=%s type=%s : %s",
                    tgt, from, f == null ? "?" : f.getName() + "@" + f.getEntryPoint(),
                    r.getReferenceType(), ins == null ? "(data)" : ins.toString()));
            }
            println("REFCOUNT " + tgt + " " + n);
        }
    }
}

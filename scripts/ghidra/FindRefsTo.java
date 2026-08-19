// Print every reference Ghidra resolved to a target address, with the
// referencing instruction and its containing function. Usage:
//   scripts/ghidra/run.sh script FindRefsTo.java 0x8c0ca6dc
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FindRefsTo extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Address tgt = toAddr(Long.decode(a[0]));
        int n = 0;
        for (Reference r : getReferencesTo(tgt)) {
            n++;
            Address from = r.getFromAddress();
            Function f = getFunctionContaining(from);
            Instruction ins = getInstructionAt(from);
            println(String.format("REF from=%s fn=%s type=%s : %s",
                from, f == null ? "?" : f.getName() + "@" + f.getEntryPoint(),
                r.getReferenceType(), ins == null ? "(data)" : ins.toString()));
        }
        println("REFCOUNT " + n);
    }
}

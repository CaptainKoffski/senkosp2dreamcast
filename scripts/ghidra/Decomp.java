// Decompile the function containing each address argument, and list its callers.
// For turning a set of xref hits (e.g. register-literal referrers) into readable
// C + the call tree above them. Usage:
//   scripts/ghidra/run.sh script Decomp.java 0x8c022afa 0x8c033160 ...
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class Decomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (String s : getScriptArgs()) {
            Address a = toAddr(Long.decode(s));
            Function f = getFunctionContaining(a);
            if (f == null) { println("// NO FUNCTION at " + s); continue; }
            println("// ===== " + f.getName() + " @" + f.getEntryPoint()
                    + "  body " + f.getBody().getMinAddress() + ".." + f.getBody().getMaxAddress());
            StringBuilder cc = new StringBuilder("// callers:");
            for (Reference r : getReferencesTo(f.getEntryPoint())) {
                Function c = getFunctionContaining(r.getFromAddress());
                cc.append(" ").append(r.getFromAddress()).append("(")
                  .append(c == null ? "?" : c.getName()).append(")");
            }
            println(cc.toString());
            DecompileResults res = di.decompileFunction(f, 60, monitor);
            if (res != null && res.decompileCompleted())
                println(res.getDecompiledFunction().getC());
            else
                println("// decompile FAILED: " + (res == null ? "null" : res.getErrorMessage()));
        }
        di.dispose();
    }
}

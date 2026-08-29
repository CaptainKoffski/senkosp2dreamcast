// Map addresses (given as script args, 0x-hex) to their containing functions.
// Prints WHICHFUNC <addr> <fn name> entry=<entry> body=<min>..<max>, or "none".
// Args-driven twin of WhichFunc.java (hardcoded list) for ad-hoc queries.
//   scripts/ghidra/run.sh script WhichFuncArgs.java 0x8c03c360 0x8c03c4c0
//@category Senkosp
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class WhichFuncArgs extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (String a : getScriptArgs()) {
            Address addr = toAddr(Long.decode(a));
            Function f = getFunctionContaining(addr);
            if (f == null)
                f = getFunctionBefore(addr);   // SH-4 literal pools follow the body
            if (f == null)
                println(String.format("WHICHFUNC %s none", a));
            else
                println(String.format("WHICHFUNC %s %s entry=%s body=%s..%s",
                    a, f.getName(), f.getEntryPoint(),
                    f.getBody().getMinAddress(), f.getBody().getMaxAddress()));
        }
    }
}

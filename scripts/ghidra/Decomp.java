// Decompile the function containing each address argument, and list its callers.
// For turning a set of xref hits (e.g. register-literal referrers) into readable
// C + the call tree above them. Usage:
//   scripts/ghidra/run.sh script Decomp.java 0x8c022afa 0x8c033160 ...
//
// Address list is a CLI argument, not hardcoded (unlike WhichFunc.java): an
// address that lands outside every recognised function prints "NO FUNCTION at
// <addr>", which doubles as a cheap probe for Ghidra's function coverage.
//
// senkosp Task 4 (MMIO xref sweep) ran it three times; re-run these to
// reproduce docs/kb/boot-binary.md §MMIO xref sweep:
//   # RTC/SCIF hit functions + the cart/g1dma/maple referencers
//   ... Decomp.java 0x8c029e8c 0x8c067c82 0x8c02c584 0x8c02ca74 0x8c02c9ac \
//       0x8c02cb50 0x8c026b30 0x8c02751a 0x8c066288 0x8c066396 0x8c0664b4 \
//       0x8c0665fe 0x8c066964 0x8c0678c2 0x8c0679b4 0x8c067b48
//   # function-coverage probes across the driver block + the callers above it
//   ... Decomp.java 0x8c0663a8 0x8c0663c8 0x8c066400 0x8c066424 0x8c06642c \
//       0x8c066460 0x8c0664cc 0x8c0664e0 0x8c066500 0x8c066530 0x8c066554 \
//       0x8c066564 0x8c0665a0 0x8c0665e0 0x8c06694c 0x8c066b10 0x8c067e14 \
//       0x8c0678ee 0x8c02c5ec 0x8c02c37c 0x8c02cba6 0x8c02cbdc 0x8c029d8a \
//       0x8c029e00 0x8c068034 0x8c06773a 0x8c066146
//   # outer bounds + reachability of the RTC/SCIF callers
//   ... Decomp.java 0x8c066180 0x8c0661c0 0x8c066200 0x8c066240 0x8c066260 \
//       0x8c066270 0x8c066280 0x8c0678a0 0x8c0678f0 0x8c067900 0x8c067940 \
//       0x8c0679d0 0x8c067a00 0x8c067a80 0x8c067b00 0x8c067c20 0x8c067c60 \
//       0x8c067ca8 0x8c067d00 0x8c067d80 0x8c067e00 0x8c085b00 0x8c029a74 \
//       0x8c029a3c 0x8c02c824
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

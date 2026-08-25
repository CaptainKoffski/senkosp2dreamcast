// Print the caller tree of each target address, following both direct calls
// and computed calls through literal-pool words (a DATA ref to the target is
// treated as a pool word; instructions referencing that word count as call
// sites). Usage:
//   scripts/ghidra/run.sh script CallTree.java 0x8c035144 3
// (last arg = max depth)
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import java.util.HashSet;
import java.util.Set;

public class CallTree extends GhidraScript {
    int maxDepth;

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        maxDepth = Integer.parseInt(a[a.length - 1]);
        for (int i = 0; i < a.length - 1; i++) {
            Address tgt = toAddr(Long.decode(a[i]));
            println("TREE root " + tgt);
            walk(tgt, 1, new HashSet<Address>());
        }
    }

    void walk(Address tgt, int depth, Set<Address> seen) {
        if (depth > maxDepth || !seen.add(tgt))
            return;
        Set<Address> callers = new HashSet<>();
        for (Reference r : getReferencesTo(tgt)) {
            Address from = r.getFromAddress();
            if (r.getReferenceType().isData()) {
                // pool word: instructions referencing it are the call sites
                for (Reference r2 : getReferencesTo(from)) {
                    Function f = getFunctionContaining(r2.getFromAddress());
                    if (f != null) callers.add(f.getEntryPoint());
                }
            } else {
                Function f = getFunctionContaining(from);
                if (f != null) callers.add(f.getEntryPoint());
            }
        }
        for (Address c : callers) {
            if (c.equals(tgt)) continue;
            StringBuilder pad = new StringBuilder();
            for (int i = 0; i < depth; i++) pad.append("  ");
            println(String.format("%s%s FUN_%s", pad, "^", c));
            walk(c, depth + 1, seen);
        }
    }
}

// Refs to the TEXTURE LOAD ERROR string block (senkosp Phase 5, Task 4).
// SH-4 reaches constants via literal pools, so a string's direct refs are
// usually pool words -- when a target has no code ref, dump refs to whatever
// DOES reference it (one hop), which lands in the using function.
//
// Default target list = the error-string block verified by raw scan of
// senkosp.dat (file offset = address - 0x8c020000), plus the two anchors that
// ARE pool-referenced, kept as positive controls so a run that prints NOREF for
// everything is recognisable as a harness failure rather than a finding:
//   0x8c18880c  PAK filename pointer table (64 entries -> 0x8c18890c..0x8c188b61)
//   0x8c188760  "FONT.PAK"
// Override with args:  run.sh script FindTexErrXrefs.java 0x8c188b8a ...
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FindTexErrXrefs extends GhidraScript {
    // (address, what) -- verified by raw scan of senkosp.dat, see KB.
    private static final Object[][] TARGETS = {
        {0x8c18871bL, "\"ERROR !!\""},
        {0x8c18700aL, "\"FILE LOAD ERROR !\\nFILE NAME:%s\\n\" (copy 1)"},
        {0x8c188b6aL, "\"FILE LOAD ERROR !\\nFILE NAME:%s\\n\" (copy 2)"},
        {0x8c188b8aL, "\"TEXTURE LOAD ERROR !\\n\""},
        {0x8c188ba0L, "\"PACKTEX MALLOC FAILED %s\\n\""},
        {0x8c188bbaL, "\"PACKTEX DECODE ERROR\\n\""},
        {0x8c188bd0L, "\"PACKTEX LOAD ERROR\\n\""},
        {0x8c188be4L, "\"LOADPACKSTEX LIST MALLOC FAILED %s\\n\""},
        {0x8c188c08L, "\"LOADPACKSTEX WORK MALLOC FAILED %s\\n\""},
        {0x8c1885f0L, "\"MEMORY ALLOCATE ERROR !\\nHEAP:%p\\nSIZE:%d\\n\" (sibling: heap OOM)"},
        {0x8c188c2cL, "\"LOADPACKSTEX DECODE ERROR\\n\""},
        {0x8c188c47L, "\"LOADPACKSTEX LOAD ERROR\\n\""},
        {0x8c18880cL, "PAK filename table (positive control)"},
        {0x8c188760L, "\"FONT.PAK\" (positive control)"},
    };

    private void dumpRefs(Address a, int hop) {
        ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(a);
        boolean any = false;
        while (it.hasNext()) {
            any = true;
            Reference r = it.next();
            Address from = r.getFromAddress();
            Function f = getFunctionContaining(from);
            Instruction ins = getInstructionAt(from);
            println("  XREF hop=" + hop + " to=" + a + " from=" + from
                    + " type=" + r.getReferenceType()
                    + " fn=" + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint())
                    + " : " + (ins == null ? "(data)" : ins.toString()));
            if (f == null && hop < 2) dumpRefs(from, hop + 1);   // pool word: follow
        }
        if (!any) println("  NOREF to=" + a + " hop=" + hop);
    }

    @Override public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length > 0) {
            for (String s : args) {
                println("TARGET " + s);
                dumpRefs(toAddr(Long.decode(s)), 0);
            }
            return;
        }
        for (Object[] t : TARGETS) {
            println("TARGET " + String.format("0x%08x", (Long) t[0]) + "  " + t[1]);
            dumpRefs(toAddr((Long) t[0]), 0);
        }
    }
}

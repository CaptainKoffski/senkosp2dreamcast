// Disassembly listing for an address range. Usage:
//   scripts/ghidra/run.sh script DisasmRange.java 0x8c021000 0x8c021200 [force]
//
// Auto-analysis left spans of this image undisassembled (see
// docs/kb/boot-binary.md §MMIO xref sweep); such a span prints nothing. Pass a
// third argument to disassemble START first, which recovers the fall-through
// run. This WRITES to the project DB (monotonic: it only adds instructions);
// `run.sh import` rebuilds from scratch if it ever needs undoing.
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;

public class DisasmRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Address start = toAddr(Long.decode(a[0]));
        Address end = toAddr(Long.decode(a[1]));
        if (a.length > 2) disassemble(start);
        Instruction ins = getInstructionAt(start);
        if (ins == null) ins = getInstructionAfter(start);
        while (ins != null && ins.getAddress().compareTo(end) <= 0) {
            println(String.format("%s  %s", ins.getAddress(), ins));
            ins = ins.getNext();
        }
    }
}

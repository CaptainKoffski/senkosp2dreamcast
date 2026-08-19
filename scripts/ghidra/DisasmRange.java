// Disassembly listing for an address range. Usage:
//   scripts/ghidra/run.sh script DisasmRange.java 0x8c021000 0x8c021200
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
        Instruction ins = getInstructionAt(start);
        if (ins == null) ins = getInstructionAfter(start);
        while (ins != null && ins.getAddress().compareTo(end) <= 0) {
            println(String.format("%s  %s", ins.getAddress(), ins));
            ins = ins.getNext();
        }
    }
}

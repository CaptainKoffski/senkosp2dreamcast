// Target 4 static: walk the entry trampoline (0x8c04ae2c) to the real init and
// dump it, flagging every instruction that writes r15 (SP) with the pc-relative
// pool constant it loads (the candidate stack top). The dynamic sp= log (Task 6)
// is authoritative; this corroborates and, if the game sets SP itself, pins it.
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class DumpEntryChain extends GhidraScript {
    private static final long ENTRY = 0x8c04ae2cL;

    @Override
    public void run() throws Exception {
        Address entry = addr(ENTRY);
        new DisassembleCommand(entry, null, true).applyTo(currentProgram, monitor);
        println("== entry trampoline @ " + entry + " ==");
        Address jumpTarget = dump(entry, 8);

        if (jumpTarget == null) {
            // ponytail: Ghidra doesn't attach a flow ref to jmp @rN loaded via pool;
            // fall back: scan the trampoline for mov.l <pool>,rN and read the pool word.
            jumpTarget = resolvePoolJmp(entry, 8);
            if (jumpTarget != null)
                println("NOTE: auto-ref missing; resolved jmp target from pool memory read: " + jumpTarget);
            else
                println("NOTE: could not resolve trampoline jump target automatically — read the trampoline above by hand");
        }
        if (jumpTarget != null) {
            new DisassembleCommand(jumpTarget, null, true).applyTo(currentProgram, monitor);
            println("== init (jmp target) @ " + jumpTarget + " ==");
            dump(jumpTarget, 80);
        }
    }

    // Dump n instructions from addr; return the first resolved jmp/branch target seen.
    private Address dump(Address a, int n) {
        Instruction ins = currentProgram.getListing().getInstructionAt(a);
        Address target = null;
        for (int i = 0; ins != null && i < n; i++) {
            String flag = "";
            if (writesR15(ins)) {
                flag = "   <== writes r15 (SP)";
                for (Reference r : ins.getReferencesFrom())
                    if (r.getReferenceType().isData()) {
                        try {
                            long poolVal = ((long) currentProgram.getMemory().getInt(r.getToAddress())) & 0xffffffffL;
                            flag += String.format(", loads 0x%08x", poolVal);
                        } catch (Exception e) { /* no pool word readable */ }
                        break;
                    }
            }
            println(String.format("%s  %-28s%s", ins.getAddress(), ins.toString(), flag));
            if (target == null)
                for (Reference r : ins.getReferencesFrom())
                    if (r.getReferenceType().isJump() || r.getReferenceType().isCall())
                        target = r.getToAddress();
            ins = ins.getNext();
        }
        return target;
    }

    // Fallback: walk n instructions from a, find jmp @rN, then find the mov.l <pool>,rN
    // that loaded it, and return the 32-bit pool value. Matches on register name.
    private Address resolvePoolJmp(Address a, int n) {
        // Pass 1: find jmp and the register it uses
        Instruction ins = currentProgram.getListing().getInstructionAt(a);
        String jmpReg = null;
        for (int i = 0; ins != null && i < n; i++) {
            if (ins.getMnemonicString().equalsIgnoreCase("jmp")) {
                for (int op = 0; op < ins.getNumOperands(); op++)
                    for (Object o : ins.getOpObjects(op))
                        if (o instanceof ghidra.program.model.lang.Register)
                            jmpReg = ((ghidra.program.model.lang.Register) o).getName();
                break;
            }
            ins = ins.getNext();
        }
        if (jmpReg == null) return null;
        // Pass 2: find the LAST mov.l <pool>,<jmpReg> before the jmp (handles two loads to same reg)
        ins = currentProgram.getListing().getInstructionAt(a);
        Address jmpAddr = null;
        // locate jmp address first for comparison
        Instruction tmp = ins;
        for (int i = 0; tmp != null && i < n; i++) {
            if (tmp.getMnemonicString().equalsIgnoreCase("jmp")) { jmpAddr = tmp.getAddress(); break; }
            tmp = tmp.getNext();
        }
        Instruction lastMovL = null;
        for (int i = 0; ins != null && i < n; i++) {
            if (jmpAddr != null && ins.getAddress().compareTo(jmpAddr) >= 0) break;
            if (ins.getMnemonicString().equalsIgnoreCase("mov.l")) {
                int lastOp = ins.getNumOperands() - 1;
                boolean destMatch = false;
                for (Object o : ins.getOpObjects(lastOp))
                    if (o instanceof ghidra.program.model.lang.Register
                            && ((ghidra.program.model.lang.Register) o).getName().equalsIgnoreCase(jmpReg))
                        destMatch = true;
                if (destMatch) lastMovL = ins;
            }
            ins = ins.getNext();
        }
        if (lastMovL != null)
            for (Reference r : lastMovL.getReferencesFrom())
                if (r.getReferenceType().isData()) {
                    try {
                        int w = currentProgram.getMemory().getInt(r.getToAddress());
                        return addr(((long) w) & 0xffffffffL);
                    } catch (Exception e) { /* skip */ }
                }
        return null;
    }

    private boolean writesR15(Instruction ins) {
        for (int op = 0; op < ins.getNumOperands(); op++) {
            for (Object o : ins.getOpObjects(op)) {
                if (o instanceof ghidra.program.model.lang.Register
                        && ((ghidra.program.model.lang.Register) o).getName().equalsIgnoreCase("r15"))
                    return true;
            }
        }
        return false;
    }

    private Address addr(long v) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v);
    }
}

// Target 7 static (senkosp): walk the entry chain from the Naomi header entrypoint
// (0x8c021000) to the real init and dump it, flagging every instruction that writes
// r15 (SP) with the pc-relative pool constant it loads (the candidate stack top).
// Unlike Cleopatra's bare `jmp @rN` trampoline, senkosp's entry is a real function:
// its first pool-loaded hop is a `jsr` that RETURNS, so the chain continues inside
// the entry itself. Hence the wide entry window plus explicit per-hop resolution.
// The dynamic sp= log is authoritative; this corroborates and, since the game does
// set SP itself, pins the constant and its patch site.
//@category Cleopatra
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class DumpEntryChain extends GhidraScript {
    private static final long ENTRY = 0x8c021000L;
    // senkosp's entry is a real function (the pool-loaded jsr returns), so the entry
    // window has to be wide enough to cover the post-rts continuation, not just a hop.
    private static final int ENTRY_INSNS = 64;
    private static final int INIT_INSNS = 80;
    // Sites in the entry function that hop through a literal pool (jsr @rN, target
    // OR'd with 0xa0000000 for the P2/uncached mirror). Ghidra's auto-analysis never
    // follows these, so each is resolved by reading the pool word and dumped.
    private static final long[] HOP_SITES = { 0x8c021000L, 0x8c02103cL };

    @Override
    public void run() throws Exception {
        Address entry = addr(ENTRY);
        new DisassembleCommand(entry, null, true).applyTo(currentProgram, monitor);
        println("== entry @ " + entry + " ==");
        dump(entry, ENTRY_INSNS);
        // ponytail: Ghidra attaches no flow ref to jmp/jsr @rN loaded via pool, so each
        // hop target comes from reading the pool word the register was loaded from.
        for (long site : HOP_SITES) {
            Address hop = resolvePoolJmp(addr(site), 8);
            if (hop == null) {
                println(String.format("NOTE: no pool-loaded hop resolved at 0x%08x — read the entry above by hand", site));
                continue;
            }
            println(String.format("== hop from 0x%08x -> %s (resolved via pool memory read) ==", site, hop));
            new DisassembleCommand(hop, null, true).applyTo(currentProgram, monitor);
            dump(hop, INIT_INSNS);
        }
    }

    // Dump n instructions from addr, flagging r15 (SP) writes with their pool constant.
    private void dump(Address a, int n) {
        Instruction ins = currentProgram.getListing().getInstructionAt(a);
        for (int i = 0; ins != null && i < n; i++) {
            String flag = "";
            if (writesR15(ins)) {
                flag = "   <== writes r15 (SP)";
                // The constant hangs off this instruction (mov.l @r0,r15, via constant
                // propagation) or off the preceding pool load (mov.l <pool>,r0; mov r0,r15).
                String pool = poolValue(ins);
                if (pool == null) pool = poolValue(ins.getPrevious());
                if (pool != null) flag += ", loads " + pool;
            }
            println(String.format("%s  %-28s%s", ins.getAddress(), ins.toString(), flag));
            ins = ins.getNext();
        }
    }

    // senkosp's entry is jsr @rN, not Cleopatra's jmp @rN — treat both as the chain hop.
    private boolean isIndirectHop(Instruction ins) {
        String m = ins.getMnemonicString();
        return m.equalsIgnoreCase("jmp") || m.equalsIgnoreCase("jsr");
    }

    // Fallback: walk n instructions from a, find jmp/jsr @rN, then find the mov.l <pool>,rN
    // that loaded it, and return the 32-bit pool value. Matches on register name.
    private Address resolvePoolJmp(Address a, int n) {
        // Pass 1: find jmp/jsr and the register it uses
        Instruction ins = currentProgram.getListing().getInstructionAt(a);
        String jmpReg = null;
        for (int i = 0; ins != null && i < n; i++) {
            if (isIndirectHop(ins)) {
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
            if (isIndirectHop(tmp)) { jmpAddr = tmp.getAddress(); break; }
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

    // Read the 32-bit word this instruction's first data reference points at, and say
    // where it came from, so the KB can cite the exact patch site.
    private String poolValue(Instruction ins) {
        if (ins == null) return null;
        for (Reference r : ins.getReferencesFrom())
            if (r.getReferenceType().isData()) {
                try {
                    long v = ((long) currentProgram.getMemory().getInt(r.getToAddress())) & 0xffffffffL;
                    return String.format("0x%08x (from %s)", v, r.getToAddress());
                } catch (Exception e) { return null; }
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

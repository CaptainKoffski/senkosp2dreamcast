// Phase 3 target 3: candidate provenance sites for above-cap placement.
// Scans every 4-byte-aligned LE word of the imported boot image for values
// resolving (29-bit phys) into one of the 5 above-16m main-RAM corridors
// (docs/kb/cart-streaming-map.md) or above-8m VRAM, printing address, value,
// containing function (or "data"). Keep RANGES in sync with
// scripts/scan_dat_constants.py.
//@category Senkosp
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.*;

public class ScanPlacementConstants extends GhidraScript {
    private static final long[][] RANGES = {
        {0x0d244c20L, 0x0dd73e00L}, // corridor 1 (main off 0x1244c20-0x1d73e00)
        {0x0dd7d020L, 0x0dd92020L}, // corridor 2
        {0x0ddc2960L, 0x0dde3960L}, // corridor 3
        {0x0de4dbe0L, 0x0de8b480L}, // corridor 4
        {0x0dfe6d20L, 0x0dfe7520L}, // corridor 5
        {0x04800000L, 0x04ffffffL}, // VRAM above-8m, 64-bit window
        {0x05800000L, 0x05ffffffL}, // VRAM above-8m, 32-bit window
    };
    private static final String[] LABELS = {
        "corridor1", "corridor2", "corridor3", "corridor4", "corridor5",
        "vram64", "vram32"};

    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock blk = mem.getBlocks()[0];
        int hits = 0;
        for (Address a = blk.getStart(); a.compareTo(blk.getEnd().subtract(3)) <= 0; a = a.add(4)) {
            long v = ((long) mem.getInt(a)) & 0xffffffffL;
            long phys = v & 0x1fffffffL;
            for (int r = 0; r < RANGES.length; r++) {
                if (phys >= RANGES[r][0] && phys <= RANGES[r][1]) {
                    Function f = getFunctionContaining(a);
                    println(String.format("PLACE range=%s word=0x%08x at=%s fn=%s",
                            LABELS[r], v, a,
                            f == null ? "data" : f.getName() + "@" + f.getEntryPoint()));
                    hits++;
                }
            }
        }
        println("PLACE-TOTAL hits=" + hits);
    }
}

// Read-only instruction listing for the pinned MAP001 room reverse engineering.
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.address.Address;
import java.io.PrintWriter;

public class ExportRoomDisassembly extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Output path required");
        PseudoDisassembler decoder = new PseudoDisassembler(currentProgram);
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            for (long offset = 0; offset + 1 <= currentProgram.getMaxAddress().getOffset(); offset += 2) {
                Address address = toAddr(offset);
                try {
                    PseudoInstruction instruction = decoder.disassemble(address);
                    out.printf("%08x %04x %s%n", offset, getShort(address) & 0xffff,
                        instruction == null ? "<invalid>" : instruction.toString());
                } catch (Exception e) {
                    out.printf("%08x %04x <undecodable>%n", offset, getShort(address) & 0xffff);
                }
            }
        }
    }
}

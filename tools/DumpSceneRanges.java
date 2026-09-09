import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Instruction;
import java.io.PrintWriter;

public class DumpSceneRanges extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (!currentProgram.getName().equals("TWN.BIN") || currentProgram.getImageBase().getOffset()!=0
                || args.length<3 || args.length%2!=1) {
            throw new IllegalArgumentException("Expected zero-based TWN.BIN and output/start/end arguments");
        }
        try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
            for (int i=1;i<args.length;i+=2) {
                long start=Long.decode(args[i]), end=Long.decode(args[i+1]);
                disassemble(toAddr(start));
                for (long p=start;p<end;p+=2) {
                    Instruction instruction=getInstructionAt(toAddr(p));
                    out.printf("%05X %04X %s%n",p,getShort(toAddr(p))&65535,
                        instruction==null?"[undecoded]":instruction.toString());
                }
            }
        }
    }
}

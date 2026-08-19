// Headless postScript: export currentProgram to Ghidra Program XML.
// Produces <out>.xml (markup) + <out>.bytes (raw image) side by side.
import ghidra.app.script.GhidraScript;
import ghidra.app.util.exporter.XmlExporter;
import java.io.File;

public class ExportToXML extends GhidraScript {
    @Override
    public void run() throws Exception {
        File out = new File(getScriptArgs()[0]);
        XmlExporter exporter = new XmlExporter();
        boolean ok = exporter.export(out, currentProgram, null, monitor);
        println("EXPORT_RESULT ok=" + ok + " file=" + out.getAbsolutePath());
        if (!ok) {
            println("EXPORT_LOG " + exporter.getMessageLog().toString());
        }
    }
}

using System;
using System.IO;
using System.Text.Json;
using System.Linq;
using System.Collections.Generic;
using Ao.SourceContracts;

internal static class Program
{
    static int checks;
    static void Require(bool value, string reason)
    { checks++; if (!value) throw new Exception(reason); }
    static void Reject(Action action)
    {
        checks++;
        try { action(); } catch (InvalidDataException) { return; }
        throw new Exception("Expected invalid source to be rejected");
    }
    static void Main(string[] args)
    {
        string root = Path.GetFullPath(args[0]);
        string local = Path.Combine(root, "unity-remake/Assets/StreamingAssets/SourceLocal");
        string manifest = Path.Combine(local, "unity-source-manifest.json");
        using var document = JsonDocument.Parse(File.ReadAllBytes(manifest));
        var approved = new List<SourceIdentity>();
        foreach (var file in document.RootElement.GetProperty("files").EnumerateObject())
            approved.Add(new SourceIdentity(file.Name, file.Value.GetProperty("bytes").GetInt64(), file.Value.GetProperty("sha256").GetString()));
        approved.Add(new SourceIdentity("unity-source-manifest.json",new FileInfo(manifest).Length,SourceGuard.Hash(File.ReadAllBytes(manifest))));
        Require(SourceGuard.Load(local, approved,editorMetadata:true).Count == 7, "Incorrect local source closure");
        Require(approved.All(x => !x.Path.Contains("reference-")), "Golden replay leaked into runtime");
        string temp = Path.Combine(root,"build/unity-source-negative-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        byte[] raw = { 0x80, 0x01, 0xff, 0xff };
        File.WriteAllBytes(Path.Combine(temp,"actor.bin"),raw);
        var one = new[]{new SourceIdentity("actor.bin",raw.Length,SourceGuard.Hash(raw))};
        Require(SourceGuard.Load(temp,one).Count == 1,"Valid identity rejected");
        File.WriteAllBytes(Path.Combine(temp,"actor.bin"),new byte[]{0x80,0,0xff,0xff});
        Reject(()=>SourceGuard.Load(temp,one));
        File.WriteAllBytes(Path.Combine(temp,"actor.bin"),raw);
        File.WriteAllText(Path.Combine(temp,"unapproved.json"),"{}");
        Reject(()=>SourceGuard.Load(temp,one));
        foreach (string name in new[]{"../actor.bin","/absolute","C:/x","a\\b","a//b"})
            Reject(()=>SourceGuard.SafePath(temp,name));
        Require(SourceInteger.Signed16(65535)==-1,"Signed wrap");
        Require(SourceInteger.Signed16(32768)==-32768,"Signed boundary");
        Require(SourceInteger.Divide16(-15)==0 && SourceInteger.Divide16(-17)==-1,"SH2 truncation differs");
        SourceInteger.PutWord(raw,0,65536+3);
        Require(SourceInteger.Word(raw,0)==3,"Word write must wrap");
        string report=Path.Combine(root,"reports/unity/u1-csharp-source-guard.json");
        File.WriteAllText(report,JsonSerializer.Serialize(new{passed=true,checks,
            source_files=approved.Count,gameplay_port_tested=false,performance_tested=false,
            scope="Source closure, byte hashes, path rejection and SH2 integer helpers only"},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine(File.ReadAllText(report));
        MovementTests.Run(root);
        EquipmentTests.Run(root);
    }
}

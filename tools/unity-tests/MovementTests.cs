using System;
using System.IO;
using System.Text.Json;
using System.Linq;
using System.Collections.Generic;
using Ao.SourceContracts;
using static Ao.SourceContracts.SourceInteger;

internal static class MovementTests
{
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    public static void Run(string root)
    {
        string scene=Path.Combine(root,"exploration-demo/generated/scene");
        using var profile=JsonDocument.Parse(File.ReadAllBytes(Path.Combine(scene,"profile.json")));
        using var traces=JsonDocument.Parse(File.ReadAllBytes(Path.Combine(scene,"traces.json")));
        var fields=profile.RootElement.GetProperty("comparison_fields").EnumerateObject().ToArray();
        var verified=profile.RootElement.GetProperty("verified_query_indices").EnumerateArray().Select(x=>x.GetInt32()).ToHashSet();
        byte[] flags=File.ReadAllBytes(Path.Combine(scene,"flags.bin"));
        Check(SourceGuard.Hash(flags)=="78863dedbf02a07158821486a059af56f31a0b18d11a9eee6a7986dd10943e5b","Unapproved source flags");
        int updates=0,routes=0,checks=0;
        byte[] replay=File.ReadAllBytes(Path.Combine(root,"reports/exploration/player-replay-fixtures.json"));
        Check(SourceGuard.Hash(replay)=="1ec29b8be515f381727ab64024d62d418a176724b45d2046fa0430181a1976a4","Full movement fixture changed");
        using var all = JsonDocument.Parse(replay);
        foreach(var route in all.RootElement.GetProperty("traces").EnumerateArray())
        {
            routes++;var state=new byte[112];
            foreach(var field in fields)
            {
                int offset=field.Value.GetProperty("offset").GetInt32(), size=field.Value.GetProperty("bytes").GetInt32();
                int value=route.GetProperty("initial_state").GetProperty(field.Name).GetInt32();
                if(size==1)state[offset]=(byte)value;else PutWord(state,offset,value);
            }
            foreach(var row in route.GetProperty("updates").EnumerateArray())
            {
                byte[] before=(byte[])state.Clone();
                var next=Movement.Step(state,row.GetProperty("game_pad_word").GetInt32(),flags,verified,out bool outside);
                Check(state.SequenceEqual(before),"Movement mutated caller state");
                Check(!outside,"Verified trace rejected");
                foreach(var field in fields)
                {
                    int offset=field.Value.GetProperty("offset").GetInt32(),size=field.Value.GetProperty("bytes").GetInt32();
                    int actual=size==1?next[offset]:Word(next,offset);
                    Check(actual==row.GetProperty("expected").GetProperty(field.Name).GetInt32(),
                        $"Movement differs: route {routes} frame {row.GetProperty("frame")} {field.Name} {actual}");
                    checks++;
                }
                state=next;updates++;
            }
            var rejected=Movement.Step(state,0,flags,new HashSet<int>(),out bool boundary);
            Check(boundary && rejected.SequenceEqual(state),"Outside-domain update was not preserved");
        }
        Check(updates==1680,"Full source route coverage changed");
        string report=JsonSerializer.Serialize(new{passed=true,routes,updates,checks,
            continuous_from_initial=true,post_initial_state_injection=false,
            scope="Four movement routes, three source repeats each",
            full_equipment_core_tested=false,performance_tested=false},new JsonSerializerOptions{WriteIndented=true});
        File.WriteAllText(Path.Combine(root,"reports/unity/u2-movement-csharp.json"),report);
        Console.WriteLine(report);
    }
}

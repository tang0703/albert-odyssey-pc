using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Ao.SourceContracts;

internal static class EquipmentTests
{
    static int updates,checks;
    static void Check(bool ok,string reason){checks++;if(!ok)throw new Exception(reason);}
    static void Compare(JObject actual,JObject expected,string route)
    {
        foreach(var property in expected.Properties())
            Check(JToken.DeepEquals(actual[property.Name],property.Value),route+" "+property.Name+"\nActual: "+actual[property.Name]+"\nExpected: "+property.Value);
        Check(actual.Properties().Count()==expected.Properties().Count(),"Unexpected state fields");
    }
    public static void Run(string root, bool unity = false)
    {
        string folder=Path.Combine(root,"exploration-demo/generated/equipment");
        string runtime=Path.Combine(root,"unity-remake/Assets/StreamingAssets/SourceLocal");
        var manifest=JObject.Parse(File.ReadAllText(Path.Combine(folder,"package.json")));
        var routes=new JArray();
        foreach(var route in new[]{"equip-stairs","remove-stairs","reequip-stairs","unowned","cancel-owned","hold-equip","cancel-selection"})
        {
            byte[] raw=File.ReadAllBytes(Path.Combine(folder,"reference-"+route+".json"));
            Check(SourceGuard.Hash(raw)==(string)manifest["files"]["reference-"+route+".json"]["sha256"],"Reference changed");
            var fixture=JObject.Parse(System.Text.Encoding.UTF8.GetString(raw));
            var core=new EquipmentCore(runtime,editorMetadata:true);var initial=core.Snapshot();
            foreach(var row in fixture["updates"])
            {
                foreach(var action in row["equipment"])Check(core.Equipment((string)action).Ok,"Equipment action rejected");
                var input=row["input"];
                var result=core.Step((int)input["pad"],new DeviceSignals((int)input["resource_loaded"],(int)input["resource_playing"],(bool)input["text_active"]),(int)input["pressed"]);
                string context=route+" update "+input["update"];
                Check(result.Ok&&result.Applied,context+" rejected "+result.Reason);
                Compare(core.Snapshot(),(JObject)row["expected"],context);updates++;
            }
            if(fixture["terminal"].Type!=JTokenType.Null)
            {
                var result=core.Step((int)fixture["terminal"]["pad"],new DeviceSignals(0,0,false));
                Check(result.Ok&&result.Applied,"Terminal boundary rejected");
                Compare(core.Snapshot(),(JObject)fixture["terminal"]["expected"],route+" boundary");
                var frozen=core.Snapshot();Check(!core.Step(0,new DeviceSignals(0,0,false)).Applied,"Boundary advanced");
                Compare(core.Snapshot(),frozen,route+" frozen");Check(!core.Equipment("remove").Ok,"Boundary accepted equipment");
            }
            core.Reset();Compare(core.Snapshot(),initial,route+" reset");
            Check(!core.Equipment("equip").Applied&&!core.Equipment("remove").Applied,"Unowned item mutated");
            Check(!core.Equipment("unknown").Ok,"Unknown operation accepted");
            Check(!core.Step(0,new DeviceSignals(3,0,false)).Ok,"Invalid device response accepted");
            Compare(core.Snapshot(),initial,route+" invalid operations");
            routes.Add(new JObject{["route"]=route,["updates"]=fixture["updates"].Count()});
        }
        Check(updates==3685,"Equipment coverage changed");
        var report=new JObject{["passed"]=true,["updates"]=updates,["checks"]=checks,["routes"]=routes,
            ["continuous_from_initial"]=true,["post_initial_state_injection"]=false,["unity_runtime_tested"]=unity,["performance_tested"]=false};
        File.WriteAllText(Path.Combine(root,unity ? "reports/unity/u2-equipment-unity.json" : "reports/unity/u2-equipment-csharp.json"),report.ToString(Formatting.Indented));
        Console.WriteLine(report.ToString(Formatting.Indented));
    }
}

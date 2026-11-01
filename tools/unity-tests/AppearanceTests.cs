using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using Ao.SourceContracts;
using Newtonsoft.Json.Linq;

static class AppearanceTests
{
    static void Require(bool ok,string reason){if(!ok)throw new Exception(reason);}
    static byte[] Raw(JToken token){string text=(string)token;return Enumerable.Range(0,text.Length/2).Select(i=>Convert.ToByte(text.Substring(i*2,2),16)).ToArray();}
    public static void Main(string[] args)
    {
        string root=args[0],sources=Path.Combine(root,"exploration-demo/generated/equipment");
        int samples=0;var clips=new HashSet<string>();var phases=new HashSet<float>();
        foreach(string route in new[]{"equip-stairs","remove-stairs","reequip-stairs","unowned","cancel-owned","hold-equip","cancel-selection"})
        {
            var fixture=JObject.Parse(File.ReadAllText(Path.Combine(sources,"reference-"+route+".json")));
            foreach(bool marker in new[]{false,true})
            {
                var core=new EquipmentCore(Path.Combine(root,"unity-remake/Assets/StreamingAssets/SourceLocal"),true);
                foreach(var row in fixture["updates"])
                {
                    foreach(var action in row["equipment"])Require(core.Equipment((string)action).Ok,"Equipment request rejected");
                    var input=row["input"];
                    Require(core.Step((int)input["pad"],new DeviceSignals((int)input["resource_loaded"],(int)input["resource_playing"],(bool)input["text_active"]),(int)input["pressed"]).Ok,"Core rejected");
                    var state=core.Snapshot();Require(JToken.DeepEquals(state,row["expected"]),"Continuous state differs");
                    byte[] actor=Raw(state["player"]),before=(byte[])actor.Clone();
                    var pose=AppearancePose.Select(actor,(int)state["update"]);
                    Require(actor.SequenceEqual(before)&&JToken.DeepEquals(state,core.Snapshot()),"Presentation mutated source");
                    Require(pose.Phase>=0&&pose.Phase<1,"Invalid phase");
                    clips.Add(pose.Clip);if(pose.Clip=="walk")phases.Add(pose.Phase);
                    var repeated=AppearancePose.Select(actor,(int)state["update"]);
                    Require(repeated.Clip==pose.Clip&&repeated.Phase==pose.Phase,"Paused sample not stable");samples++;
                }
            }
        }
        Require(samples==7370,"Coverage changed");Require(clips.Count==6,"Missing required clip");Require(phases.Count==40,"Source gait phase coverage incomplete");
        var invalid=new byte[112];SourceInteger.PutWord(invalid,54,23);bool rejected=false;
        try{AppearancePose.Select(invalid,0);}catch(InvalidDataException){rejected=true;}Require(rejected,"Unknown required pose accepted");
        File.WriteAllText(Path.Combine(root,"reports/unity/u4-appearance-core.json"),new JObject{["passed"]=true,["samples"]=samples,["clips"]=new JArray(clips),["walk_phases"]=phases.Count,["continuous_from_initial"]=true,["post_initial_state_injection"]=false,["performance_tested"]=false}.ToString());
        Console.WriteLine("Appearance source checks passed: "+samples);
    }
}

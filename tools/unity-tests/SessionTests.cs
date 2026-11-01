using System;
using System.IO;
using Newtonsoft.Json.Linq;
using Ao.SourceContracts;

internal static class SessionTests
{
    static int checks;
    static void Check(bool value,string reason){checks++;if(!value)throw new Exception(reason);}
    public static void Run(string root)
    {
        var session=new RoomSession(new EquipmentCore(Path.Combine(root,"unity-remake/Assets/StreamingAssets/SourceLocal"),true));
        session.DeviceRequest=(type,id,generation)=>{if(type=="load_original_resource")session.SetDeviceResponse(generation,true,false);if(type=="play_original_resource")session.SetDeviceResponse(generation,true,true);};
        var initial=session.Core.Snapshot();
        JObject timingExpected=null;
        foreach(int fps in new[]{30,60,120})
        {
            var clock=new LogicClock();var timed=new EquipmentCore(Path.Combine(root,"unity-remake/Assets/StreamingAssets/SourceLocal"),true);
            int ticks=0;
            for(int frame=0;frame<fps*3;frame++)
            {
                clock.Push(1.0/fps);
                while(clock.Take()){var result=timed.Step(ticks<20?0x2000:0,new DeviceSignals(0,0,false));Check(result.Ok,"Synthetic timing rejected");ticks++;}
            }
            Check(ticks==179,"Synthetic tick count differs");
            if(timingExpected==null)timingExpected=timed.Snapshot();else Check(JToken.DeepEquals(timingExpected,timed.Snapshot()),"30/60/120 partitions differ");
        }
        session.TogglePanel();Check(session.Panel,"Unowned panel inaccessible");session.SelectOption(0);Check(JToken.DeepEquals(initial,session.Core.Snapshot()),"Unowned equip changed state");session.Tick(0x2000);Check(JToken.DeepEquals(initial,session.Core.Snapshot()),"Panel advanced room");session.TogglePanel();
        session.FocusLost();session.Tick(0x2000);Check(JToken.DeepEquals(initial,session.Core.Snapshot()),"Focus loss advanced core");
        session.Tick(0,true,true);Check(JToken.DeepEquals(initial,session.Core.Snapshot()),"Multiple directions advanced core");
        session.Tick(0,false,true);Check((int)session.Core.Snapshot()["update"]==1,"Single step failed");session.Reset();
        int epoch=session.Generation;session.Reset();session.SetDeviceResponse(epoch,true,true);Check(!session.Loaded&&!session.Started,"Stale response accepted");
        // Normal PC navigation and fresh confirmation edges, no replay expected states.
        int navigation=0,pageAge=0,stairs=0;bool equipped=false,requested=false;int dialogueCount=0;
        for(int i=0;i<2500&&!session.Boundary;i++)
        {
            int pad=0;var state=session.Core.Snapshot();
            if(session.DialogueActive){pageAge++;if(pageAge==60){session.ConfirmEdge();pageAge=0;dialogueCount++;}}
            else if(!requested){navigation++;pad=navigation<=4?0:navigation<=34?0x2000:navigation<=53?0x8000:navigation<=63?0x2000:0;if(navigation==69){session.ConfirmEdge();requested=true;}}
            else if(session.CanAct&&(int)state["item_count"]==1&&!equipped)
            {
                session.TogglePanel();Check(session.Panel,"Owned panel inaccessible");session.SelectOption(0);
                Check((int)session.Core.Snapshot()["weapon"]==27&&(int)session.Core.Snapshot()["item_count"]==0,"Equip state");
                session.SelectOption(0);Check((int)session.Core.Snapshot()["item_count"]==0,"Duplicate item");
                session.SelectOption(1);Check((int)session.Core.Snapshot()["item_count"]==1,"Remove state");session.SelectOption(0);
                session.TogglePanel();equipped=true;
            }
            else if(equipped&&session.CanAct){stairs++;pad=stairs<=9?0x1000:stairs<=61?0x8000:stairs<=121?0:stairs<=137?0x1000:stairs<=157?0x8000:stairs<=185?0x2000:0;}
            session.Tick(pad);Check(session.Error=="",session.Error);
        }
        Check(equipped&&session.Boundary&&dialogueCount>=1,"PC flow did not reach source transition boundary");
        session.TogglePanel();Check(!session.Panel,"Boundary panel opened");session.Reset();Check(JToken.DeepEquals(initial,session.Core.Snapshot()),"Full reset differs");
        var report=new JObject{["passed"]=true,["checks"]=checks,["device_responses"]="explicit test doubles; live audio validated separately",["performance_tested"]=false};
        File.WriteAllText(Path.Combine(root,"reports/unity/u2-session-csharp.json"),report.ToString());Console.WriteLine(report);
    }
}

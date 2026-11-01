using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Ao.SourceContracts
{
    // PC modal-input/presentation adapter. Device callbacks are explicit inputs.
    // Golden source states are never consumed here.
    public sealed class RoomSession
    {
        public readonly EquipmentCore Core;
        readonly Queue<JObject> queue=new Queue<JObject>();
        public JObject Shown {get;private set;}
        public bool Paused {get;private set;}
        public bool Panel {get;private set;}
        public bool Diagnostic {get;private set;}
        public bool Marker {get;private set;}
        public bool DialogueActive=>Page>=0;
        public bool Closing {get;private set;}
        public int Page {get;private set;}=-1;
        public int Selection {get;private set;}
        public int Generation {get;private set;}
        public int Confirmations {get;private set;}
        public JArray Pages {get;private set;}=new JArray();
        public string DialogueId {get;private set;}="";
        public string Notice {get;private set;}="";
        public string Error {get;private set;}="";
        public bool Boundary=>Shown["transition_pending"].Value<bool>();
        public bool Loaded {get;private set;}
        public bool Started {get;private set;}
        public Action<string,string,int> DeviceRequest;
        bool confirm,interact;
        int boundaryDrain;
        public int InputEpoch {get;private set;}
        public RoomSession(EquipmentCore core){Core=core;Reset();}
        static bool Active(JToken slot)=>slot!=null&&slot.Type!=JTokenType.Null&&slot["active"].Value<bool>();
        public bool CanAct
        {
            get {var s=Core.Snapshot();return !Paused&&!DialogueActive&&!Closing&&!s["transition_pending"].Value<bool>()&&
                s["disabled"].Value<int>()==0&&Shown["disabled"].Value<int>()==0&&!Active(s["root"])&&Error=="";}
        }
        public void ClearInput(){confirm=false;interact=false;InputEpoch++;}
        public void Reset()
        {
            Generation++;Core.Reset();queue.Clear();Shown=Core.Snapshot();
            for(int i=0;i<3;i++)queue.Enqueue((JObject)Shown.DeepClone());
            Paused=false;Panel=false;Page=-1;Pages=new JArray();DialogueId="";Closing=false;
            Loaded=false;Started=false;Confirmations=0;boundaryDrain=0;Error="";Notice="";ClearInput();
            DeviceRequest?.Invoke("stop","",Generation);
        }
        public void SetDeviceResponse(int generation,bool loaded,bool started)
        {if(generation!=Generation)return;Loaded=loaded;Started=started;}
        public void FocusLost(){Paused=true;ClearInput();}
        public void TogglePause(){Paused=!Paused;ClearInput();}
        public void ToggleMarker(){Marker=!Marker;}
        public void ToggleDiagnostic(){Diagnostic=!Diagnostic;}
        public void TogglePanel()
        {
            if(Panel){Panel=false;ClearInput();return;}
            if(!CanAct)return;
            Panel=true;var s=Core.Snapshot();Selection=(int)s["weapon"]==27?1:(int)s["item_count"]==1?0:2;ClearInput();
        }
        public bool OptionAllowed(int option)
        {
            var s=Core.Snapshot();return option==2||(option==0&&(int)s["weapon"]!=27&&(int)s["item_count"]==1)||(option==1&&(int)s["weapon"]==27);
        }
        public void NavigatePanel(int delta)
        {if(!Panel||Paused)return;for(int i=0;i<3;i++){Selection=(Selection+delta+3)%3;if(OptionAllowed(Selection))break;}}
        public void SelectOption(int option)
        {
            if(!Panel||!CanAct||!OptionAllowed(option))return;
            Selection=option;if(option==2){TogglePanel();return;}
            var result=Core.Equipment(option==0?"equip":"remove");
            if(!result.Ok){Error=result.Reason;Paused=true;return;}
            foreach(var sample in queue)CopyEquipment(sample);
            CopyEquipment(Shown);Selection=(int)Shown["weapon"]==27?1:0;ClearInput();
        }
        void CopyEquipment(JObject target)
        {var s=Core.Snapshot();foreach(string key in new[]{"weapon","attack","story","item_count"})target[key]=s[key].DeepClone();}
        public void ConfirmEdge()
        {
            if(Paused||Boundary)return;
            if(Panel){SelectOption(Selection);return;}
            if(DialogueActive)confirm=true;else if(CanAct)interact=true;
        }
        public void Tick(int pad,bool multipleDirections=false,bool singleStep=false)
        {
            if(Error!=""||Panel||(Paused&&!singleStep))return;
            if(multipleDirections){confirm=false;interact=false;Notice="同時多方向：凍結更新";return;}
            if(Core.Snapshot()["transition_pending"].Value<bool>())
            {
                if(boundaryDrain<3){queue.Enqueue(Core.Snapshot());Shown=queue.Dequeue();boundaryDrain++;}
                Notice="測試邊界：已提出轉場，下一房間未載入。按 R 重設。";ClearInput();return;
            }
            int pressed=interact?0x0200:0;interact=false;
            if(confirm&&DialogueActive){Page++;Confirmations++;if(Page==Pages.Count){Page=-1;Closing=true;}}
            confirm=false;
            if(Closing&&Shown["child"].Type!=JTokenType.Null&&!Active(Shown["child"]))Closing=false;
            var result=Core.Step(pad,new DeviceSignals(Loaded?1:0,Started?1:0,DialogueActive||Closing),pressed);
            if(!result.Ok){Error=result.Reason;Paused=true;return;}
            if(!result.Applied){Notice="測試邊界：未驗證區域";return;}
            var state=Core.Snapshot();Notice="";
            foreach(var request in state["requests"])
            {
                string type=(string)request["type"],id=(string)request["id"]??"";
                switch(type)
                {
                    case "load_original_resource":Loaded=false;Started=false;DeviceRequest?.Invoke(type,id,Generation);break;
                    case "play_original_resource":DeviceRequest?.Invoke(type,id,Generation);break;
                    case "dialogue":DialogueId=id;Pages=Core.DialoguePages(id);Page=0;ClearInput();break;
                    case "source_text_layout":break;
                    default:Error="Unknown presentation request: "+type;Paused=true;return;
                }
            }
            queue.Enqueue(state);Shown=queue.Dequeue();
        }
    }
}

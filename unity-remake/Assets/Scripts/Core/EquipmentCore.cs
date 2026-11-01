using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;
using static Ao.SourceContracts.SourceInteger;

namespace Ao.SourceContracts
{
    public readonly struct DeviceSignals
    {
        public readonly int Loaded, Playing;
        public readonly bool TextActive;
        public DeviceSignals(int loaded,int playing,bool textActive)
        {Loaded=loaded;Playing=playing;TextActive=textActive;}
    }
    public readonly struct CoreResult
    {
        public readonly bool Ok,Applied;
        public readonly string Reason;
        public CoreResult(bool ok,bool applied,string reason=""){Ok=ok;Applied=applied;Reason=reason;}
    }

    // Converted PC instructions only. No Unity types, physical time or source replay input.
    public sealed class EquipmentCore
    {
        readonly JObject data,room,initial;
        readonly byte[] flags,bank,images;
        readonly HashSet<int> verified;
        readonly Dictionary<int,JObject> instructions=new Dictionary<int,JObject>();
        readonly Dictionary<string,int> starts=new Dictionary<string,int>();
        JObject s;
        byte[] player,decor,ambient,spark;
        bool outside;
        public string Error {get;private set;}="";
        static int N(JToken value,string key)=>value[key].Value<int>();
        static int N(JToken value)=>value.Value<int>();
        static int Raw32(JToken value)
        {
            long raw=value.Value<long>();
            if(raw<0||raw>uint.MaxValue)throw new InvalidDataException("Source pointer outside 32-bit range");
            return unchecked((int)(uint)raw);
        }
        static bool B(JToken value,string key)=>value[key].Value<bool>();
        static bool Null(JToken value)=>value==null || value.Type==JTokenType.Null;
        static JObject Obj(JToken value)=>Null(value)?null:(JObject)value;
        static byte[] Hex(string value)
        {
            if(value.Length%2!=0)throw new InvalidDataException("Odd source hex length");
            var bytes=new byte[value.Length/2];
            for(int i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);
            return bytes;
        }
        static string Hex(byte[] value)=>value==null?null:BitConverter.ToString(value).Replace("-","").ToLowerInvariant();
        static void PutLong(byte[] raw,int offset,int value){PutWord(raw,offset,value>>16);PutWord(raw,offset+2,value);}
        static int Long(byte[] raw,int offset)=>(Word(raw,offset)<<16)|Word(raw,offset+2);
        static JObject Slot(int pc,string owner)=>new JObject { ["pc"]=pc,["owner"]=owner,["wait"]=null,["arg"]=0,["target"]=0,["active"]=true };
        static bool Active(JToken slot)=>!Null(slot)&&B(slot,"active");
        void Request(JObject request)=>((JArray)s["requests"]).Add(request);

        public EquipmentCore(string directory,bool editorMetadata=false)
        {
            var files=SourceGuard.Load(directory,SourcePins.Files,editorMetadata);
            data=JObject.Parse(Encoding.UTF8.GetString(files["equipment/core.json"]));
            room=JObject.Parse(Encoding.UTF8.GetString(files["room/room.json"]));
            flags=files["scene/flags.bin"];bank=files["character/animation-bank.bin"];images=files["character/image-table.bin"];
            if((string)data["schema"]!="ao_pc_equipment_core_v1")throw new InvalidDataException("Unknown equipment contract");
            foreach(var program in ((JObject)data["contract"]["programs"]).Properties())
            {
                var rows=(JArray)program.Value;starts.Add(program.Name,N(rows[0]["source"],"offset"));
                foreach(JObject row in rows) instructions.Add(N(row["source"],"offset"),(JObject)row.DeepClone());
            }
            if(starts.Count!=12 || instructions.Count!=86)throw new InvalidDataException("Incomplete source programs");
            verified=new HashSet<int>(room["movement_profile"]["verified_query_indices"].Select(N));
            verified.UnionWith(data["additional_query_indices"].Select(N));
            initial=(JObject)data["initial_state"].DeepClone();Reset();
        }
        public void Reset(){Restore(initial);Error="";outside=false;}
        void Restore(JObject state)
        {
            s=(JObject)state.DeepClone();player=Hex((string)s["player"]);decor=Hex((string)s["decor"]);ambient=Hex((string)s["ambient"]);
            spark=Null(s["spark"])?null:Hex((string)s["spark"]);
        }
        public JObject Snapshot()
        {
            var copy=(JObject)s.DeepClone();copy["player"]=Hex(player);copy["decor"]=Hex(decor);copy["ambient"]=Hex(ambient);
            copy["spark"]=spark==null?JValue.CreateNull():new JValue(Hex(spark));return copy;
        }
        int[] Record(byte[] raw,bool auxiliary)
        {
            int index=Word(raw,0x36),cursor=Word(raw,0x2c);
            if(!auxiliary&&index<16)
            {
                if(cursor<0 || cursor%3!=0 || (index<8?cursor>3:cursor>12))throw new InvalidDataException("Unknown animation cursor");
                int offset=Long(bank,index*4)-0x20220010+cursor;
                if(offset<0 || offset>=bank.Length)throw new InvalidDataException("Unknown animation record");
                if(bank[offset]==0)return new[]{0,0,0};
                if(offset+3>bank.Length)throw new InvalidDataException("Truncated animation record");
                return new[]{(int)bank[offset],bank[offset+1],bank[offset+2]};
            }
            var list=data["extra_animations"][auxiliary?"spark":"player"][index.ToString()];
            if(Null(list)||cursor%3!=0||cursor/3>=list.Count())throw new InvalidDataException("Unknown interaction animation record");
            return list[cursor/3].Select(N).ToArray();
        }
        bool DecodeExtra(byte[] raw,bool auxiliary)
        {
            var record=Record(raw,auxiliary);
            if(record[0]==0){PutWord(raw,0x2c,0);PutWord(raw,6,Word(raw,6)|0x100);return true;}
            PutWord(raw,0x32,record[0]);PutWord(raw,0x34,record[1]);PutWord(raw,0x14,(Word(raw,0x14)&0xfffe)|((record[2]&4)!=0?1:0));
            int pointer=auxiliary?Raw32(data["extra_animations"]["spark_image_pointers"][record[1].ToString()]):Long(images,record[1]*4);
            PutLong(raw,0x5c,pointer);return false;
        }
        bool AnimationWait(byte[] raw,bool auxiliary)
        {
            PutWord(raw,0x30,Word(raw,0x30)+1);
            if(Word(raw,0x30)>=Word(raw,0x32)){PutWord(raw,0x30,0);PutWord(raw,0x2c,Word(raw,0x2c)+3);PutWord(raw,6,Word(raw,6)|0x80);}
            bool done=DecodeExtra(raw,auxiliary);if(done)PutWord(raw,6,Word(raw,6)&0xfeff);return done;
        }
        void Decode(bool advance)
        {
            if(advance)
            {
                PutWord(player,0x30,Word(player,0x30)+1);
                if(Word(player,0x30)>=Word(player,0x32)){PutWord(player,0x30,0);PutWord(player,0x2c,Word(player,0x2c)+3);PutWord(player,6,Word(player,6)|0x80);}
            }
            var record=Record(player,false);
            if(record[0]==0){PutWord(player,0x2c,0);PutWord(player,6,Word(player,6)|0x100);record=Record(player,false);}
            PutWord(player,0x32,record[0]);PutWord(player,0x34,record[1]);PutWord(player,0x14,(Word(player,0x14)&0xfffe)|((record[2]&4)!=0?1:0));
            PutLong(player,0x5c,Long(images,record[1]*4));
        }
        void Pose(int heading)
        {foreach(int offset in new[]{0x30,0x2c,0x18,0x1a})PutWord(player,offset,0);PutWord(player,0x26,heading);PutWord(player,0x36,heading);Decode(false);}
        bool Forced(int axis,int target)
        {
            int position=Word(player,axis*2),delta=Signed16(target-position),speed=Movement.StraightSpeed[Word(player,0x24)];
            int heading=delta<0?(axis==0?4:6):(axis==0?0:2),amount=delta<0?Math.Max(delta,-speed):Math.Min(delta,speed);
            PutWord(player,0x26,heading);PutWord(player,0x18,axis==0?amount:0);PutWord(player,0x1a,axis==1?amount:0);
            PutWord(player,0x36,8+heading);Decode(true);PutWord(player,axis*2,position+amount);
            bool done=(Word(player,axis*2)&0xfff0)==(target&0xfff0);
            if(done){PutWord(player,6,Word(player,6)&0xfeff);PutWord(player,0x18+axis*2,0);}return done;
        }
        void Free()
        {
            if(N(s,"disabled")!=255)
            {
                if((Word(player,6)&2)!=0)Movement.Velocity(player);
                else{PutWord(player,0x2c,0);PutWord(player,0x36,Word(player,0x26));}
                PutWord(player,0x18,Word(player,0x18)+Word(player,0x1e));PutWord(player,0x1a,Word(player,0x1a)+Word(player,0x20));
                PutWord(player,0x1e,0);PutWord(player,0x20,0);
            }
            Decode(true);var next=Movement.Collision(player,flags,verified,out outside);if(!outside)player=next;
        }
        JObject Camera(JObject state,JArray target)
        {
            var r=(JObject)state.DeepClone();r["display_x"]=N(state,"x");r["display_y"]=N(state,"y");r["dx"]=0;r["dy"]=0;
            for(int axis=0;axis<2;axis++)
            {
                string key=axis==0?"x":"y";int center=B(s,"fixed_camera")?0:(axis==0?0xa80:0x780),margin=B(s,"fixed_camera")?0:0x200;
                int upper=Signed16(N(state,key)+center+margin),lower=Signed16(N(state,key)+center-margin),min=axis==0?8192:24576,max=axis==0?10240:25088,value=N(target[axis]);
                if(value>upper){int d=Math.Min(N(s,"camera_speed"),Signed16(value-upper)),p=Signed16(N(state,key)+d);if(p>max){p=max;d=0;}r[key]=p;r["d"+key]=d;}
                if(value<lower){int d=Math.Min(N(s,"camera_speed"),Signed16(lower-value)),p=Signed16(N(r,key)-d);if(p<min){p=min;d=0;}r[key]=p;r["d"+key]=-d;}
            }
            return r;
        }
        void EffectStep()
        {
            var effect=Obj(s["effect"]);if(effect==null||B(effect,"ended"))throw new InvalidDataException("Inactive expression wait");
            if(N(effect,"phase")==4){effect["counter"]=(N(effect,"counter")-1)&65535;if(N(effect,"counter")==0)effect["phase"]=5;return;}
            effect["animation"]=N(effect,"phase")==0?0:(N(effect,"phase")==5?1:9);
            effect["timer"]=(N(effect,"timer")+1)&65535;
            if(N(effect,"timer")>=N(effect,"duration")){effect["timer"]=0;effect["cursor"]=N(effect,"cursor")+3;effect["flags"]=N(effect,"flags")|0x80;}
            var sequences=data["contract"]["expression_sequences"];var sequence=(JArray)sequences[N(effect,"animation").ToString()];
            if(N(effect,"cursor")/3==sequence.Count){effect["cursor"]=0;effect["flags"]=N(effect,"flags")|0x100;}
            var record=sequence[N(effect,"cursor")/3];effect["duration"]=N(record[0]);effect["image"]=N(record[1]);
            if((N(effect,"flags")&0x100)!=0)
            {
                effect["flags"]=N(effect,"flags")&0xfeff;bool ending=N(effect,"phase")==5;
                if(!ending)effect["phase"]=N(effect,"phase")+1;
                effect["animation"]=N(effect,"phase")==1?9:1;effect["timer"]=0;effect["cursor"]=0;
                effect["duration"]=N(sequences[N(effect,"animation").ToString()][0][0]);
                if(ending){effect["flags"]=0;effect["ended"]=true;}
            }
        }
        bool DecorTick(byte[] raw,int index,bool eventAnimation)
        {
            var program=room["visuals"]["programs"][index];
            byte[] sequence=eventAnimation?data["contract"]["cirrus_sequence"].Select(x=>(byte)N(x)).ToArray():Hex((string)program["sequence_hex"]);
            int cursor=Word(raw,0x1c),timer=Word(raw,0x1e);
            if(eventAnimation)timer=(timer+1)&65535;
            if(timer>=Word(raw,0x20)){timer=0;cursor+=3;PutWord(raw,10,Word(raw,10)|0x80);}
            if(!eventAnimation)timer++;PutWord(raw,0x1e,timer);
            bool ended=sequence[cursor]==0;
            if(ended){PutWord(raw,10,Word(raw,10)|0x100);if(!eventAnimation)cursor=0;}
            if(!ended||!eventAnimation){PutWord(raw,0x1c,cursor);PutWord(raw,0x20,sequence[cursor]);PutWord(raw,0x22,sequence[cursor+1]);}
            PutWord(raw,0x14,Word(raw,0x14)&0xfffe);PutLong(raw,0x30,N(program["image_pointers"][Word(raw,0x22)]));return ended;
        }
        bool Wait(JObject slot,DeviceSignals signals)
        {
            switch(N(slot,"wait"))
            {
                case 4:bool auxiliary=(string)slot["owner"]=="spark";return AnimationWait(auxiliary?spark:player,auxiliary);
                case 0:int old=N(slot,"arg");slot["arg"]=(old-1)&65535;return old==0;
                case 1:case 2:return Forced(N(slot,"wait")-1,N(slot,"target"));
                case 8:return !signals.TextActive;
                case 9:return (Word(N(slot,"target")==0?player:spark,6)&4)==0;
                case 11:bool done=N(s["cameras"][0],"dx")==0&&N(s["cameras"][0],"dy")==0;if(done&&N(slot,"arg")==2){s["fixed_camera"]=false;s["camera_speed"]=128;}return done;
                case 15:if(signals.Loaded==1||N(slot,"arg")>300)return true;slot["arg"]=N(slot,"arg")+1;return false;
                case 16:PutWord(decor,6,0);PutWord(decor,8,0);bool ended=DecorTick(decor,0,true);if(ended){PutWord(decor,10,Word(decor,10)&0xfeff);PutWord(decor,0x1a,0);}return ended;
                case 19:return signals.Playing!=0;
                case 23:EffectStep();return B(s["effect"],"ended");
                default:throw new InvalidDataException("Unknown event wait");
            }
        }
        void Attach(string program,string owner)
        {
            if(owner=="spark")
            {
                if(spark==null||Active(s["spark_child"]))throw new InvalidDataException("Occupied spark child slot");
                s["spark_child"]=Slot(starts[program],owner);PutWord(spark,6,Word(spark,6)|4);PutWord(spark,0x38,2);return;
            }
            if(Active(s["child"]))throw new InvalidDataException("Occupied child slot");
            s["child"]=Slot(starts[program],owner);
            if(owner=="actor"){PutWord(player,6,Word(player,6)|4);PutWord(player,0x38,1);}
            else{PutWord(decor,10,Word(decor,10)|4);PutWord(decor,0x26,1);}
        }
        void Dispatch(JObject slot,DeviceSignals signals)
        {
            if(slot==null||!B(slot,"active"))return;
            if(!Null(slot["wait"])){if(Wait(slot,signals))slot["wait"]=null;return;}
            for(int budget=0;budget<32;budget++)
            {
                if(!instructions.TryGetValue(N(slot,"pc"),out var row))throw new InvalidDataException("Unknown PC instruction cursor");
                var a=row["args"];((JArray)s["commands"]).Add(new JArray((string)slot["owner"],N(slot,"pc"),N(row["source"],"opcode")));
                slot["pc"]=N(slot,"pc")+N(row["source"],"span");
                switch((string)row["action"])
                {
                    case "end":slot["active"]=false;
                        if((string)slot["owner"]=="actor")PutWord(player,6,Word(player,6)&0xfffb);
                        else if((string)slot["owner"]=="decoration")PutWord(decor,10,Word(decor,10)&0xfffb);
                        else if((string)slot["owner"]=="spark"){PutWord(spark,6,Word(spark,6)&0xfffb);PutWord(spark,0x2a,2);}return;
                    case "branch_story":int value=Convert.ToInt32((string)s["story"],16);
                        if(!a["allowed_bytes"].Select(N).Contains(value))throw new InvalidDataException("Unverified story branch");
                        var destination=a[(value&N(a,"mask"))!=0?"if_set":"if_clear"];
                        if(Null(destination))throw new InvalidDataException("Unverified story target");slot["pc"]=N(destination);break;
                    case "set_story_bit":int story=Convert.ToInt32((string)s["story"],16);
                        if(story!=N(a,"required_byte"))throw new InvalidDataException("Illegal story mutation");s["story"]=(story|(1<<N(a,"bit"))).ToString("x2");break;
                    case "hide_decoration":PutWord(N(a,"object_id")==48?decor:ambient,10,0);break;
                    case "grant_story_item":if(N(s,"item_count")!=N(a,"required_count"))throw new InvalidDataException("Illegal story item count");s["item_count"]=N(a,"result_count");break;
                    case "player_palette":PutWord(player,0x12,N(a,"selector"));break;
                    case "player_mode":PutWord(player,0x16,(Word(player,0x16)&0xff00)|N(a,"mode"));break;
                    case "player_aux_input":player[0x49]=(byte)N(a,"value");break;
                    case "player_pickup_y":PutWord(player,2,N(a,"y_raw"));break;
                    case "actor_animation":bool auxiliary=(string)slot["owner"]=="spark";byte[] raw=auxiliary?spark:player;
                        PutWord(raw,0x36,N(a,"index"));PutWord(raw,0x30,0);PutWord(raw,0x2c,0);PutWord(raw,6,Word(raw,6)&0xfeff);DecodeExtra(raw,auxiliary);slot["wait"]=4;break;
                    case "save_actor_position":s["temporary_coordinates"][N(a,"slot").ToString()]=new JArray(Word(player,0),Word(player,2),Word(player,4));break;
                    case "offset_saved_position":var position=(JArray)s["temporary_coordinates"][N(a,"slot").ToString()];for(int i=0;i<3;i++)position[i]=(N(position[i])+N(a["delta_raw"][i]))&65535;break;
                    case "spawn_story_spark":spark=Hex((string)data["extra_animations"]["spark_spawn"]);var p=s["temporary_coordinates"][N(a,"slot").ToString()];PutWord(spark,0,N(p[0]));PutWord(spark,2,N(p[1]));s["effect"]=null;s["effect_xy"]=null;break;
                    case "remove_story_spark":PutWord(spark,6,0);break;
                    case "attach_actor":Attach((string)a["program"],N(a,"actor_id")==0?"actor":"spark");break;
                    case "wait_actor":slot["target"]=N(a,"actor_id");if((Word(N(slot,"target")==0?player:spark,6)&4)!=0)slot["wait"]=9;break;
                    case "lock_control":s["disabled"]=255;PutWord(player,0x2c,0);PutWord(player,0x36,Word(player,0x26));break;
                    case "unlock_control":s["disabled"]=0;break;
                    case "attach_player":Attach((string)a["program"],"actor");break;
                    case "wait_player":if((Word(player,6)&4)!=0)slot["wait"]=9;break;
                    case "expression":spark=null;s["effect"]=new JObject{["phase"]=0,["counter"]=N(a,"hold_updates"),["animation"]=0,["cursor"]=0,["timer"]=0,["duration"]=5,["image"]=0,["flags"]=0x8000,["ended"]=false};s["effect_xy"]=new JArray(Word(player,0),Word(player,2));slot["wait"]=23;break;
                    case "player_pose":Pose(N(a,"heading"));slot["wait"]=0;slot["arg"]=1;break;
                    case "camera_target":s["camera_target"]=new JArray(N(a,"x_raw"),N(a,"y_raw"));s["camera_speed"]=N(a,"speed_raw");s["fixed_camera"]=true;break;
                    case "camera_follow_player":s["fixed_camera"]=false;break;
                    case "wait_camera":slot["wait"]=11;slot["arg"]=B(a,"restore_speed")?2:0;break;
                    case "load_audio":s["resource"]=(string)a["id"]=="cirrus_pickup_audio"?"IVENT176.AIF":"IVENT041.AIF";Request(new JObject{["type"]="load_original_resource",["id"]=(string)s["resource"]});break;
                    case "wait_audio_loaded":slot["wait"]=15;slot["arg"]=0;break;
                    case "play_audio":Request(new JObject{["type"]="play_original_resource",["id"]=(string)s["resource"]});break;
                    case "wait_audio_started":slot["wait"]=19;break;
                    case "attach_cirrus":Attach((string)a["program"],"decoration");break;
                    case "cirrus_animation":PutWord(decor,0x24,N(a,"index"));PutWord(decor,0x1e,0);PutWord(decor,0x1c,0);PutWord(decor,0x20,8);PutWord(decor,0x22,46);PutWord(decor,0x14,Word(decor,0x14)&0xfffe);PutWord(decor,10,Word(decor,10)&0xfeff);PutLong(decor,0x30,N(room["visuals"]["programs"][0]["image_pointers"][46]));slot["wait"]=16;break;
                    case "wait_updates":slot["wait"]=0;slot["arg"]=N(a,"count");break;
                    case "source_text_layout":Request(new JObject{["type"]="source_text_layout",["y"]=N(a,"y")});break;
                    case "dialogue":Request(new JObject{["type"]="dialogue",["id"]=(string)a["id"]});slot["wait"]=8;break;
                    case "player_speed":PutWord(player,0x24,N(a,"index"));break;
                    case "player_move_axis":int axis=N(a,"axis"),target=N(a,"target_raw");if((Word(player,axis*2)&0xfff0)!=(target&0xfff0)){PutWord(player,0x2c,0);PutWord(player,0x30,0);slot["wait"]=axis+1;slot["target"]=target;if(Wait(slot,signals))slot["wait"]=null;return;}break;
                    default:throw new InvalidDataException("Unknown PC action: "+row["action"]);
                }
                if(!Null(slot["wait"]))return;
            }
            throw new InvalidDataException("Event instruction budget exhausted");
        }
        bool Contact(string id)
        {
            foreach(var b in room["boundaries"])
            {if((string)b["id"]!=id)continue;var bounds=b["raw_bounds_inclusive"];return Word(player,0)>=N(bounds[0])&&Word(player,0)<=N(bounds[2])&&Word(player,2)>=N(bounds[1])&&Word(player,2)<=N(bounds[3]);}return false;
        }
        bool InteractionHit(int pressed)
        {
            if(N(s,"disabled")==255||(pressed&0x0600)==0)return false;
            if(Word(player,0x28)!=1)throw new InvalidDataException("Unverified interaction shape");
            int x=Signed16(Word(player,0)),y=Signed16(Word(player,2));var shape=Movement.Shape;
            switch(Word(player,0x26)){case 0:x+=shape[0]+shape[3]+32;break;case 2:y+=shape[1]+shape[4]+32;break;case 4:x+=shape[0]-32;break;case 6:y+=shape[1]-32;break;default:throw new InvalidDataException("Unverified interaction heading");}
            x=Signed16(x);y=Signed16(y);var bounds=data["interaction"]["bounds"];
            return x>=N(bounds[0])&&x<=N(bounds[2])&&y>=N(bounds[1])&&y<=N(bounds[3]);
        }
        bool LegalEquipment()
        {
            int weapon=N(s,"weapon"),attack=N(s,"attack"),count=N(s,"item_count");
            switch((string)s["story"])
            {case "01":return weapon==255&&attack==10&&count==0;case "03":return weapon==255&&attack==10&&(count==0||count==1);case "07":return (weapon==255&&attack==10&&count==1)||(weapon==27&&attack==15&&count==0);default:return false;}
        }
        public CoreResult Equipment(string action)
        {
            if(Error!=""||!LegalEquipment())return new CoreResult(false,false,"Invalid equipment state");
            if(action!="equip"&&action!="remove")return new CoreResult(false,false,"Unknown equipment operation");
            if(B(s,"transition_pending")||N(s,"disabled")!=0||Active(s["root"]))return new CoreResult(false,false,"Equipment unavailable during event or boundary");
            if(action=="equip")
            {
                if(N(s,"weapon")==27)return new CoreResult(true,false,"already_equipped");
                if(((string)s["story"]!="03"&&(string)s["story"]!="07")||N(s,"item_count")!=1)return new CoreResult(true,false,"not_owned");
                s["weapon"]=27;s["item_count"]=N(s,"item_count")-1;s["attack"]=15;s["story"]=(Convert.ToInt32((string)s["story"],16)|4).ToString("x2");
            }
            else{if(N(s,"weapon")==255)return new CoreResult(true,false,"empty_slot");s["weapon"]=255;s["item_count"]=N(s,"item_count")+1;s["attack"]=10;}
            return new CoreResult(true,true);
        }
        public CoreResult Step(int pad,DeviceSignals signals,int pressed=0)
        {
            if(Error!=""||!LegalEquipment())return new CoreResult(false,false,"Invalid core state: "+Error);
            if(!new[]{0,0x1000,0x2000,0x4000,0x8000,0x0200,0x0400}.Contains(pad)||pressed<0||pressed>65535||signals.Loaded<0||signals.Loaded>1||signals.Playing<0||signals.Playing>255)return new CoreResult(false,false,"Invalid input/device response");
            if(B(s,"transition_pending"))return new CoreResult(true,false,"test_boundary");
            var before=Snapshot();
            try
            {
                s["update"]=N(s,"update")+1;((JArray)s["commands"]).Clear();((JArray)s["requests"]).Clear();outside=false;
                PutWord(player,6,Word(player,6)&0xfffd);PutWord(player,0x18,0);PutWord(player,0x1a,0);
                if(N(s,"disabled")!=255&&(Word(player,6)&4)==0)Movement.Gate(player,pad);
                if(Contact("stair_scene_boundary")){s["transition_pending"]=true;return new CoreResult(true,true,"scene_submission_boundary");}
                if(!Active(s["root"])&&Contact("stair_script_boundary")){s["root"]=Slot(starts["entry"],"root");s["runs"]=N(s,"runs")+1;}
                else if(!Active(s["root"])&&InteractionHit(pressed)){s["root"]=Slot(starts["pickup_entry"],"root");s["runs"]=N(s,"runs")+1;}
                Dispatch(Obj(s["root"]),signals);
                if((Word(player,6)&4)!=0)Dispatch(Obj(s["child"]),signals);else Free();
                if(spark!=null&&(Word(spark,6)&0x8000)!=0){if((Word(spark,6)&4)!=0)Dispatch(Obj(s["spark_child"]),signals);else DecodeExtra(spark,true);}
                var target=B(s,"fixed_camera")?(JArray)s["camera_target"]:new JArray(Signed16(Word(player,0)),Signed16(Word(player,2)));
                var cameras=(JArray)s["cameras"];for(int i=0;i<cameras.Count;i++)cameras[i]=Camera((JObject)cameras[i],target);
                if((Word(decor,10)&4)!=0)Dispatch(Obj(s["child"]),signals);else if((Word(decor,10)&0x8000)!=0&&Word(decor,0x1a)!=0)DecorTick(decor,0,false);
                if((Word(ambient,10)&0x8000)!=0)DecorTick(ambient,1,false);
                if(outside){Restore(before);return new CoreResult(true,false,"test_boundary");}
                return new CoreResult(true,true);
            }
            catch(Exception e) when(e is InvalidDataException||e is IndexOutOfRangeException||e is ArgumentException||e is KeyNotFoundException)
            {Restore(before);Error=e.Message;return new CoreResult(false,false,Error);}
        }
    }
}

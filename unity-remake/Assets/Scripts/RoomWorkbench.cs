using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Ao.SourceContracts;
using Newtonsoft.Json.Linq;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ao.UnityMigration
{
    // U2 presentation only. Cube furniture and capsule are explicitly graybox art.
    public sealed class RoomWorkbench : MonoBehaviour
    {
        public Material BaseMaterial;
        public RoomArt Art;
        public Font BundledFont;
        RoomSession session;
        SourceEffects3D effects;
        Camera view;
        Transform player,cirrus,spark,heading;
        GameObject marker,actor,dialoguePanel,equipmentPanel,diagnosticPanel;
        TextMeshProUGUI status,dialogueText,pageText,weaponText,diagnosticText;
        Button interactButton,equipmentButton,equipButton,removeButton,backButton;
        TMP_FontAsset font;
        Canvas ui;
        AudioSource voice;
        readonly Dictionary<string,AudioClip> clips=new Dictionary<string,AudioClip>();
        readonly HashSet<KeyCode> blocked=new HashSet<KeyCode>();
        readonly LogicClock clock=new LogicClock();
        int inputEpoch,autoUpdate,pageAge,stairs,frames;
        bool autoEquipped,qa,screenshotBusy,finished,uiVerified,reminderQA,audioStartedObserved;
        readonly HashSet<string> presentationChecks=new HashSet<string>();
        string reportPath,shotDir,failure="",loadedId="";
        readonly HashSet<string> shots=new HashSet<string>();
        static readonly KeyCode[] Directions={KeyCode.UpArrow,KeyCode.W,KeyCode.DownArrow,KeyCode.S,KeyCode.LeftArrow,KeyCode.A,KeyCode.RightArrow,KeyCode.D};
        static string Arg(string name){var args=Environment.GetCommandLineArgs();for(int i=0;i<args.Length-1;i++)if(args[i]==name)return args[i+1];return "";}
        void Start()
        {
            if(Art!=null&&Arg("--u4-preview")!="")
            {var preview=gameObject.AddComponent<U4Preview>();preview.Art=Art;preview.Output=Arg("--u4-preview");enabled=false;return;}
            try
            {
                reportPath=Arg("--u2-report");shotDir=Arg("--u2-shots");qa=reportPath!="";reminderQA=Arg("--u4-route")=="reminder";
                Application.runInBackground=qa;Application.targetFrameRate=60;
                if(qa&&shotDir!="")Directory.CreateDirectory(shotDir);
                session=new RoomSession(new EquipmentCore(Path.Combine(Application.streamingAssetsPath,"SourceLocal"),Application.isEditor));
                var audio=SourceGuard.Load(Path.Combine(Application.streamingAssetsPath,"PresentationLocal"),PresentationPins.Files,Application.isEditor);
                clips.Add("IVENT041.AIF",ReadWave(audio["event.wav"],"Cirrus reminder"));
                clips.Add("IVENT176.AIF",ReadWave(audio["pickup.wav"],"Cirrus pickup"));
                voice=gameObject.AddComponent<AudioSource>();voice.playOnAwake=false;voice.spatialBlend=0;
                session.DeviceRequest=Device;
                font=BundledFont!=null?TMP_FontAsset.CreateFontAsset(BundledFont):TMP_FontAsset.CreateFontAsset("Microsoft JhengHei","Regular",64);
                if(font==null)font=TMP_FontAsset.CreateFontAsset("Microsoft JhengHei UI","Regular",64);
                if(font==null)throw new InvalidDataException("U2 requires installed Microsoft JhengHei; bundled font pending U4");
                BuildScene();BuildUI();Draw();
            }
            catch(Exception ex){Fail(ex.ToString());}
        }
        static AudioClip ReadWave(byte[] bytes,string name)
        {
            using(var reader=new BinaryReader(new MemoryStream(bytes)))
            {
                if(new string(reader.ReadChars(4))!="RIFF")throw new InvalidDataException("Invalid WAV");
                reader.ReadInt32();if(new string(reader.ReadChars(4))!="WAVE")throw new InvalidDataException("Invalid WAV");
                int rate=0;short channels=0,bits=0;byte[] pcm=null;
                while(reader.BaseStream.Position+8<=bytes.Length)
                {
                    string id=new string(reader.ReadChars(4));int n=reader.ReadInt32();long end=reader.BaseStream.Position+n;
                    if(end>bytes.Length||n<0)throw new InvalidDataException("Truncated WAV");
                    if(id=="fmt "){if(reader.ReadInt16()!=1)throw new InvalidDataException("Non-PCM WAV");channels=reader.ReadInt16();rate=reader.ReadInt32();reader.ReadInt32();reader.ReadInt16();bits=reader.ReadInt16();}
                    if(id=="data")pcm=reader.ReadBytes(n);
                    reader.BaseStream.Position=end+(n&1);
                }
                if(channels!=1||bits!=16||rate!=22050||pcm==null)throw new InvalidDataException("Unexpected source audio format");
                var values=new float[pcm.Length/2];for(int i=0;i<values.Length;i++)values[i]=(short)(pcm[i*2]|pcm[i*2+1]<<8)/32768f;
                var clip=AudioClip.Create(name,values.Length,1,rate,false);clip.SetData(values,0);return clip;
            }
        }
        void Device(string type,string id,int generation)
        {
            if(type=="stop"){voice.Stop();loadedId="";return;}
            if(type=="load_original_resource")
            {if(!clips.ContainsKey(id))throw new InvalidDataException("Unknown audio resource "+id);voice.Stop();loadedId=id;voice.clip=clips[id];session.SetDeviceResponse(generation,true,false);}
            else if(type=="play_original_resource")
            {if(loadedId=="")throw new InvalidOperationException("Audio play before load");voice.Play();if(!voice.isPlaying)throw new InvalidOperationException("Audio failed to start");audioStartedObserved=true;session.SetDeviceResponse(generation,true,true);if(session.Paused)voice.Pause();}
            else throw new InvalidDataException("Unknown device request");
        }
        Material Material(Color color){var m=new Material(BaseMaterial);m.color=color;return m;}
        GameObject Primitive(string name,PrimitiveType type,Vector3 position,Vector3 scale,Color color)
        {
            var go=GameObject.CreatePrimitive(type);go.name=name;go.transform.position=position;go.transform.localScale=scale;
            Destroy(go.GetComponent<Collider>());go.GetComponent<Renderer>().sharedMaterial=Material(color);return go;
        }
        void BuildScene()
        {
            view=Camera.main;if(view==null){view=new GameObject("Fixed source-independent ortho camera").AddComponent<Camera>();view.gameObject.AddComponent<AudioListener>();}
            var target=new Vector3(7,0,-4);view.transform.rotation=Quaternion.Euler(45,0,0);view.transform.position=target-view.transform.forward*16;
            view.orthographic=true;view.orthographicSize=5.7f;view.clearFlags=CameraClearFlags.SolidColor;view.backgroundColor=new Color(.025f,.04f,.05f);
            var key=new GameObject("Warm key light").AddComponent<Light>();key.type=LightType.Directional;key.color=new Color(1,.83f,.65f);key.intensity=1.8f;key.shadows=LightShadows.Soft;key.transform.rotation=Quaternion.Euler(50,-30,0);
            RenderSettings.ambientLight=new Color(.35f,.38f,.43f);
            if(Art!=null){key.color=new Color(1,.91f,.8f);key.intensity=1.15f;RenderSettings.ambientLight=new Color(.29f,.30f,.32f);}
            if(Art==null)
            {
            Primitive("Graybox floor — not collision geometry",PrimitiveType.Cube,new Vector3(7,-.12f,-4),new Vector3(14,.2f,8),new Color(.20f,.24f,.25f));
            // Only visual masses. Authoritative contacts come exclusively from sealed source lookup data.
            Box("West bed",57,110,55,67,.65f);Box("North west bed",144,60,48,68,.65f);Box("North east bed",224,60,48,68,.65f);
            Box("Table",176,160,96,63,.8f);Box("Left chair",182,139,29,21,.5f);Box("Right chair",220,139,29,21,.5f);
            }
            player=new GameObject("Player source anchor").transform;
            if(Art==null)actor=Primitive("U2 capsule; final model pending review",PrimitiveType.Capsule,Vector3.zero,new Vector3(.45f,.5625f,.45f),new Color(.4f,.63f,.37f));if(Art==null){actor.transform.SetParent(player,false);actor.transform.localPosition=new Vector3(0,.5625f,0);}else{Art.Initialize(player);view.orthographicSize=5.7f;}
            marker=Primitive("Diagnostic marker",PrimitiveType.Cube,Vector3.zero,new Vector3(.4f,.08f,.4f),Color.cyan);marker.transform.SetParent(player,false);marker.transform.localPosition=Vector3.up*.06f;
            heading=Primitive("Facing",PrimitiveType.Cube,Vector3.zero,new Vector3(.10f,.08f,.35f),new Color(1,.75f,.3f)).transform;heading.SetParent(player,false);heading.localPosition=new Vector3(0,.1f,.32f);
            if(Art==null)cirrus=Primitive("Cirrus source object placeholder",PrimitiveType.Cylinder,Vector3.zero,new Vector3(.25f,.3f,.25f),new Color(.85f,.65f,.25f)).transform;
            if(Art==null)spark=Primitive("Source story spark diagnostic",PrimitiveType.Sphere,Vector3.zero,Vector3.one*.23f,Color.white).transform;
            if(Art!=null){effects=gameObject.AddComponent<SourceEffects3D>();effects.Initialize(font,BaseMaterial);}
        }
        void Box(string name,float x,float y,float w,float h,float height)
        {Primitive(name+" visual mass only",PrimitiveType.Cube,new Vector3((x+w/2)/32,height/2,-(y+h/2)/32),new Vector3(w/32,height,h/32),new Color(.31f,.35f,.36f));}
        RectTransform Rect(GameObject go,Transform parent,Vector2 min,Vector2 max,Vector2 offsetMin,Vector2 offsetMax)
        {go.transform.SetParent(parent,false);var r=go.GetComponent<RectTransform>();r.anchorMin=min;r.anchorMax=max;r.offsetMin=offsetMin;r.offsetMax=offsetMax;return r;}
        GameObject Panel(string name,Transform parent,Vector2 min,Vector2 max,Vector2 lo,Vector2 hi)
        {var go=new GameObject(name,typeof(RectTransform),typeof(Image));Rect(go,parent,min,max,lo,hi);go.GetComponent<Image>().color=new Color(.045f,.085f,.105f,.96f);return go;}
        TextMeshProUGUI Text(string value,Transform parent,int size,Vector2 min,Vector2 max,Vector2 lo,Vector2 hi)
        {
            var go=new GameObject("Text",typeof(RectTransform),typeof(TextMeshProUGUI));Rect(go,parent,min,max,lo,hi);var t=go.GetComponent<TextMeshProUGUI>();t.font=font;t.fontSize=size;t.color=new Color(.91f,.93f,.9f);t.text=value;t.raycastTarget=false;t.textWrappingMode=TextWrappingModes.Normal;return t;
        }
        Button Button(string value,Transform parent,Vector2 pos,Vector2 size,UnityEngine.Events.UnityAction action)
        {
            var go=Panel(value,parent,Vector2.zero,Vector2.zero,pos,pos+size);go.GetComponent<Image>().color=new Color(.14f,.24f,.28f);var b=go.AddComponent<Button>();b.targetGraphic=go.GetComponent<Image>();b.navigation=new Navigation{mode=Navigation.Mode.None};b.onClick.AddListener(action);
            var t=Text(value,go.transform,24,Vector2.zero,Vector2.one,new Vector2(8,3),new Vector2(-8,-3));t.alignment=TextAlignmentOptions.Center;return b;
        }
        void BuildUI()
        {
            var canvas=new GameObject("PC UI",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));ui=canvas.GetComponent<Canvas>();ui.renderMode=RenderMode.ScreenSpaceOverlay;
            var scaler=canvas.GetComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;scaler.referenceResolution=new Vector2(1920,1080);scaler.matchWidthOrHeight=.5f;
            new GameObject("UI events",typeof(EventSystem),typeof(StandaloneInputModule)).GetComponent<EventSystem>().sendNavigationEvents=false;
            var top=Panel("Title",canvas.transform,new Vector2(0,1),Vector2.one,new Vector2(0,-78),Vector2.zero);
            Text(Art==null?"MAP001  /  UNITY 3D 灰模驗證":"MAP001  /  UNITY 3D 起始房間",top.transform,30,Vector2.zero,Vector2.one,new Vector2(34,18),new Vector2(-700,-12));
            Text(Art==null?"U2 功能移植 · 美術未定稿 · 效能未驗收":"起始房間候選版 · 效能未驗收",top.transform,23,Vector2.zero,Vector2.one,new Vector2(1120,19),new Vector2(-24,-14));
            var bottom=Panel("Controls",canvas.transform,Vector2.zero,new Vector2(1,0),Vector2.zero,new Vector2(0,150));
            status=Text("",bottom.transform,25,Vector2.zero,Vector2.one,new Vector2(30,85),new Vector2(-30,-12));
            Text("方向鍵 / WASD 移動    Space 暫停    . 單步    R 重設    F1 診斷    F2 外觀",bottom.transform,21,Vector2.zero,Vector2.one,new Vector2(30,22),new Vector2(-650,-85));
            interactButton=Button("互動 / 繼續  Enter",bottom.transform,new Vector2(1270,22),new Vector2(280,52),()=>session.ConfirmEdge());
            equipmentButton=Button("裝備  E",bottom.transform,new Vector2(1570,22),new Vector2(260,52),()=>session.TogglePanel());
            dialoguePanel=Panel("Dialogue",canvas.transform,new Vector2(.5f,0),new Vector2(.5f,0),new Vector2(-720,170),new Vector2(720,400));
            pageText=Text("CIRRUS",dialoguePanel.transform,26,Vector2.zero,Vector2.one,new Vector2(28,170),new Vector2(-28,-15));
            dialogueText=Text("",dialoguePanel.transform,32,Vector2.zero,Vector2.one,new Vector2(28,30),new Vector2(-28,-72));
            equipmentPanel=Panel("Equipment",canvas.transform,new Vector2(.5f,.5f),new Vector2(.5f,.5f),new Vector2(-330,-230),new Vector2(330,230));
            weaponText=Text("",equipmentPanel.transform,30,Vector2.zero,Vector2.one,new Vector2(30,255),new Vector2(-30,-24));
            equipButton=Button("裝備 Cirrus",equipmentPanel.transform,new Vector2(30,180),new Vector2(600,56),()=>session.SelectOption(0));
            removeButton=Button("卸下 Cirrus",equipmentPanel.transform,new Vector2(30,110),new Vector2(600,56),()=>session.SelectOption(1));
            backButton=Button("返回探索  Esc",equipmentPanel.transform,new Vector2(30,40),new Vector2(600,56),()=>session.TogglePanel());
            diagnosticPanel=Panel("Diagnostics",canvas.transform,new Vector2(0,1),new Vector2(0,1),new Vector2(20,-340),new Vector2(620,-95));
            diagnosticText=Text("",diagnosticPanel.transform,23,Vector2.zero,Vector2.one,new Vector2(18,18),new Vector2(-18,-18));
        }
        bool Down(KeyCode key)=>Input.GetKeyDown(key)&&!blocked.Contains(key);
        bool Held(KeyCode key)=>Input.GetKey(key)&&!blocked.Contains(key);
        void Barrier()
        {foreach(KeyCode key in Directions.Concat(new[]{KeyCode.Return,KeyCode.KeypadEnter,KeyCode.E}))if(Input.GetKey(key))blocked.Add(key);clock.Clear();}
        void Update()
        {
            if(failure!=""||session==null||finished)return;
            try
            {
                frames++;blocked.RemoveWhere(key=>!Input.GetKey(key));
                if(!qa)
                {
                    if(Down(KeyCode.R)){session.Reset();Barrier();}
                    if(Down(KeyCode.Space)){session.TogglePause();if(session.Paused)voice.Pause();else voice.UnPause();}
                    if(Down(KeyCode.F1))session.ToggleDiagnostic();if(Down(KeyCode.F2))session.ToggleMarker();
                    if(Down(KeyCode.E))session.TogglePanel();if(Down(KeyCode.Escape)&&session.Panel)session.TogglePanel();
                    if(inputEpoch!=session.InputEpoch){inputEpoch=session.InputEpoch;Barrier();}
                    if(session.Panel){if(Down(KeyCode.UpArrow)||Down(KeyCode.W))session.NavigatePanel(-1);if(Down(KeyCode.DownArrow)||Down(KeyCode.S))session.NavigatePanel(1);}
                    if(Down(KeyCode.Return)||Down(KeyCode.KeypadEnter))session.ConfirmEdge();
                }
                if(inputEpoch!=session.InputEpoch){inputEpoch=session.InputEpoch;Barrier();}
                if(qa&&session.Panel&&!screenshotBusy&&shots.Contains("equipped")){if(Art!=null&&!uiVerified)VerifyUI();else session.TogglePanel();}
                int pad=0,count=0;
                if(!qa&&!session.Panel){if(Held(KeyCode.UpArrow)||Held(KeyCode.W)){pad=0x1000;count++;}if(Held(KeyCode.DownArrow)||Held(KeyCode.S)){pad=0x2000;count++;}if(Held(KeyCode.LeftArrow)||Held(KeyCode.A)){pad=0x4000;count++;}if(Held(KeyCode.RightArrow)||Held(KeyCode.D)){pad=0x8000;count++;}}
                if(Down(KeyCode.Period)&&session.Paused)session.Tick(pad,count>1,true);
                if(!session.Paused&&!session.Panel&&!screenshotBusy)
                {
                    clock.Push(Time.unscaledDeltaTime);
                    while(clock.Take()){if(qa)pad=AutoPad();session.Tick(pad,count>1);if(qa){clock.Clear();break;}if(session.Panel||session.Paused)break;}
                }
                else clock.Clear();
                Draw();if(session.Error!="")throw new InvalidDataException(session.Error);
                if(qa)ObserveQA();
            }
            catch(Exception ex){Fail(ex.ToString());}
        }
        int AutoPad()
        {
            if(session.DialogueActive){pageAge++;if(pageAge>=60){session.ConfirmEdge();pageAge=0;}}
            if(!autoEquipped)
            {
                autoUpdate++;
                if(reminderQA)return autoUpdate<=6?0:autoUpdate<=36?0x2000:autoUpdate<=103?0x8000:0;
                if(Art!=null&&autoUpdate<=8)return autoUpdate<=2?0x4000:autoUpdate<=4?0x8000:autoUpdate<=6?0x1000:0x2000;
                int routeStep=autoUpdate-(Art!=null?8:0);
                if(routeStep<=4)return 0;if(routeStep<=34)return 0x2000;if(routeStep<=53)return 0x8000;if(routeStep<=63)return 0x2000;
                if(routeStep==69)session.ConfirmEdge();
                if(session.CanAct&&(int)session.Core.Snapshot()["item_count"]==1){equipmentButton.onClick.Invoke();equipButton.onClick.Invoke();autoEquipped=true;}
                return 0;
            }
            if(!session.CanAct)return 0;
            stairs++;return stairs<=9?0x1000:stairs<=61?0x8000:stairs<=121?0:stairs<=137?0x1000:stairs<=157?0x8000:stairs<=185?0x2000:0;
        }
        static byte[] Raw(JToken token){string s=(string)token;var b=new byte[s.Length/2];for(int i=0;i<b.Length;i++)b[i]=Convert.ToByte(s.Substring(i*2,2),16);return b;}
        public static Vector3 SourcePosition(byte[] raw,float height=0)=>new Vector3((SourceInteger.Word(raw,0)/16f-512)/32,height,-(SourceInteger.Word(raw,2)/16f-1536)/32);
        void Draw()
        {
            var s=session.Shown;var raw=Raw(s["player"]);player.position=SourcePosition(raw);player.rotation=Quaternion.Euler(0,90+45*SourceInteger.Word(raw,38),0);
            if(Art==null)actor.SetActive(!session.Marker);marker.SetActive(session.Marker);heading.gameObject.SetActive(Art==null||session.Marker);
            var decoration=Raw(s["decor"]);if(Art!=null)Art.Present(s,raw,decoration,session.Marker);else{cirrus.gameObject.SetActive((SourceInteger.Word(decoration,10)&0x8000)!=0);cirrus.position=SourcePosition(decoration,.3f);}
            if(Art!=null)effects.Present(s,s["spark"].Type==JTokenType.Null?null:Raw(s["spark"]));else{spark.gameObject.SetActive(s["spark"].Type!=JTokenType.Null);if(spark.gameObject.activeSelf)spark.position=SourcePosition(Raw(s["spark"]),1.3f);}
            dialoguePanel.SetActive(session.DialogueActive);if(session.DialogueActive){dialogueText.text=(string)session.Pages[session.Page]["zh_tw"];pageText.text=$"CIRRUS  /  {session.Page+1} · {session.Pages.Count}    Enter 繼續";}
            equipmentPanel.SetActive(session.Panel);weaponText.text="派克 / 武器\n"+((int)s["weapon"]==27?"Cirrus · 已裝備":(int)s["item_count"]==1?"持有 Cirrus · 未裝備":"尚未取得 Cirrus");
            equipButton.interactable=session.CanAct&&session.OptionAllowed(0);removeButton.interactable=session.CanAct&&session.OptionAllowed(1);
            var buttons=new[]{equipButton,removeButton,backButton};for(int i=0;i<3;i++)buttons[i].GetComponent<Image>().color=i==session.Selection?new Color(.35f,.31f,.18f):new Color(.14f,.24f,.28f);
            interactButton.interactable=!session.Paused&&!session.Panel&&(session.CanAct||session.DialogueActive);equipmentButton.interactable=session.CanAct||session.Panel;
            status.text=session.Notice!=""?session.Notice:session.Paused?"已暫停 · Space 繼續 / . 單步":session.Panel?"裝備面板 · 房內更新暫停":session.DialogueActive?"正在對話":(int)s["disabled"]!=0?"原作事件演出中":"自由探索 · 接近 Cirrus 並按 Enter";
            diagnosticPanel.SetActive(session.Diagnostic);diagnosticText.text=$"來源座標 {SourceInteger.Word(raw,0)}, {SourceInteger.Word(raw,2)}\n更新 {s["update"]} / 動畫 {SourceInteger.Word(raw,54)}\n故事 {s["story"]} / 武器 {s["weapon"]} / 持有 {s["item_count"]}\n核心獨立於模型、鏡頭、物理與渲染 FPS\n"+(Art==null?"灰模特殊動作尚未製作":"骨架姿勢："+Art.CurrentClip);
            float aspect=16f/9f,current=(float)Screen.width/Screen.height;view.rect=current>aspect?new Rect((1-aspect/current)/2,0,aspect/current,1):new Rect(0,(1-current/aspect)/2,1,current/aspect);
        }
        void ObserveQA()
        {
            if(autoUpdate+stairs>2500)throw new InvalidOperationException("U2 functional flow did not finish; log retained");
            string stage=session.Boundary?"boundary":session.DialogueActive?"dialogue":autoEquipped?"equipped":"initial";
            if(!shots.Contains(stage)&&!screenshotBusy){shots.Add(stage);if(shotDir!="")StartCoroutine(Capture(stage));}
            if(Art!=null&&presentationChecks.Add(Art.CurrentClip))
            {
                var before=session.Core.Snapshot();session.TogglePause();session.Tick(0);Draw();
                session.ToggleMarker();Draw();session.ToggleMarker();Draw();session.TogglePause();Draw();
                if(!JToken.DeepEquals(before,session.Core.Snapshot()))throw new InvalidDataException("Pause/mode changed core state");
            }
            if(Art!=null&&!screenshotBusy&&Art.CurrentClip.StartsWith("pickup_",StringComparison.Ordinal)&&!shots.Contains(Art.CurrentClip)){shots.Add(Art.CurrentClip);if(shotDir!="")StartCoroutine(Capture(Art.CurrentClip));}
            if(Art!=null&&!screenshotBusy)
            {
                var shown=session.Shown;var actorBytes=Raw(shown["player"]);string extra="";
                if(session.DialogueActive)extra="dialogue-page-"+session.Page;
                else if((SourceInteger.Word(actorBytes,6)&2)!=0)extra="walk-direction-"+SourceInteger.Word(actorBytes,38);
                if(reminderQA&&shown["effect"].Type!=JTokenType.Null&&!(bool)shown["effect"]["ended"])extra="expression-"+shown["effect"]["image"];
                if(extra!=""&&!shots.Contains(extra)){shots.Add(extra);if(shotDir!="")StartCoroutine(Capture(extra));}
            }
            if(reminderQA&&autoUpdate>103&&session.Confirmations>=2&&session.CanAct&&!screenshotBusy)
            {
                var state=session.Core.Snapshot();if((string)state["story"]!="01"||(int)state["weapon"]!=255||(int)state["item_count"]!=0)throw new InvalidDataException("Reminder changed item state");
                foreach(string required in new[]{"expression-0","expression-1","expression-2","expression-14","expression-15","dialogue-page-0","dialogue-page-1"})if(!shots.Contains(required))throw new InvalidDataException("Missing reminder view "+required);
                session.Reset();Draw();WriteReport(true,"");finished=true;Application.Quit(0);return;
            }
            if(session.Boundary&&!screenshotBusy)
            {
                if(Art!=null&&new[]{"pickup_35","pickup_36","pickup_37","pickup_38"}.Any(x=>!Art.Seen.Contains(x)))throw new InvalidDataException("Required skeletal pickup pose was missed");
                if(!shots.Contains("dialogue"))throw new InvalidDataException("Required dialogue capture was missed");
                var s=session.Core.Snapshot();if((int)s["weapon"]!=27||(string)s["story"]!="07")throw new InvalidDataException("Boundary equipment differs");
                int oldGeneration=session.Generation;session.Reset();session.SetDeviceResponse(oldGeneration,true,true);
                if(session.Loaded||session.Started||(int)session.Core.Snapshot()["weapon"]!=255)throw new InvalidDataException("Reset contamination");
                WriteReport(true,"");finished=true;Application.Quit(0);
            }
        }
        IEnumerator Capture(string stage)
        {
            screenshotBusy=true;yield return new WaitForEndOfFrame();
            RenderTexture target=null;Texture2D texture=null;var active=RenderTexture.active;
            try
            {
                // A hidden Windows helper has no reliable backbuffer. Render the actual
                // runtime camera and camera-space UI to an explicit target instead.
                target=new RenderTexture(Screen.width,Screen.height,24,RenderTextureFormat.ARGB32);target.Create();
                ui.renderMode=RenderMode.ScreenSpaceCamera;ui.worldCamera=view;ui.planeDistance=1;Canvas.ForceUpdateCanvases();
                RenderPipeline.SubmitRenderRequest(view,new UniversalRenderPipeline.SingleCameraRequest{destination=target});
                RenderTexture.active=target;texture=new Texture2D(target.width,target.height,TextureFormat.RGB24,false);
                texture.ReadPixels(new Rect(0,0,target.width,target.height),0,0);texture.Apply();
                File.WriteAllBytes(Path.Combine(shotDir,stage+".png"),texture.EncodeToPNG());
            }
            catch(Exception ex){Fail("Runtime render capture failed: "+ex);}
            finally
            {RenderTexture.active=active;ui.renderMode=RenderMode.ScreenSpaceOverlay;if(texture!=null)Destroy(texture);if(target!=null){target.Release();Destroy(target);}screenshotBusy=false;}
        }
        void VerifyUI()
        {
            removeButton.onClick.Invoke();
            if((int)session.Core.Snapshot()["weapon"]!=255||(int)session.Core.Snapshot()["item_count"]!=1)throw new InvalidDataException("UI remove failed");
            equipButton.onClick.Invoke();var equipped=session.Core.Snapshot();equipButton.onClick.Invoke();
            if((int)equipped["weapon"]!=27||(int)equipped["item_count"]!=0||!JToken.DeepEquals(equipped,session.Core.Snapshot()))throw new InvalidDataException("Repeated equip changed resources");
            backButton.onClick.Invoke();if(session.Panel)throw new InvalidDataException("UI cancel failed");
            session.FocusLost();var paused=session.Core.Snapshot();session.Tick(0x2000);Draw();
            if(!JToken.DeepEquals(paused,session.Core.Snapshot()))throw new InvalidDataException("Focus pause advanced core");session.TogglePause();uiVerified=true;
        }
        void WriteReport(bool passed,string error)
        {
            if(reportPath=="")return;
            var report=new JObject{["passed"]=passed,["error"]=error,["editor"]=Application.unityVersion,["scope"]=Art==null?"one PC-input pickup/equip/staircase graybox run and reset":"one source-driven skeletal pickup/equip/staircase run and reset",["real_audio_start"]=audioStartedObserved,["qa_route"]=reminderQA?"unowned-staircase-reminder":"pickup-equipment-stairs",["shots"]=new JArray(shots),["performance_tested"]=false,["final_art"]=false,["skeletal_art"]=Art!=null,["ui_semantic_checks"]=uiVerified,["pause_mode_clip_checks"]=new JArray(presentationChecks),["sampled_clips"]=Art==null?new JArray():new JArray(Art.Seen)};
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath)));File.WriteAllText(reportPath,report.ToString());
        }
        void Fail(string message){failure=message;Debug.LogError(message);WriteReport(false,message);if(qa)Application.Quit(1);}
        void OnGUI(){if(failure!="")GUI.Label(new Rect(20,20,Screen.width-40,Screen.height-40),"STARTUP REJECTED\n"+failure);}
        void OnApplicationFocus(bool focused){if(!focused&&session!=null&&!qa){session.FocusLost();voice.Pause();Barrier();}}
        void OnDestroy(){if(voice!=null)voice.Stop();foreach(var clip in clips.Values)Destroy(clip);}
    }
}

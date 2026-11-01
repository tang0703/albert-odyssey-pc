using System;
using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ao.UnityMigration
{
    // Explicit isolated art mode. It never constructs or advances a game core.
    public sealed class U4Preview : MonoBehaviour
    {
        public RoomArt Art;
        public string Output;
        Camera view;
        IEnumerator Start()
        {
            Application.runInBackground=true;Directory.CreateDirectory(Output);
            Art.Initialize(new GameObject("Art-only player anchor").transform);
            view=new GameObject("Art camera").AddComponent<Camera>();view.gameObject.AddComponent<UniversalAdditionalCameraData>();view.orthographic=true;view.orthographicSize=.78f;view.aspect=.8f;
            view.transform.position=new Vector3(0,1.25f,-3);view.transform.LookAt(new Vector3(0,.57f,0));view.backgroundColor=new Color(.045f,.055f,.06f);view.clearFlags=CameraClearFlags.SolidColor;
            var key=new GameObject("Warm art key").AddComponent<Light>();key.type=LightType.Directional;key.intensity=1.2f;key.color=new Color(1,.91f,.8f);key.transform.rotation=Quaternion.Euler(50,-30,0);key.shadows=LightShadows.Soft;
            RenderSettings.ambientLight=new Color(.35f,.38f,.41f);
            var ground=GameObject.CreatePrimitive(PrimitiveType.Cube);Destroy(ground.GetComponent<Collider>());ground.transform.position=new Vector3(0,-.025f,0);ground.transform.localScale=new Vector3(4,.04f,4);
            var mat=new Material(Shader.Find("Universal Render Pipeline/Lit"));mat.color=new Color(.13f,.15f,.16f);ground.GetComponent<Renderer>().sharedMaterial=mat;
            foreach(var direction in new[]{0,2,4,6})
            {
                Art.Preview("idle",0,direction);yield return new WaitForEndOfFrame();Capture("idle-"+direction);
            }
            foreach(string clip in new[]{"walk","pickup_35","pickup_36","pickup_37","pickup_38"})
            {
                int count=clip=="walk"?40:1;
                for(int frame=0;frame<count;frame++){Art.Preview(clip,frame/(float)count,2);yield return new WaitForEndOfFrame();Capture(clip+"-"+frame.ToString("D2"));}
            }
            File.WriteAllText(Path.Combine(Output,"preview.json"),new JObject{["passed"]=true,["scope"]="Isolated skeletal art preview; no gameplay state",["frames"]=48,["performance_tested"]=false}.ToString());Application.Quit(0);
        }
        void Capture(string name)
        {
            var rt=new RenderTexture(640,800,24);rt.Create();var previous=RenderTexture.active;Texture2D image=null;
            try{RenderPipeline.SubmitRenderRequest(view,new UniversalRenderPipeline.SingleCameraRequest{destination=rt});RenderTexture.active=rt;image=new Texture2D(640,800,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,640,800),0,0);image.Apply();File.WriteAllBytes(Path.Combine(Output,name+".png"),image.EncodeToPNG());}
            finally{RenderTexture.active=previous;if(image!=null)Destroy(image);rt.Release();Destroy(rt);}
        }
    }
}

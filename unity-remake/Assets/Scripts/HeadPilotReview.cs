using System;
using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
namespace Ao.UnityMigration
{
    // Static art only: no session, input, animation, physics or gameplay.
    public sealed class HeadPilotReview:MonoBehaviour
    {
        public GameObject Previous, Pilot;
        Camera view; string output;
        IEnumerator Start()
        {
            var args=Environment.GetCommandLineArgs();int at=Array.IndexOf(args,"--review-output");
            if(at<0){Application.Quit(1);yield break;}
            output=Path.GetFullPath(args[at+1]);if(Directory.Exists(output))throw new IOException("Preserve captures");Directory.CreateDirectory(output);
            Application.runInBackground=true;
            view=new GameObject("Static head camera").AddComponent<Camera>();view.gameObject.AddComponent<UniversalAdditionalCameraData>();
            view.orthographic=true;view.orthographicSize=.64f;view.nearClipPlane=.05f;view.farClipPlane=10;view.clearFlags=CameraClearFlags.SolidColor;view.backgroundColor=new Color(.035f,.045f,.052f);
            view.transform.position=new Vector3(0,.55f,-3);view.transform.LookAt(new Vector3(0,.5f,0));
            var key=new GameObject("Key").AddComponent<Light>();key.type=LightType.Directional;key.intensity=1.1f;key.shadows=LightShadows.None;key.transform.rotation=Quaternion.Euler(45,-30,0);
            var fill=new GameObject("Fill").AddComponent<Light>();fill.type=LightType.Directional;fill.intensity=.45f;fill.color=new Color(.92f,.96f,1);fill.transform.rotation=Quaternion.Euler(20,35,0);
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.32f,.32f,.32f);
            var pipeline=(UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;pipeline.shadowDistance=5;pipeline.shadowNormalBias=.08f;pipeline.shadowDepthBias=1;
            var clay=new Material(Shader.Find("Universal Render Pipeline/Lit"));clay.color=new Color(.66f,.64f,.59f);clay.SetFloat("_Smoothness",.25f);
            int count=0;
            foreach(bool old in new[]{true,false})
            {
                var pivot=new GameObject("Static portrait pivot");var model=Instantiate(old?Previous:Pilot,pivot.transform,false);
                var b=BoundsOf(model);model.transform.localScale*=1/b.size.y;b=BoundsOf(model);model.transform.position-=new Vector3(b.center.x,b.min.y,b.center.z);
                var renderers=model.GetComponentsInChildren<Renderer>();var original=new Material[renderers.Length][];
                for(int r=0;r<renderers.Length;r++)original[r]=renderers[r].sharedMaterials;
                foreach(bool untextured in new[]{true,false})
                {
                    for(int r=0;r<renderers.Length;r++)
                    {var materials=(Material[])original[r].Clone();if(untextured)for(int m=0;m<materials.Length;m++)materials[m]=clay;renderers[r].sharedMaterials=materials;}
                    foreach(bool warm in new[]{false,true})
                    {
                        key.color=warm?new Color(1,.9f,.76f):Color.white;
                        int d=0;foreach(string direction in new[]{"front","left","back","right","threequarter"})
                        {
                            pivot.transform.rotation=Quaternion.Euler(0,new[]{180,270,0,90,215}[d++],0);
                            yield return new WaitForEndOfFrame();
                            Capture((old?"v2":"pilot")+"-"+(untextured?"clay":"palette")+"-"+(warm?"warm":"neutral")+"-"+direction);count++;
                        }
                    }
                }
                Destroy(pivot);yield return null;
            }
            File.WriteAllText(Path.Combine(output,"review.json"),new JObject{["captures"]=count,["engine"]="Unity URP",["scope"]="head-only static art study; equal normalized head height",["animation_tested"]=false,["performance_tested"]=false,["gameplay_changed"]=false}.ToString());Application.Quit(0);
        }
        static Bounds BoundsOf(GameObject obj){var rs=obj.GetComponentsInChildren<Renderer>();if(rs.Length==0)throw new InvalidDataException("Empty head");var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;}
        void Capture(string name)
        {
            var target=new RenderTexture(900,900,24);target.Create();var previous=RenderTexture.active;Texture2D image=null;
            try{view.aspect=1;RenderPipeline.SubmitRenderRequest(view,new UniversalRenderPipeline.SingleCameraRequest{destination=target});RenderTexture.active=target;image=new Texture2D(900,900,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,900,900),0,0);image.Apply();File.WriteAllBytes(Path.Combine(output,name+".png"),image.EncodeToPNG());}
            finally{RenderTexture.active=previous;if(image!=null)Destroy(image);target.Release();Destroy(target);}
        }
    }
}

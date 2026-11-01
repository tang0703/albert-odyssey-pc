using System;
using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
namespace Ao.UnityMigration
{
    public sealed class CharacterReview:MonoBehaviour
    {
        public GameObject Player,OldPlayer,Room;
        public AnimationClip OldIdle;
        Camera view;string output;Light key,fill;GameObject room,ground;UniversalRenderPipelineAsset pipeline;
        IEnumerator Start()
        {
            var args=Environment.GetCommandLineArgs();int i=Array.IndexOf(args,"--review-output");
            if(i<0){Application.Quit(1);yield break;}output=Path.GetFullPath(args[i+1]);
            if(Directory.Exists(output))throw new IOException("Preserve previous review captures");Directory.CreateDirectory(output);
            Application.runInBackground=true;
            pipeline=(UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;
            room=Instantiate(Room);var rb=BoundsOf(room);room.transform.localScale=new Vector3(rb.center.x<0?-1:1,1,rb.center.z>0?-1:1);room.SetActive(false);
            view=new GameObject("C2 camera").AddComponent<Camera>();view.gameObject.AddComponent<UniversalAdditionalCameraData>();view.orthographic=true;view.backgroundColor=new Color(.035f,.045f,.052f);view.clearFlags=CameraClearFlags.SolidColor;
            key=new GameObject("C2 controlled key").AddComponent<Light>();key.type=LightType.Directional;key.shadows=LightShadows.Soft;key.transform.rotation=Quaternion.Euler(50,-30,0);
            fill=new GameObject("Portrait neutral fill only").AddComponent<Light>();fill.type=LightType.Directional;fill.color=new Color(.9f,.94f,1);fill.intensity=.28f;fill.transform.rotation=Quaternion.Euler(20,35,0);fill.shadows=LightShadows.None;
            RenderSettings.ambientMode=AmbientMode.Flat;
            ground=GameObject.CreatePrimitive(PrimitiveType.Cube);Destroy(ground.GetComponent<Collider>());ground.transform.position=new Vector3(0,-.025f,0);ground.transform.localScale=new Vector3(10,.04f,10);
            var gm=new Material(Shader.Find("Universal Render Pipeline/Lit"));gm.color=new Color(.14f,.16f,.18f);ground.GetComponent<Renderer>().material=gm;
            int captures=0;
            foreach(bool old in new[]{true,false})
            {
                string version=old?"old":"refined";var pivot=new GameObject("Static feet anchor");var model=Instantiate(old?OldPlayer:Player,pivot.transform,false);
                foreach(var a in model.GetComponentsInChildren<Animation>())a.enabled=false;
                foreach(var a in model.GetComponentsInChildren<Animator>()){a.applyRootMotion=false;a.enabled=false;}
                if(old)OldIdle.SampleAnimation(model,0);
                model.transform.localScale*=1.125f/BoundsOf(model).size.y;model.transform.position-=Vector3.up*BoundsOf(model).min.y;
                foreach(bool warm in new[]{false,true})
                {
                    fill.enabled=true;pipeline.shadowDistance=6;pipeline.shadowNormalBias=.15f;pipeline.shadowDepthBias=2;view.nearClipPlane=.05f;view.farClipPlane=10;
                    Lighting(warm);string light=warm?"warm":"neutral";
                    view.orthographicSize=.64f;view.transform.position=new Vector3(0,1.05f,-3);view.transform.LookAt(new Vector3(0,.56f,0));
                    int d=0;foreach(string direction in new[]{"front","left","back","right"})
                    {
                        pivot.transform.rotation=Quaternion.Euler(0,new[]{180,90,0,270}[d++],0);yield return new WaitForEndOfFrame();Capture(version+"-"+light+"-"+direction,800,1000);captures++;
                    }
                    pivot.transform.rotation=Quaternion.Euler(0,180,0);view.orthographicSize=.24f;view.transform.position=new Vector3(0,.86f,-3);view.transform.LookAt(new Vector3(0,.80f,0));
                    yield return new WaitForEndOfFrame();Capture(version+"-"+light+"-face",900,900);captures++;
                    if(!old&&!warm)
                    {
                        key.shadows=LightShadows.None;yield return new WaitForEndOfFrame();Capture("diagnostic-no-shadow",900,900);
                        foreach(var r in model.GetComponentsInChildren<Renderer>())foreach(var m in r.materials)m.SetFloat("_BumpScale",0);
                        yield return new WaitForEndOfFrame();Capture("diagnostic-no-shadow-no-normal",900,900);
                        foreach(var r in model.GetComponentsInChildren<Renderer>())foreach(var m in r.materials)m.SetFloat("_BumpScale",1);
                        key.shadows=LightShadows.Soft;
                    }
                }
                Lighting(true);fill.enabled=false;ground.SetActive(false);room.SetActive(true);pivot.transform.position=new Vector3((718-512)/32f,0,-(1626-1536)/32f);
                pipeline.shadowDistance=25;pipeline.shadowNormalBias=1;pipeline.shadowDepthBias=1;view.nearClipPlane=.3f;view.farClipPlane=1000;
                view.orthographicSize=5.7f;view.transform.rotation=Quaternion.Euler(45,0,0);view.transform.position=new Vector3(7,0,-4)-view.transform.forward*16;
                yield return new WaitForEndOfFrame();Capture(version+"-room",1920,1080);captures++;
                room.SetActive(false);ground.SetActive(true);Destroy(pivot);yield return null;
            }
            File.WriteAllText(Path.Combine(output,"review.json"),new JObject{["passed"]=true,["scope"]="C2 static Unity URP review, no gameplay or animation acceptance",["captures"]=captures,["diagnostic_captures"]=2,["height"]=1.125,["room_camera_pitch"]=45,["lighting"]="Identical old/new portrait rig: neutral or warm key plus 0.28 fill. Room uses original warm key, no fill.",["portrait_shadow_distance"]=6,["portrait_shadow_normal_bias"]=.15,["portrait_shadow_depth_bias"]=2,["room_shadow_distance"]=25,["room_shadow_bias"]=1,["performance_tested"]=false}.ToString());Application.Quit(0);
        }
        void Lighting(bool warm){key.color=warm?new Color(1,.91f,.8f):Color.white;key.intensity=1.15f;RenderSettings.ambientLight=warm?new Color(.29f,.30f,.32f):new Color(.32f,.32f,.32f);}
        static Bounds BoundsOf(GameObject obj){var renderers=obj.GetComponentsInChildren<Renderer>();if(renderers.Length==0)throw new InvalidDataException("Empty geometry");var b=renderers[0].bounds;foreach(var r in renderers)b.Encapsulate(r.bounds);return b;}
        void Capture(string name,int width,int height)
        {
            var target=new RenderTexture(width,height,24);target.Create();var previous=RenderTexture.active;Texture2D image=null;
            try{view.aspect=(float)width/height;RenderPipeline.SubmitRenderRequest(view,new UniversalRenderPipeline.SingleCameraRequest{destination=target});RenderTexture.active=target;image=new Texture2D(width,height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(Path.Combine(output,name+".png"),image.EncodeToPNG());}
            finally{RenderTexture.active=previous;if(image!=null)Destroy(image);target.Release();Destroy(target);}
        }
    }
}

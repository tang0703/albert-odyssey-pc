using System;
using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
namespace Ao.UnityMigration
{
    // Static review only: no RoomSession, input, physics, Animator or animation sampling.
    public sealed class BodyFitReview:MonoBehaviour
    {
        public GameObject Player,Room;
        Camera cameraView;string output;
        IEnumerator Start()
        {
            var args=Environment.GetCommandLineArgs();int at=Array.IndexOf(args,"--review-output");if(at<0){Application.Quit(1);yield break;}
            output=Path.GetFullPath(args[at+1]);if(Directory.Exists(output))throw new IOException("Preserve captures");Directory.CreateDirectory(output);
            Application.runInBackground=true;
            var model=Instantiate(Player);var bounds=BoundsOf(model);
            if(Mathf.Abs(bounds.size.y-1.125f)>.01f||Mathf.Abs(bounds.min.y)>.01f)throw new InvalidDataException("Height or feet anchor wrong");
            // No automatic normalization: preserve the explicit approved-head/body fitting.
            var pivot=new GameObject("Feet origin");model.transform.SetParent(pivot.transform,false);
            cameraView=new GameObject("Static camera").AddComponent<Camera>();cameraView.gameObject.AddComponent<UniversalAdditionalCameraData>();cameraView.orthographic=true;cameraView.nearClipPlane=.05f;cameraView.farClipPlane=100;cameraView.clearFlags=CameraClearFlags.SolidColor;cameraView.backgroundColor=new Color(.035f,.045f,.052f);
            var key=new GameObject("Key").AddComponent<Light>();key.type=LightType.Directional;key.intensity=1.1f;key.shadows=LightShadows.None;key.transform.rotation=Quaternion.Euler(45,-30,0);
            var fill=new GameObject("Fill").AddComponent<Light>();fill.type=LightType.Directional;fill.intensity=.45f;fill.color=new Color(.92f,.96f,1);fill.transform.rotation=Quaternion.Euler(20,35,0);
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.32f,.32f,.32f);
            var pipeline=(UniversalRenderPipelineAsset)GraphicsSettings.currentRenderPipeline;pipeline.shadowDistance=5;pipeline.shadowNormalBias=.08f;pipeline.shadowDepthBias=1;
            var floor=GameObject.CreatePrimitive(PrimitiveType.Cube);Destroy(floor.GetComponent<Collider>());floor.transform.position=new Vector3(0,-.022f,0);floor.transform.localScale=new Vector3(10,.04f,10);
            var fm=new Material(Shader.Find("Universal Render Pipeline/Lit"));fm.color=new Color(.14f,.16f,.18f);floor.GetComponent<Renderer>().material=fm;
            int captures=0;
            foreach(bool warm in new[]{false,true})
            {
                string light=warm?"warm":"neutral";key.color=warm?new Color(1,.9f,.76f):Color.white;
                cameraView.orthographicSize=.65f;cameraView.transform.position=new Vector3(0,.72f,-3);cameraView.transform.LookAt(new Vector3(0,.56f,0));
                int d=0;foreach(string direction in new[]{"front","left","back","right","threequarter"})
                {pivot.transform.rotation=Quaternion.Euler(0,new[]{180,270,0,90,215}[d++],0);yield return new WaitForEndOfFrame();Capture(light+"-"+direction,1000,1200);captures++;}
                pivot.transform.rotation=Quaternion.Euler(0,180,0);cameraView.transform.position=new Vector3(0,2.68f,-2.12f);cameraView.transform.LookAt(new Vector3(0,.56f,0));
                yield return new WaitForEndOfFrame();Capture(light+"-top45",1000,1200);captures++;
                foreach(var crop in new[]{new Vector3(.65f,.24f,0),new Vector3(.45f,.23f,0),new Vector3(.12f,.22f,0)})
                {cameraView.orthographicSize=crop.y;cameraView.transform.position=new Vector3(0,crop.x,-3);cameraView.transform.LookAt(new Vector3(0,crop.x,0));yield return new WaitForEndOfFrame();Capture(light+"-"+(crop.x>.6f?"neckline":crop.x>.3f?"waist":"boots"),1000,900);captures++;}
            }
            var renderers=model.GetComponentsInChildren<Renderer>();var old=new Material[renderers.Length][];var clay=new Material(Shader.Find("Universal Render Pipeline/Lit"));clay.color=new Color(.65f,.63f,.58f);clay.SetFloat("_Smoothness",.2f);
            for(int i=0;i<renderers.Length;i++){old[i]=renderers[i].sharedMaterials;var m=new Material[old[i].Length];for(int j=0;j<m.Length;j++)m[j]=old[i][j].HasProperty("_AlphaClip")&&old[i][j].GetFloat("_AlphaClip")>.5f&&old[i][j].color.a==0?old[i][j]:clay;renderers[i].sharedMaterials=m;}
            key.color=Color.white;cameraView.orthographicSize=.65f;cameraView.transform.position=new Vector3(0,.72f,-3);cameraView.transform.LookAt(new Vector3(0,.56f,0));
            int side=0;foreach(string dir in new[]{"front","left","back","right"}){pivot.transform.rotation=Quaternion.Euler(0,new[]{180,270,0,90}[side++],0);yield return new WaitForEndOfFrame();Capture("clay-"+dir,1000,1200);captures++;}
            for(int i=0;i<renderers.Length;i++)renderers[i].sharedMaterials=old[i];
            floor.SetActive(false);var room=Instantiate(Room);var rb=BoundsOf(room);room.transform.localScale=new Vector3(rb.center.x<0?-1:1,1,rb.center.z>0?-1:1);
            key.color=new Color(1,.91f,.8f);key.shadows=LightShadows.Soft;fill.enabled=false;pipeline.shadowDistance=25;pipeline.shadowNormalBias=1;pipeline.shadowDepthBias=1;
            pivot.transform.position=new Vector3((718-512)/32f,0,-(1626-1536)/32f);pivot.transform.rotation=Quaternion.Euler(0,215,0);
            cameraView.orthographicSize=5.7f;cameraView.transform.rotation=Quaternion.Euler(45,0,0);cameraView.transform.position=new Vector3(7,0,-4)-cameraView.transform.forward*16;
            yield return new WaitForEndOfFrame();Capture("room-scale-45",1920,1080);captures++;
            File.WriteAllText(Path.Combine(output,"review.json"),new JObject{["engine"]="Unity URP",["captures"]=captures,["height"]=bounds.size.y,["static_room_context_only"]=true,["animation_tested"]=false,["performance_tested"]=false,["gameplay_changed"]=false}.ToString());Application.Quit(0);
        }
        static Bounds BoundsOf(GameObject obj){var r=obj.GetComponentsInChildren<Renderer>();if(r.Length==0)throw new InvalidDataException("Missing model");var b=r[0].bounds;foreach(var a in r)b.Encapsulate(a.bounds);return b;}
        void Capture(string name,int width,int height)
        {var target=new RenderTexture(width,height,24);target.Create();var previous=RenderTexture.active;Texture2D image=null;
            try{cameraView.aspect=(float)width/height;RenderPipeline.SubmitRenderRequest(cameraView,new UniversalRenderPipeline.SingleCameraRequest{destination=target});RenderTexture.active=target;image=new Texture2D(width,height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(Path.Combine(output,name+".png"),image.EncodeToPNG());}
            finally{RenderTexture.active=previous;if(image!=null)Destroy(image);target.Release();Destroy(target);}}
    }
}

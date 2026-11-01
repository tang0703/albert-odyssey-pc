using System;
using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ao.UnityMigration
{
    // Static U3 art review, deliberately disconnected from the gameplay core.
    public sealed class U3Review : MonoBehaviour
    {
        public GameObject Room,Player;
        public Material Lit;
        public string ArtVersion;
        Camera view;
        string output;
        GameObject room,player;
        IEnumerator Start()
        {
            var args=Environment.GetCommandLineArgs();int at=Array.IndexOf(args,"--u3-output");
            if(at<0){Debug.LogError("Review output required");Application.Quit(1);yield break;}
            output=Path.GetFullPath(args[at+1]);Directory.CreateDirectory(output);Application.runInBackground=true;Application.targetFrameRate=60;
            room=Instantiate(Room);player=new GameObject("Player orientation pivot");var model=Instantiate(Player);model.transform.SetParent(player.transform,false);ConvertMaterials(room);ConvertMaterials(player);
            float modelScale=1.125f/BoundsOf(player).size.y;model.transform.localScale*=modelScale;
            var bounds=BoundsOf(room);
            // Blender FBX handedness is normalized explicitly for the same XZ plan.
            float sx=bounds.center.x<0?-1:1,sz=bounds.center.z>0?-1:1;
            room.transform.localScale=new Vector3(sx,1,sz);
            player.transform.position=new Vector3((718-512)/32f,0,-(1626-1536)/32f);
            view=new GameObject("U3 fixed orthographic 45 degree camera").AddComponent<Camera>();view.gameObject.AddComponent<UniversalAdditionalCameraData>();view.orthographic=true;view.orthographicSize=5.1f;view.aspect=16f/9f;
            view.clearFlags=CameraClearFlags.SolidColor;view.backgroundColor=new Color(.035f,.045f,.052f);
            view.transform.rotation=Quaternion.Euler(45,0,0);view.transform.position=new Vector3(7,0,-4)-view.transform.forward*17;
            Light key=new GameObject("Warm key").AddComponent<Light>();key.type=LightType.Directional;key.color=new Color(1,.91f,.8f);key.intensity=1.4f;key.shadows=LightShadows.Soft;key.transform.rotation=Quaternion.Euler(50,-30,0);
            Light fill=new GameObject("Soft cool fill").AddComponent<Light>();fill.type=LightType.Directional;fill.color=new Color(.65f,.76f,1);fill.intensity=.45f;fill.transform.rotation=Quaternion.Euler(70,150,0);
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.4f,.36f,.29f);
            yield return null;yield return new WaitForEndOfFrame();
            Capture("unity-room",1920,1080);
            room.SetActive(false);player.transform.position=Vector3.zero;
            view.orthographicSize=.73f;view.aspect=.8f;view.transform.position=new Vector3(0,1.3f,-3);view.transform.LookAt(new Vector3(0,.56f,0));
            int i=0;foreach(string direction in new[]{"front","left","right","back"})
            {
                player.transform.rotation=Quaternion.Euler(0,new[]{180f,90f,270f,0f}[i++],0);yield return new WaitForEndOfFrame();Capture("unity-"+direction,800,1000);
            }
            File.WriteAllText(Path.Combine(output,"review.json"),new JObject{["stage"]="U3 draft, pending approval",["art_version"]=ArtVersion,["editor"]=Application.unityVersion,["renderer"]="URP Universal Renderer",["room_axis_sign_x"]=sx,["room_axis_sign_z"]=sz,["player_bounds_height"]=BoundsOf(player).size.y,["source_gameplay_test"]=false,["performance_tested"]=false,["note"]="Static geometric appearance preview. No rig or animation acceptance."}.ToString());
            Application.Quit(0);
        }
        void ConvertMaterials(GameObject root)
        {
            foreach(var renderer in root.GetComponentsInChildren<Renderer>())
            {
                var materials=renderer.sharedMaterials;
                for(int i=0;i<materials.Length;i++)
                {
                    var old=materials[i];var m=new Material(Lit);m.name=old.name+" URP draft";m.color=old.HasProperty("_Color")?Color.Lerp(old.color.linear,old.color,.3f):Color.gray;
                    m.SetFloat("_Smoothness",.25f);if(old.name.Contains("Brass")||old.name.Contains("metal")){m.SetFloat("_Metallic",.65f);m.SetFloat("_Smoothness",.5f);}materials[i]=m;
                }
                renderer.sharedMaterials=materials;
            }
        }
        static Bounds BoundsOf(GameObject root)
        {var renderers=root.GetComponentsInChildren<Renderer>();var b=renderers[0].bounds;foreach(var r in renderers)b.Encapsulate(r.bounds);return b;}
        void Capture(string name,int width,int height)
        {
            RenderTexture target=null;Texture2D image=null;var active=RenderTexture.active;
            try
            {
                target=new RenderTexture(width,height,24,RenderTextureFormat.ARGB32);target.Create();view.aspect=(float)width/height;
                RenderPipeline.SubmitRenderRequest(view,new UniversalRenderPipeline.SingleCameraRequest{destination=target});
                RenderTexture.active=target;image=new Texture2D(width,height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(Path.Combine(output,name+".png"),image.EncodeToPNG());
            }
            catch(Exception e){Debug.LogError(e);Application.Quit(1);}
            finally{RenderTexture.active=active;if(image!=null)Destroy(image);if(target!=null){target.Release();Destroy(target);}}
        }
    }
}

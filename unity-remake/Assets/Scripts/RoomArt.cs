using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Ao.SourceContracts;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Ao.UnityMigration
{
    // Models only consume aligned presentation state; they never own a core reference.
    public sealed class RoomArt : MonoBehaviour
    {
        public GameObject PlayerModel,RoomModel,CirrusModel;
        public AnimationClip[] Clips;
        GameObject model,heldSword,room,cirrus;
        Transform player;
        Transform hand;
        SkinnedMeshRenderer skinRenderer;
        Dictionary<string,AnimationClip> clips;
        public readonly HashSet<string> Seen=new HashSet<string>();
        public string CurrentClip {get;private set;}="";
        public void Preview(string clip,float phase,int heading)
        {
            room.SetActive(false);cirrus.SetActive(false);model.SetActive(true);
            clips[clip].SampleAnimation(model,phase*clips[clip].length);
            player.rotation=Quaternion.Euler(0,90+45*heading,0);
            heldSword.SetActive(clip=="pickup_38");PlaceHeldSword();
        }
        public void Initialize(Transform anchor)
        {
            player=anchor;room=Instantiate(RoomModel);
            Bounds roomBounds=BoundsOf(room);room.transform.localScale=new Vector3(roomBounds.center.x<0?-1:1,1,roomBounds.center.z>0?-1:1);
            model=Instantiate(PlayerModel,player,false);
            foreach(var a in model.GetComponentsInChildren<Animator>()){a.applyRootMotion=false;a.enabled=false;}
            foreach(var a in model.GetComponentsInChildren<Animation>())a.enabled=false;
            clips=new Dictionary<string,AnimationClip>();
            foreach(string name in new[]{"idle","walk","pickup_35","pickup_36","pickup_37","pickup_38"})
            {
                var found=Clips.Where(c=>c.name==name||c.name.EndsWith("|"+name,StringComparison.Ordinal)).ToArray();
                if(found.Length!=1)throw new InvalidDataException("Required clip missing or ambiguous: "+name);
                clips.Add(name,found[0]);
            }
            // FBX rest bounds can describe the centimetre bind pose before animation
            // converts the skeleton. Normalize the evaluated rest mesh, never stale bounds.
            clips["idle"].SampleAnimation(model,0);
            Bounds? evaluated=null;
            foreach(var renderer in model.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var mesh=new Mesh();renderer.BakeMesh(mesh);
                foreach(var vertex in mesh.vertices){var point=renderer.transform.TransformPoint(vertex);if(evaluated==null)evaluated=new Bounds(point,Vector3.zero);else{var b=evaluated.Value;b.Encapsulate(point);evaluated=b;}}
                renderer.localBounds=mesh.bounds;Destroy(mesh);renderer.updateWhenOffscreen=true;
            }
            if(evaluated==null||evaluated.Value.size.y<=0)throw new InvalidDataException("Empty evaluated rest mesh");
            model.transform.localScale*=1.125f/evaluated.Value.size.y;
            skinRenderer=model.GetComponentInChildren<SkinnedMeshRenderer>();
            Debug.Log("U4 evaluated rest height="+evaluated.Value.size.y+" scale="+model.transform.localScale);
            cirrus=Instantiate(CirrusModel);
            hand=model.GetComponentsInChildren<Transform>().Single(t=>t.name=="hand.R");
            heldSword=Instantiate(CirrusModel);heldSword.SetActive(false);
        }
        public void Present(JObject state,byte[] actor,byte[] decor,bool marker)
        {
            AppearancePose pose=AppearancePose.Select(actor,(int)state["update"]);
            // SampleAnimation writes only imported model descendants. Source anchor is outside it.
            clips[pose.Clip].SampleAnimation(model,pose.Phase*clips[pose.Clip].length);
            player.rotation=Quaternion.Euler(0,90+45*pose.Heading,0);
            model.SetActive(!marker);heldSword.SetActive(!marker&&pose.RaisedSword);PlaceHeldSword();
            cirrus.SetActive((SourceInteger.Word(decor,10)&0x8000)!=0);
            cirrus.transform.position=RoomWorkbench.SourcePosition(decor,.65f)+Vector3.back*.125f;
            cirrus.transform.rotation=Quaternion.Euler(0,90,90);
            CurrentClip=pose.Clip;
            var height=skinRenderer.bounds.size.y;
            if(height<.5f||height>2)throw new InvalidDataException("Evaluated character height invalid: "+height);
            if(Seen.Add(pose.Clip))Debug.Log("U4 sampled "+pose.Clip+" bounds="+BoundsOf(model)+" anchor="+player.position+" model="+model.transform.localPosition+" / "+model.transform.localScale);
        }
        public static Bounds BoundsOf(GameObject root)
        {var r=root.GetComponentsInChildren<Renderer>();if(r.Length==0)throw new InvalidDataException("Empty model");var b=r[0].bounds;foreach(var item in r)b.Encapsulate(item.bounds);return b;}
        void PlaceHeldSword()
        {
            // The source raised pose holds the blade vertically, above the hand.
            // An independent socket avoids inheriting the FBX hand's local unit/axis basis.
            heldSword.transform.position=hand.TransformPoint(new Vector3(0,.025f,0))+Vector3.up*.08f;
            heldSword.transform.rotation=player.rotation*CirrusModel.transform.rotation;
        }
        void OnDestroy(){if(room!=null)Destroy(room);if(cirrus!=null)Destroy(cirrus);if(heldSword!=null)Destroy(heldSword);}
    }
}

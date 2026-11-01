using System;
using System.IO;
using Ao.SourceContracts;
using Newtonsoft.Json.Linq;
using TMPro;
using UnityEngine;

namespace Ao.UnityMigration
{
    // Original effect images choose the shape/visibility; no particle-system clock.
    public sealed class SourceEffects3D : MonoBehaviour
    {
        Transform bubble,spark;
        TextMeshPro mark;
        Material pale,gold;
        static GameObject Primitive(string name,PrimitiveType type,Transform parent,Vector3 scale,Material material)
        {var go=GameObject.CreatePrimitive(type);go.name=name;Destroy(go.GetComponent<Collider>());go.transform.SetParent(parent,false);go.transform.localScale=scale;go.GetComponent<Renderer>().sharedMaterial=material;return go;}
        public void Initialize(TMP_FontAsset font,Material baseMaterial)
        {
            pale=new Material(baseMaterial);pale.color=new Color(.9f,.97f,1);gold=new Material(baseMaterial);gold.color=new Color(1,.82f,.24f);
            bubble=new GameObject("Source expression bubble").transform;bubble.SetParent(transform,false);bubble.rotation=Quaternion.Euler(45,0,0);
            Primitive("Expression volume",PrimitiveType.Sphere,bubble,new Vector3(.32f,.3f,.06f),pale);
            mark=new GameObject("Source exclamation",typeof(TextMeshPro)).GetComponent<TextMeshPro>();mark.transform.SetParent(bubble,false);mark.transform.localPosition=new Vector3(0,0,-.055f);mark.font=font;mark.text="!";mark.fontSize=2.7f;mark.alignment=TextAlignmentOptions.Center;mark.color=new Color(.8f,.05f,.06f);mark.rectTransform.sizeDelta=new Vector2(.3f,.3f);
            spark=new GameObject("Source story sparkle").transform;spark.SetParent(transform,false);spark.rotation=Quaternion.Euler(45,0,0);
            Primitive("Star horizontal",PrimitiveType.Cube,spark,new Vector3(.4f,.035f,.035f),gold);
            Primitive("Star vertical",PrimitiveType.Cube,spark,new Vector3(.035f,.4f,.035f),gold);
            Primitive("Star center",PrimitiveType.Sphere,spark,new Vector3(.1f,.1f,.08f),pale);
            bubble.gameObject.SetActive(false);spark.gameObject.SetActive(false);
        }
        public void Present(JObject state,byte[] sparkle)
        {
            var effect=state["effect"];bool show=effect!=null&&effect.Type!=JTokenType.Null&&!(bool)effect["ended"]&&(int)effect["flags"]!=0;
            bubble.gameObject.SetActive(show);
            if(show)
            {
                int image=(int)effect["image"];if(image!=0&&image!=1&&image!=2&&image!=14&&image!=15)throw new InvalidDataException("Unknown expression pose "+image);
                var xy=state["effect_xy"];bubble.position=new Vector3(((int)xy[0]/16f-512)/32,1.32f,-((int)xy[1]/16f-1536)/32);
                float size=image==0?.35f:image==1?.65f:1; bubble.localScale=Vector3.one*size;mark.gameObject.SetActive(image>=14);
            }
            bool showSpark=sparkle!=null&&SourceInteger.Word(sparkle,52)!=127;spark.gameObject.SetActive(showSpark);
            if(showSpark)
            {
                int image=SourceInteger.Word(sparkle,52);if(image<32||image>44||image==43)throw new InvalidDataException("Unknown sparkle pose");
                spark.position=RoomWorkbench.SourcePosition(sparkle,1.35f);spark.localScale=Vector3.one*(.45f+(image-32)/12f*.6f);
            }
        }
        void OnDestroy(){if(pale!=null)Destroy(pale);if(gold!=null)Destroy(gold);}
    }
}

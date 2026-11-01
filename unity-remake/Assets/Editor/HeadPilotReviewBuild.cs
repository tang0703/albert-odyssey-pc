using System;
using System.IO;
using System.Linq;
using Ao.SourceContracts;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
namespace Ao.UnityMigration.Editor
{
    public static class HeadPilotReviewBuild
    {
        const string Folder="Assets/HeadPilotGenerated";
        public static void Run()
        {
            var args=Environment.GetCommandLineArgs();string output=args[Array.IndexOf(args,"-reviewOutput")+1];string art=Path.GetFullPath(args[Array.IndexOf(args,"-headArt")+1]);
            if(Directory.Exists(output))throw new IOException("Preserve old builds");
            var manifest=JObject.Parse(File.ReadAllText(Path.Combine(art,"unity-inputs.json")));
            foreach(var p in ((JObject)manifest["files"]).Properties())if(SourceGuard.Hash(File.ReadAllBytes(SourceGuard.SafePath(art,p.Name)))!=(string)p.Value)throw new InvalidDataException("Changed pilot asset "+p.Name);
            Directory.CreateDirectory(Folder);var palette=JObject.Parse(File.ReadAllText(Path.Combine(art,"palette.json")));
            bool eyeColor=Array.IndexOf(args,"-eyeColorReview")>=0;
            if(eyeColor&&(bool?)manifest["require_textures"]!=true)throw new InvalidDataException("Textured head contract required");
            if(eyeColor)foreach(var required in new[]{"old-head.fbx","head-palette.fbx","palette.json","head-basecolor.png","eye-basecolor.png"})
                if(manifest["files"]?[required]==null)throw new InvalidDataException("Unpinned required head asset "+required);
            var prefabs=new GameObject[2];int n=0;
            foreach(string name in new[]{"old-head","head-palette"})
            {
                string path=Folder+"/"+name+".fbx";File.Copy(Path.Combine(art,name+".fbx"),path,true);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                var importer=(ModelImporter)AssetImporter.GetAtPath(path);importer.importAnimation=false;importer.SaveAndReimport();
                var instance=UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(path));
                if(eyeColor&&name=="head-palette")foreach(var filter in instance.GetComponentsInChildren<MeshFilter>())
                    if(filter.sharedMesh==null||filter.sharedMesh.uv.Length!=filter.sharedMesh.vertexCount||filter.sharedMesh.uv.Any(uv=>float.IsNaN(uv.x)||float.IsNaN(uv.y)||float.IsInfinity(uv.x)||float.IsInfinity(uv.y)))throw new InvalidDataException("Missing or invalid head UV");
                foreach(var r in instance.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(m=>{
                    var entry=palette[m.name];if(entry==null)throw new InvalidDataException("Unknown material "+m.name);
                    var rgb=(JArray)entry["linear_color"];var material=new Material(Shader.Find("Universal Render Pipeline/Lit"));material.name=m.name;
                    material.color=new Color((float)rgb[0],(float)rgb[1],(float)rgb[2],(float)rgb[3]).gamma;material.SetFloat("_Smoothness",1-(float)entry["roughness"]);
                    if((bool?)entry["alpha_clip"]==true){material.SetFloat("_AlphaClip",1);material.SetFloat("_Cutoff",.5f);material.EnableKeyword("_ALPHATEST_ON");material.SetOverrideTag("RenderType","TransparentCutout");material.renderQueue=(int)RenderQueue.AlphaTest;}
                    string textureName=(string)entry["base_texture"];
                    if(eyeColor&&name=="head-palette"&&string.IsNullOrEmpty(textureName))throw new InvalidDataException("Missing base texture for "+m.name);
                    if(!string.IsNullOrEmpty(textureName))
                    {
                        if(manifest["files"][textureName]==null)throw new InvalidDataException("Unapproved texture "+textureName);
                        string texturePath=Folder+"/"+Path.GetFileName(textureName);File.Copy(SourceGuard.SafePath(art,textureName),texturePath,true);AssetDatabase.ImportAsset(texturePath,ImportAssetOptions.ForceSynchronousImport);
                        var ti=(TextureImporter)AssetImporter.GetAtPath(texturePath);ti.textureType=TextureImporterType.Default;ti.sRGBTexture=true;ti.maxTextureSize=2048;ti.textureCompression=TextureImporterCompression.Uncompressed;ti.wrapMode=TextureWrapMode.Clamp;ti.SaveAndReimport();
                        var texture=AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath);if(texture==null||texture.width!=2048||texture.height!=2048)throw new InvalidDataException("Invalid base texture "+textureName);material.SetTexture("_BaseMap",texture);
                    }
                    AssetDatabase.CreateAsset(material,Folder+"/Mat-"+Guid.NewGuid().ToString("N")+".mat");material.name=m.name;EditorUtility.SetDirty(material);return material;
                }).ToArray();
                prefabs[n++]=PrefabUtility.SaveAsPrefabAsset(instance,Folder+"/"+name+".prefab");UnityEngine.Object.DestroyImmediate(instance);
            }
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);var review=new GameObject("Static head pilot").AddComponent<HeadPilotReview>();review.Previous=prefabs[0];review.Pilot=prefabs[1];
            if(Array.IndexOf(args,"-faceReview")>=0){review.PreviousLabel="previous";review.PilotLabel="face";review.FaceCloseups=true;}
            if(Array.IndexOf(args,"-tripoReview")>=0){review.PreviousLabel="previous";review.PilotLabel="tripo";review.FaceCloseups=true;review.ClayOnly=true;}
            if(eyeColor){review.PreviousLabel="previous";review.PilotLabel="eye-color";review.FaceCloseups=true;review.ClayOnly=false;review.EyeColorReview=true;}
            var original=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");var pipeline=UnityEngine.Object.Instantiate(original);pipeline.msaaSampleCount=4;
            var settings=new SerializedObject(pipeline);settings.FindProperty("m_SoftShadowsSupported").boolValue=true;settings.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline,Folder+"/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            string scenePath=Folder+"/Review.unity";EditorSceneManager.SaveScene(scene,scenePath);AssetDatabase.SaveAssets();
            BuildReport result;
            try{result=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{scenePath},locationPathName=Path.Combine(output,"Head-Pilot-Review.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});}
            finally{GraphicsSettings.defaultRenderPipeline=original;QualitySettings.renderPipeline=original;AssetDatabase.SaveAssets();}
            if(result.summary.result!=BuildResult.Succeeded)throw new Exception("Head review build failed");
            File.WriteAllText(Path.Combine(output,"review-build.json"),new JObject{["passed"]=true,["scope"]="local head-only static art review",["face_review"]=Array.IndexOf(args,"-faceReview")>=0,["tripo_review"]=Array.IndexOf(args,"-tripoReview")>=0,["eye_color_review"]=eyeColor,["inputs_sha256"]=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,"unity-inputs.json"))),["performance_tested"]=false}.ToString());
        }
    }
}

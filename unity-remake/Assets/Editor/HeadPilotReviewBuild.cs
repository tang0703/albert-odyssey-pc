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
            var prefabs=new GameObject[2];int n=0;
            foreach(string name in new[]{"old-head","head-palette"})
            {
                string path=Folder+"/"+name+".fbx";File.Copy(Path.Combine(art,name+".fbx"),path,true);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                var importer=(ModelImporter)AssetImporter.GetAtPath(path);importer.importAnimation=false;importer.SaveAndReimport();
                var instance=UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(path));
                foreach(var r in instance.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(m=>{
                    var entry=palette[m.name];if(entry==null)throw new InvalidDataException("Unknown material "+m.name);
                    var rgb=(JArray)entry["linear_color"];var material=new Material(Shader.Find("Universal Render Pipeline/Lit"));material.name=m.name;
                    material.color=new Color((float)rgb[0],(float)rgb[1],(float)rgb[2],1).gamma;material.SetFloat("_Smoothness",1-(float)entry["roughness"]);
                    AssetDatabase.CreateAsset(material,Folder+"/Mat-"+Guid.NewGuid().ToString("N")+".mat");return material;
                }).ToArray();
                prefabs[n++]=PrefabUtility.SaveAsPrefabAsset(instance,Folder+"/"+name+".prefab");UnityEngine.Object.DestroyImmediate(instance);
            }
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);var review=new GameObject("Static head pilot").AddComponent<HeadPilotReview>();review.Previous=prefabs[0];review.Pilot=prefabs[1];
            if(Array.IndexOf(args,"-faceReview")>=0){review.PreviousLabel="previous";review.PilotLabel="face";review.FaceCloseups=true;}
            if(Array.IndexOf(args,"-tripoReview")>=0){review.PreviousLabel="previous";review.PilotLabel="tripo";review.FaceCloseups=true;review.ClayOnly=true;}
            var original=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");var pipeline=UnityEngine.Object.Instantiate(original);pipeline.msaaSampleCount=4;
            var settings=new SerializedObject(pipeline);settings.FindProperty("m_SoftShadowsSupported").boolValue=true;settings.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline,Folder+"/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            string scenePath=Folder+"/Review.unity";EditorSceneManager.SaveScene(scene,scenePath);AssetDatabase.SaveAssets();
            BuildReport result;
            try{result=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{scenePath},locationPathName=Path.Combine(output,"Head-Pilot-Review.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});}
            finally{GraphicsSettings.defaultRenderPipeline=original;QualitySettings.renderPipeline=original;AssetDatabase.SaveAssets();}
            if(result.summary.result!=BuildResult.Succeeded)throw new Exception("Head review build failed");
            File.WriteAllText(Path.Combine(output,"review-build.json"),new JObject{["passed"]=true,["scope"]="local head-only static art review",["face_review"]=Array.IndexOf(args,"-faceReview")>=0,["tripo_review"]=Array.IndexOf(args,"-tripoReview")>=0,["inputs_sha256"]=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,"unity-inputs.json"))),["performance_tested"]=false}.ToString());
        }
    }
}

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
    public static class BodyFitReviewBuild
    {
        const string Folder="Assets/BodyFitReviewGenerated";
        public static void Run()
        {
            var args=Environment.GetCommandLineArgs();string art=Path.GetFullPath(args[Array.IndexOf(args,"-bodyArt")+1]);
            string output=args[Array.IndexOf(args,"-reviewOutput")+1];if(Directory.Exists(output))throw new IOException("Preserve previous build");
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
            var manifest=JObject.Parse(File.ReadAllText(Path.Combine(art,"unity-inputs.json")));
            if((string)manifest["schema"]!="ao_approved_head_body_static_v1")throw new InvalidDataException("Wrong body review contract");
            if(SourceGuard.Hash(File.ReadAllBytes(Path.Combine(root,"docs/tripo-head-cloud-texture-approval.json")))!=(string)manifest["head_approval_sha256"])throw new InvalidDataException("Changed head approval");
            foreach(var file in ((JObject)manifest["files"]).Properties())if(SourceGuard.Hash(File.ReadAllBytes(SourceGuard.SafePath(art,file.Name)))!=(string)file.Value)throw new InvalidDataException("Changed body input "+file.Name);
            Directory.CreateDirectory(Folder);File.Copy(Path.Combine(art,"player-static.fbx"),Folder+"/Player.fbx",true);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var importer=(ModelImporter)AssetImporter.GetAtPath(Folder+"/Player.fbx");importer.importAnimation=false;importer.materialImportMode=ModelImporterMaterialImportMode.ImportStandard;importer.SaveAndReimport();
            var model=UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(Folder+"/Player.fbx"));
            if(model.GetComponentsInChildren<Animator>().Length>0||model.GetComponentsInChildren<Animation>().Length>0)throw new InvalidDataException("Static model must not contain animation components");
            var palette=JObject.Parse(File.ReadAllText(Path.Combine(art,"palette.json")));
            foreach(var f in model.GetComponentsInChildren<MeshFilter>())if(f.sharedMesh.uv.Length!=f.sharedMesh.vertexCount)throw new InvalidDataException("Missing UV");
            foreach(var renderer in model.GetComponentsInChildren<Renderer>())renderer.sharedMaterials=renderer.sharedMaterials.Select(old=>{
                var entry=palette[old.name];if(entry==null)throw new InvalidDataException("Unknown body material "+old.name);
                var c=(JArray)entry["linear_color"];var mat=new Material(Shader.Find("Universal Render Pipeline/Lit"));mat.name=old.name;
                mat.color=new Color((float)c[0],(float)c[1],(float)c[2],(float)c[3]).gamma;
                mat.SetFloat("_Smoothness",1-(float)entry["roughness"]);mat.SetFloat("_Metallic",(float?)entry["metallic"]??0);
                if((bool?)entry["double_sided"]==true)mat.SetFloat("_Cull",(float)CullMode.Off);
                if((bool?)entry["alpha_clip"]==true){mat.SetFloat("_AlphaClip",1);mat.SetFloat("_Cutoff",.5f);mat.EnableKeyword("_ALPHATEST_ON");mat.SetOverrideTag("RenderType","TransparentCutout");mat.renderQueue=(int)RenderQueue.AlphaTest;}
                bool repeat=(string)entry["wrap"]=="repeat";
                if((string)entry["base_texture"] is string color)mat.SetTexture("_BaseMap",Texture(art,color,manifest,true,false,repeat));
                if((string)entry["normal_texture"] is string normal){mat.SetTexture("_BumpMap",Texture(art,normal,manifest,false,true,repeat));mat.SetFloat("_BumpScale",(float?)entry["normal_scale"]??1);mat.EnableKeyword("_NORMALMAP");}
                if((string)entry["metallic_gloss_texture"] is string mask){mat.SetTexture("_MetallicGlossMap",Texture(art,mask,manifest,false,false,repeat));mat.SetFloat("_Smoothness",1);mat.SetFloat("_Metallic",1);mat.EnableKeyword("_METALLICSPECGLOSSMAP");}
                AssetDatabase.CreateAsset(mat,Folder+"/Mat-"+Guid.NewGuid().ToString("N")+".mat");return mat;
            }).ToArray();
            var prefab=PrefabUtility.SaveAsPrefabAsset(model,Folder+"/Player.prefab");UnityEngine.Object.DestroyImmediate(model);
            if(SourceGuard.Hash(File.ReadAllBytes("Assets/U4Generated/room.fbx"))!=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(root,"art/unity/startroom-u4/room.fbx"))))throw new InvalidDataException("Room baseline changed");
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var review=new GameObject("Static body fitting review").AddComponent<BodyFitReview>();review.Player=prefab;review.Room=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/U4Generated/room.prefab");
            if(review.Room==null)throw new InvalidDataException("Missing room context");
            var original=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");var pipeline=UnityEngine.Object.Instantiate(original);pipeline.msaaSampleCount=4;
            AssetDatabase.CreateAsset(pipeline,Folder+"/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");
            GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            const string scenePath=Folder+"/Review.unity";EditorSceneManager.SaveScene(scene,scenePath);AssetDatabase.SaveAssets();
            BuildReport report;try{report=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{scenePath},locationPathName=Path.Combine(output,"Body-Fit-Review.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});}
            finally{GraphicsSettings.defaultRenderPipeline=original;QualitySettings.renderPipeline=original;AssetDatabase.SaveAssets();}
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception("Body review build failed");
            File.WriteAllText(Path.Combine(output,"review-build.json"),new JObject{["passed"]=true,["art"]=Path.GetFileName(art),["inputs_sha256"]=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,"unity-inputs.json"))),["scope"]="static body proportions and clothing junction review",["animation_tested"]=false,["performance_tested"]=false}.ToString());
        }
        static Texture2D Texture(string art,string name,JObject manifest,bool srgb,bool normal,bool repeat)
        {
            if(manifest["files"]?[name]==null)throw new InvalidDataException("Unpinned texture "+name);
            var size=manifest["texture_sizes"]?[name] as JArray;if(size==null||size.Count!=2)throw new InvalidDataException("Missing size");
            int w=(int)size[0],h=(int)size[1];if(w<1||h<1||w>8192||h>8192)throw new InvalidDataException("Invalid texture size");
            string path=Folder+"/"+Path.GetFileName(name);File.Copy(SourceGuard.SafePath(art,name),path,true);AssetDatabase.ImportAsset(path,ImportAssetOptions.ForceSynchronousImport);
            var importer=(TextureImporter)AssetImporter.GetAtPath(path);importer.textureType=normal?TextureImporterType.NormalMap:TextureImporterType.Default;importer.sRGBTexture=srgb;importer.maxTextureSize=Mathf.NextPowerOfTwo(Math.Max(w,h));importer.textureCompression=TextureImporterCompression.Uncompressed;importer.wrapMode=repeat?TextureWrapMode.Repeat:TextureWrapMode.Clamp;importer.SaveAndReimport();
            var tex=AssetDatabase.LoadAssetAtPath<Texture2D>(path);if(tex==null||tex.width!=w||tex.height!=h)throw new InvalidDataException("Invalid decoded texture");return tex;
        }
    }
}

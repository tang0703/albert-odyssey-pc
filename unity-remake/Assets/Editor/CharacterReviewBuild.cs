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
    // Isolated static review: it never creates a RoomSession or new gameplay entry.
    public static class CharacterReviewBuild
    {
        const string Folder="Assets/CharacterReviewGenerated";
        public static void Run()
        {
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
            string art=Path.Combine(root,"art/unity/player-refined-v1");
            var args=Environment.GetCommandLineArgs();string output=args[Array.IndexOf(args,"-reviewOutput")+1];
            if(Directory.Exists(output))throw new IOException("Review output must be new");
            var manifest=JObject.Parse(File.ReadAllText(Path.Combine(art,"material-manifest.json")));
            foreach(var p in ((JObject)manifest["files"]).Properties())
                if(SourceGuard.Hash(File.ReadAllBytes(SourceGuard.SafePath(art,p.Name)))!=(string)p.Value["sha256"])throw new InvalidDataException("Changed review input "+p.Name);
            Directory.CreateDirectory(Folder);
            File.Copy(Path.Combine(art,"player-static.fbx"),Folder+"/player-static.fbx",true);
            foreach(string name in new[]{"character-albedo","character-normal","character-mask"})File.Copy(Path.Combine(art,"textures/"+name+".png"),Folder+"/"+name+".png",true);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            foreach(string name in new[]{"character-albedo","character-normal","character-mask"})
            {
                var imp=(TextureImporter)AssetImporter.GetAtPath(Folder+"/"+name+".png");imp.maxTextureSize=2048;imp.textureCompression=TextureImporterCompression.Uncompressed;
                imp.sRGBTexture=name=="character-albedo";imp.textureType=name=="character-normal"?TextureImporterType.NormalMap:TextureImporterType.Default;imp.alphaSource=TextureImporterAlphaSource.FromInput;imp.SaveAndReimport();
            }
            var mat=new Material(Shader.Find("Universal Render Pipeline/Lit"));mat.name="Refined character UV material";mat.color=Color.white;
            mat.SetTexture("_BaseMap",AssetDatabase.LoadAssetAtPath<Texture2D>(Folder+"/character-albedo.png"));
            mat.SetTexture("_BumpMap",AssetDatabase.LoadAssetAtPath<Texture2D>(Folder+"/character-normal.png"));mat.EnableKeyword("_NORMALMAP");mat.SetFloat("_BumpScale",1);
            mat.SetTexture("_MetallicGlossMap",AssetDatabase.LoadAssetAtPath<Texture2D>(Folder+"/character-mask.png"));mat.EnableKeyword("_METALLICSPECGLOSSMAP");mat.SetFloat("_Smoothness",1);
            mat.SetTexture("_OcclusionMap",AssetDatabase.LoadAssetAtPath<Texture2D>(Folder+"/character-mask.png"));mat.EnableKeyword("_OCCLUSIONMAP");mat.SetFloat("_OcclusionStrength",.65f);
            string materialPath=Folder+"/Character-"+Guid.NewGuid().ToString("N")+".mat";AssetDatabase.CreateAsset(mat,materialPath);
            var instance=UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(Folder+"/player-static.fbx"));
            foreach(var renderer in instance.GetComponentsInChildren<Renderer>()){renderer.sharedMaterials=renderer.sharedMaterials.Select(_=>mat).ToArray();renderer.shadowCastingMode=ShadowCastingMode.On;}
            var prefab=PrefabUtility.SaveAsPrefabAsset(instance,Folder+"/Player.prefab");UnityEngine.Object.DestroyImmediate(instance);
            // Reuse the exact prior generated models only after checking their source identities.
            foreach(string name in new[]{"room.fbx","player-rig.fbx"})
                if(SourceGuard.Hash(File.ReadAllBytes("Assets/U4Generated/"+name))!=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(root,"art/unity/startroom-u4",name))))throw new InvalidDataException("Old review base differs");
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var preview=new GameObject("C2 static character review only").AddComponent<CharacterReview>();preview.Player=prefab;
            preview.OldPlayer=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/U4Generated/player-rig.prefab");preview.Room=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/U4Generated/room.prefab");
            preview.OldIdle=AssetDatabase.LoadAllAssetsAtPath("Assets/U4Generated/player-rig.fbx").OfType<AnimationClip>().Single(c=>!c.name.StartsWith("__preview__",StringComparison.Ordinal)&&c.name.EndsWith("|idle",StringComparison.Ordinal));
            if(preview.Player==null||preview.OldPlayer==null||preview.Room==null)throw new InvalidDataException("Missing review geometry");
            var original=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");var pipeline=UnityEngine.Object.Instantiate(original);pipeline.msaaSampleCount=4;pipeline.shadowDistance=25;
            var settings=new SerializedObject(pipeline);settings.FindProperty("m_SoftShadowsSupported").boolValue=true;settings.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline,Folder+"/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            const string scenePath=Folder+"/Review.unity";EditorSceneManager.SaveScene(scene,scenePath);AssetDatabase.SaveAssets();
            BuildReport built;
            try{built=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{scenePath},locationPathName=Path.Combine(output,"MAP001-Character-Review.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});}
            finally{GraphicsSettings.defaultRenderPipeline=original;QualitySettings.renderPipeline=original;AssetDatabase.SaveAssets();}
            if(built.summary.result!=BuildResult.Succeeded)throw new Exception("C2 build failed");
            File.WriteAllText(Path.Combine(output,"review-build.json"),new JObject{["passed"]=true,["scope"]="C2 static review, no gameplay integration",["manifest_sha256"]=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,"material-manifest.json"))),["performance_tested"]=false}.ToString());
        }
    }
}

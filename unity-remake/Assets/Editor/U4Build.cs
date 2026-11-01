using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
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
    public static class U4Build
    {
        const string Folder="Assets/U4Generated";
        public static void Run()
        {
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
            string art=Path.Combine(root,"art/unity/startroom-u4");
            string[] args=Environment.GetCommandLineArgs();string output=args[Array.IndexOf(args,"-u4Output")+1];
            string sourceCommit=args[Array.IndexOf(args,"-sourceCommit")+1];bool sourceDirty=args[Array.IndexOf(args,"-sourceDirty")+1]=="true";
            if(Directory.Exists(output))throw new IOException("Build output must be new");
            var lockFile=JObject.Parse(File.ReadAllText(Path.Combine(root,"art/unity/startroom-v2/review-lock.json")));
            if(!(bool)lockFile["approved"])throw new InvalidDataException("U3 not approved");
            var rig=JObject.Parse(File.ReadAllText(Path.Combine(art,"rig.json")));
            if(SourceGuard.Hash(File.ReadAllBytes(Path.Combine(root,"art/unity/startroom-v2/review-lock.json")))!=(string)rig["approval_sha256"])throw new InvalidDataException("Approval changed");
            foreach(var item in ((JObject)rig["files"]).Properties())
                if(SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,item.Name)))!=(string)item.Value["sha256"])throw new InvalidDataException("Changed rig asset "+item.Name);
            var approvedArt=JObject.Parse(File.ReadAllText(Path.Combine(art,"asset-lock.json")));
            foreach(var item in ((JObject)approvedArt["files"]).Properties())
                if(SourceGuard.Hash(File.ReadAllBytes(SourceGuard.SafePath(art,item.Name)))!=(string)item.Value["sha256"])throw new InvalidDataException("Changed approved art "+item.Name);
            EquipmentTests.Run(root,true);
            Directory.CreateDirectory(Folder+"/textures");
            var fontSource=JObject.Parse(File.ReadAllText(Path.Combine(root,"art/unity/fonts/source.json")));
            byte[] fontBytes=File.ReadAllBytes(Path.Combine(root,"art/unity/fonts/NotoSansCJKtc-Regular.otf"));
            if(SourceGuard.Hash(fontBytes)!=(string)fontSource["font_sha256"])throw new InvalidDataException("Bundled font changed");
            File.WriteAllBytes(Folder+"/NotoSansCJKtc-Regular.otf",fontBytes);
            foreach(string name in new[]{"player-rig.fbx","room.fbx","cirrus.fbx"})File.Copy(Path.Combine(art,name),Folder+"/"+name,true);
            var materialRows=(JArray)JObject.Parse(File.ReadAllText(Path.Combine(art,"materials.json")))["materials"];
            foreach(var row in materialRows.Where(r=>r["albedo"]!=null))
            {
                string relative=(string)row["albedo"];byte[] raw=File.ReadAllBytes(Path.Combine(art,relative));
                if(SourceGuard.Hash(raw)!=(string)row["sha256"])throw new InvalidDataException("Changed baked material");
                File.WriteAllBytes(Folder+"/"+relative,raw);
            }
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var importer=(ModelImporter)AssetImporter.GetAtPath(Folder+"/player-rig.fbx");
            importer.animationType=ModelImporterAnimationType.Legacy;importer.importAnimation=true;importer.animationCompression=ModelImporterAnimationCompression.Off;importer.SaveAndReimport();
            var materials=new Dictionary<string,Material>();
            foreach(var row in materialRows)
            {
                string name=(string)row["name"],path=Folder+"/"+name+".mat";
                Material m=AssetDatabase.LoadAssetAtPath<Material>(path);
                if(m==null){m=new Material(Shader.Find("Universal Render Pipeline/Lit"));AssetDatabase.CreateAsset(m,path);}
                var c=(JArray)row["base_color"];m.color=new Color((float)c[0],(float)c[1],(float)c[2],1);
                m.SetFloat("_Metallic",(float)row["metallic"]);m.SetFloat("_Smoothness",1-(float)row["roughness"]);
                if(row["albedo"]!=null){m.mainTexture=AssetDatabase.LoadAssetAtPath<Texture2D>(Folder+"/"+(string)row["albedo"]);m.color=Color.white;}
                materials.Add(name,m);EditorUtility.SetDirty(m);
            }
            GameObject Prefab(string file)
            {
                var original=AssetDatabase.LoadAssetAtPath<GameObject>(Folder+"/"+file+".fbx");var instance=UnityEngine.Object.Instantiate(original);
                try
                {
                    foreach(var renderer in instance.GetComponentsInChildren<Renderer>())
                    {
                        renderer.sharedMaterials=renderer.sharedMaterials.Select(m=>materials.TryGetValue(m.name,out var replacement)?replacement:throw new InvalidDataException("Unmapped material "+m.name)).ToArray();
                        renderer.shadowCastingMode=ShadowCastingMode.On;renderer.receiveShadows=true;
                    }
                    return PrefabUtility.SaveAsPrefabAsset(instance,Folder+"/"+file+".prefab");
                }
                finally{UnityEngine.Object.DestroyImmediate(instance);}
            }
            var player=Prefab("player-rig");var room=Prefab("room");var sword=Prefab("cirrus");
            var clips=AssetDatabase.LoadAllAssetsAtPath(Folder+"/player-rig.fbx").OfType<AnimationClip>().Where(c=>!c.name.StartsWith("__preview__",StringComparison.Ordinal)).ToArray();
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var go=new GameObject("MAP001 source-driven skeletal workbench");var artView=go.AddComponent<RoomArt>();
            artView.PlayerModel=player;artView.RoomModel=room;artView.CirrusModel=sword;artView.Clips=clips;
            var workbench=go.AddComponent<RoomWorkbench>();workbench.BaseMaterial=AssetDatabase.LoadAssetAtPath<Material>("Assets/U2Generated/Graybox.mat");workbench.Art=artView;
            workbench.BundledFont=AssetDatabase.LoadAssetAtPath<Font>(Folder+"/NotoSansCJKtc-Regular.otf");
            if(workbench.BundledFont==null)throw new InvalidDataException("Bundled Traditional Chinese font unavailable");
            var source=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");var pipeline=UnityEngine.Object.Instantiate(source);
            pipeline.shadowDistance=25;pipeline.msaaSampleCount=4;var settings=new SerializedObject(pipeline);settings.FindProperty("m_SoftShadowsSupported").boolValue=true;settings.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline,Folder+"/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");
            GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            PlayerSettings.productName="MAP001 Unity Start Room";PlayerSettings.defaultScreenWidth=1920;PlayerSettings.defaultScreenHeight=1080;PlayerSettings.fullScreenMode=FullScreenMode.Windowed;
            const string scenePath=Folder+"/StartRoom.unity";EditorSceneManager.SaveScene(scene,scenePath);AssetDatabase.SaveAssets();
            var dependencies=AssetDatabase.GetDependencies(scenePath,true);
            string[] allowedScripts={"RoomWorkbench.cs","RoomArt.cs","SourceEffects3D.cs","U4Preview.cs"};
            foreach(string dependency in dependencies)
            {
                bool allowed=dependency.StartsWith(Folder+"/",StringComparison.Ordinal)||dependency.StartsWith("Packages/",StringComparison.Ordinal)||dependency.StartsWith("Assets/TextMesh Pro/",StringComparison.Ordinal)||dependency=="Assets/U2Generated/Graybox.mat"||dependency.StartsWith("Assets/Settings/",StringComparison.Ordinal)||dependency.StartsWith("Assets/Scripts/Core/",StringComparison.Ordinal)||allowedScripts.Any(name=>dependency=="Assets/Scripts/"+name);
                if(!allowed)throw new InvalidDataException("Unapproved scene dependency: "+dependency);
            }
            BuildReport build;
            try{build=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{scenePath},locationPathName=Path.Combine(output,"MAP001-Unity-StartRoom.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});}
            finally{GraphicsSettings.defaultRenderPipeline=source;QualitySettings.renderPipeline=source;AssetDatabase.SaveAssets();}
            var report=new JObject{["passed"]=build.summary.result==BuildResult.Succeeded,["editor"]=Application.unityVersion,["source_commit"]=sourceCommit,["source_dirty"]=sourceDirty,["art_lock_sha256"]=SourceGuard.Hash(File.ReadAllBytes(Path.Combine(art,"asset-lock.json"))),["dependencies"]=new JArray(dependencies),["clips"]=new JArray(clips.Select(c=>c.name)),["performance_tested"]=false,["scope"]="U4 integration build; visual acceptance reported separately"};
            File.WriteAllText(Path.Combine(output,"u4-build.json"),report.ToString());
            if(build.summary.result!=BuildResult.Succeeded)throw new Exception("U4 build failed");
        }
    }
}

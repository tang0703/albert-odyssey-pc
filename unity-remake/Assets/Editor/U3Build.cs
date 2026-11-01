using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ao.UnityMigration.Editor
{
    public static class U3Build
    {
        public static void Run()
        {
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));string[] args=Environment.GetCommandLineArgs();string output=args[Array.IndexOf(args,"-u3Build")+1];
            int artArgument=Array.IndexOf(args,"-u3ArtVersion");string artVersion=artArgument<0?"startroom-v1":args[artArgument+1];
            if(artVersion!="startroom-v1"&&artVersion!="startroom-v2")throw new ArgumentException("Unknown art review version");
            if(Directory.Exists(output))throw new IOException("Existing review build");
            Directory.CreateDirectory("Assets/U3Generated");
            foreach(string file in new[]{"room-draft.fbx","player-draft.fbx"})
                File.Copy(Path.Combine(root,"art/unity",artVersion,file),"Assets/U3Generated/"+file,true);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var preview=new GameObject("U3 static art review").AddComponent<U3Review>();
            preview.ArtVersion=artVersion;
            preview.Room=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/U3Generated/room-draft.fbx");preview.Player=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/U3Generated/player-draft.fbx");
            preview.Lit=AssetDatabase.LoadAssetAtPath<Material>("Assets/U2Generated/Graybox.mat");
            if(preview.Room==null||preview.Player==null||preview.Lit==null)throw new Exception("Missing draft geometry/material");
            var source=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");
            var pipeline=UnityEngine.Object.Instantiate(source);pipeline.name="U3 Review URP";pipeline.shadowDistance=25;pipeline.msaaSampleCount=4;
            var pipelineSettings=new SerializedObject(pipeline);pipelineSettings.FindProperty("m_SoftShadowsSupported").boolValue=true;pipelineSettings.ApplyModifiedPropertiesWithoutUndo();
            AssetDatabase.CreateAsset(pipeline,"Assets/U3Generated/Pipeline-"+Guid.NewGuid().ToString("N")+".asset");
            GraphicsSettings.defaultRenderPipeline=pipeline;QualitySettings.renderPipeline=pipeline;
            const string path="Assets/U3Generated/Review.unity";EditorSceneManager.SaveScene(scene,path);AssetDatabase.SaveAssets();
            var built=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{path},locationPathName=Path.Combine(output,"MAP001-Unity-U3-Review.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});
            if(built.summary.result!=BuildResult.Succeeded)throw new Exception("U3 review build failed");
            GraphicsSettings.defaultRenderPipeline=source;QualitySettings.renderPipeline=source;AssetDatabase.SaveAssets();
            File.WriteAllText(Path.Combine(output,"review-build.txt"),Application.unityVersion+"\nStatic U3 preview only; not a gameplay or performance acceptance.");
        }
    }
}

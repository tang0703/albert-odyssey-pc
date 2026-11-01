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
    public static class U1Build
    {
        [Serializable] private sealed class BuildEvidence
        {
            public bool passed;
            public string editor, output, result;
            public int errors;
            public bool gameplayPortTested=false, performanceTested=false;
        }

        public static void Run()
        {
            string[] args=Environment.GetCommandLineArgs();
            string output=null, report=null;
            for(int i=0;i<args.Length-1;i++)
            {
                if(args[i]=="-u1Output") output=Path.GetFullPath(args[i+1]);
                if(args[i]=="-u1Report") report=Path.GetFullPath(args[i+1]);
            }
            if(output==null || report==null) throw new ArgumentException("Required -u1Output and -u1Report");
            if(Directory.Exists(output)) throw new IOException("Refusing to overwrite an existing U1 build");
            Directory.CreateDirectory("Assets/U1Generated");
            Directory.CreateDirectory("Assets/Settings");
            AssetDatabase.Refresh();
            foreach(var file in new[]{"UniversalRenderer.asset","Pipeline.asset"})
                if(AssetDatabase.LoadMainAssetAtPath("Assets/Settings/"+file)==null && AssetDatabase.LoadMainAssetAtPath("Assets/U1Generated/"+file)!=null)
                    AssetDatabase.MoveAsset("Assets/U1Generated/"+file,"Assets/Settings/"+file);
            var renderer=AssetDatabase.LoadAssetAtPath<UniversalRendererData>("Assets/Settings/UniversalRenderer.asset");
            if(renderer==null) {
                renderer=ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(renderer,"Assets/Settings/UniversalRenderer.asset");
            }
            var pipeline=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");
            if(pipeline==null) {
                pipeline=UniversalRenderPipelineAsset.Create(renderer);
                pipeline.name="MAP001 U1 Universal Renderer";
                AssetDatabase.CreateAsset(pipeline,"Assets/Settings/Pipeline.asset");
            }
            GraphicsSettings.defaultRenderPipeline=pipeline;
            QualitySettings.renderPipeline=pipeline;
            PlayerSettings.companyName="MK";
            PlayerSettings.productName="MAP001 Unity U1 Tool Verification";
            PlayerSettings.defaultScreenWidth=1280;
            PlayerSettings.defaultScreenHeight=720;
            PlayerSettings.fullScreenMode=FullScreenMode.Windowed;
            PlayerSettings.colorSpace=ColorSpace.Linear;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone,ScriptingImplementation.Mono2x);
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var camera=new GameObject("Fixed ortho camera").AddComponent<Camera>();
            camera.transform.position=new Vector3(0,7,-7);
            camera.transform.rotation=Quaternion.Euler(45,0,0);
            camera.orthographic=true; camera.orthographicSize=5;
            camera.backgroundColor=new Color(0.04f,0.06f,0.07f); camera.clearFlags=CameraClearFlags.SolidColor;
            camera.gameObject.AddComponent<AudioListener>();
            camera.gameObject.AddComponent<UniversalAdditionalCameraData>();
            var light=new GameObject("Warm key").AddComponent<Light>();
            light.type=LightType.Directional; light.color=new Color(1,0.82f,0.65f); light.intensity=1.5f;
            light.transform.rotation=Quaternion.Euler(50,-35,0); light.shadows=LightShadows.Soft;
            var shader=Shader.Find("Universal Render Pipeline/Lit");
            if(shader==null) throw new InvalidOperationException("URP Lit shader unavailable");
            var material=AssetDatabase.LoadAssetAtPath<Material>("Assets/U1Generated/SmokeMaterial.mat");
            if(material==null) {
                material=new Material(shader); material.color=new Color(0.5f,0.35f,0.2f);
                AssetDatabase.CreateAsset(material,"Assets/U1Generated/SmokeMaterial.mat");
            }
            var ground=GameObject.CreatePrimitive(PrimitiveType.Cube);
            ground.name="U1 verification floor - not source geometry";
            ground.transform.localScale=new Vector3(8,0.1f,5);
            ground.GetComponent<Renderer>().sharedMaterial=material;
            var cube=GameObject.CreatePrimitive(PrimitiveType.Cube);
            cube.name="U1 verification cube - not character art";cube.transform.position=Vector3.up;
            cube.GetComponent<Renderer>().sharedMaterial=material;
            new GameObject("U1 probe").AddComponent<U1SmokeProbe>();
            const string scenePath="Assets/U1Generated/U1Smoke.unity";
            EditorSceneManager.SaveScene(scene,scenePath);
            AssetDatabase.SaveAssets();
            var built=BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes=new[]{scenePath},locationPathName=Path.Combine(output,"MAP001-Unity-U1.exe"),
                target=BuildTarget.StandaloneWindows64,options=BuildOptions.None });
            Directory.CreateDirectory(Path.GetDirectoryName(report));
            File.WriteAllText(report,JsonUtility.ToJson(new BuildEvidence {
                passed=built.summary.result==BuildResult.Succeeded,editor=Application.unityVersion,
                output=output,result=built.summary.result.ToString(),errors=(int)built.summary.totalErrors },true));
            if(built.summary.result!=BuildResult.Succeeded) throw new InvalidOperationException("U1 standalone build failed");
        }
    }
}

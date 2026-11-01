using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using Newtonsoft.Json.Linq;

namespace Ao.UnityMigration.Editor
{
    public static class U2Build
    {
        public static void Run()
        {
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
            EquipmentTests.Run(root,true);
            var args=Environment.GetCommandLineArgs();
            string output=args[Array.IndexOf(args,"-u2Output")+1],report=args[Array.IndexOf(args,"-u2Report")+1];
            if(Directory.Exists(output))throw new IOException("Refusing existing build directory");
            Directory.CreateDirectory("Assets/U2Generated");AssetDatabase.Refresh();
            if(Shader.Find("TextMeshPro/Distance Field")==null)
            {
                string package=Directory.GetFiles("Library/PackageCache","TMP Essential Resources.unitypackage",SearchOption.AllDirectories).Single();
                AssetDatabase.ImportPackage(package,false);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            }
            GraphicsSettings.defaultRenderPipeline=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/Pipeline.asset");
            QualitySettings.renderPipeline=GraphicsSettings.defaultRenderPipeline;
            PlayerSettings.productName="MAP001 Unity U2 Graybox";
            PlayerSettings.defaultScreenWidth=1920;PlayerSettings.defaultScreenHeight=1080;PlayerSettings.fullScreenMode=FullScreenMode.Windowed;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone,ScriptingImplementation.Mono2x);
            // Dynamic OS font is loaded in runtime; explicitly retain its shader.
            var graphics=new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/GraphicsSettings.asset")[0]);
            var shaders=graphics.FindProperty("m_AlwaysIncludedShaders");
            foreach(string name in new[]{"TextMeshPro/Distance Field","UI/Default"})
            {
                Shader shader=Shader.Find(name);if(shader==null)throw new InvalidOperationException("Missing shader "+name);
                bool found=false;for(int i=0;i<shaders.arraySize;i++)if(shaders.GetArrayElementAtIndex(i).objectReferenceValue==shader)found=true;
                if(!found){int i=shaders.arraySize;shaders.InsertArrayElementAtIndex(i);shaders.GetArrayElementAtIndex(i).objectReferenceValue=shader;}
            }
            graphics.ApplyModifiedPropertiesWithoutUndo();
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var material=AssetDatabase.LoadAssetAtPath<Material>("Assets/U2Generated/Graybox.mat");
            if(material==null){material=new Material(Shader.Find("Universal Render Pipeline/Lit"));AssetDatabase.CreateAsset(material,"Assets/U2Generated/Graybox.mat");}
            new GameObject("MAP001 U2 source-driven workbench").AddComponent<RoomWorkbench>().BaseMaterial=material;
            const string path="Assets/U2Generated/StartRoom.unity";EditorSceneManager.SaveScene(scene,path);AssetDatabase.SaveAssets();
            var built=BuildPipeline.BuildPlayer(new BuildPlayerOptions{scenes=new[]{path},locationPathName=Path.Combine(output,"MAP001-Unity-U2.exe"),target=BuildTarget.StandaloneWindows64,options=BuildOptions.None});
            var evidence=new JObject{["passed"]=built.summary.result==BuildResult.Succeeded,["errors"]=(int)built.summary.totalErrors,["editor"]=Application.unityVersion,["performance_tested"]=false,["final_art"]=false};
            File.WriteAllText(report,evidence.ToString());if(built.summary.result!=BuildResult.Succeeded)throw new Exception("U2 build failed");
        }
    }
}

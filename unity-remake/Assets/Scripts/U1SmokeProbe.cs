using System;
using System.IO;
using Ao.SourceContracts;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ao.UnityMigration
{
    // Tool verification only. No replay fixture, source state or gameplay is advanced.
    public sealed class U1SmokeProbe : MonoBehaviour
    {
        [Serializable] private sealed class Report
        {
            public bool passed;
            public string editor, graphics, renderer, error;
            public int sourceFiles;
            public bool gameplayPortTested = false;
            public bool performanceTested = false;
        }
        private Report result;
        private string reportPath;
        private int frames;

        private void Start()
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i=0;i<args.Length-1;i++) if (args[i]=="--u1-smoke-report") reportPath=args[i+1];
            result = new Report { editor=Application.unityVersion, graphics=SystemInfo.graphicsDeviceName };
            try
            {
                var pipeline = GraphicsSettings.currentRenderPipeline;
                result.renderer=pipeline == null ? "Built-in" : pipeline.GetType().FullName;
                if (result.renderer != "UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset")
                    throw new InvalidDataException("U1 requires the configured URP pipeline");
                result.sourceFiles=SourceGuard.Load(Path.Combine(Application.streamingAssetsPath,"SourceLocal"),
                    SourcePins.Files,Application.isEditor).Count;
                result.passed=true;
            }
            catch (Exception exception) { result.passed=false; result.error=exception.Message; Debug.LogError(exception); }
        }

        private void Update()
        {
            if (result==null || ++frames<5 || string.IsNullOrEmpty(reportPath)) return;
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath)));
            File.WriteAllText(reportPath,JsonUtility.ToJson(result,true));
            Application.Quit(result.passed ? 0 : 2);
            reportPath=null;
        }

        private void OnGUI()
        {
            GUI.Label(new Rect(20,20,900,55),"U1 - UNITY TOOL VERIFICATION ONLY\nNot the playable MAP001 slice. Performance not evaluated.");
        }
    }
}

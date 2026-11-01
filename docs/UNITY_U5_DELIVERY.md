# MAP001 Unity 起始房間候選交付

完成標記：**MAP001 起始房間 Unity 3D 俯視切片與既有玩法功能驗證通過；效能驗收暫緩。**

二進位來源：乾淨提交 `bf68bd87708292540670412e9b704a2f06a1cdd6`，Unity 6000.3.27f2。之後的本文件提交僅補記交付結果。

## 本地套件

- `build/MAP001-Unity-StartRoom-Candidate-Windows-x64.zip`
- 大小：103,217,625 bytes。
- SHA256：`92062536fe4f1ebb67b9ba07f832b495c3fecfd422cc6975ad7eb6721e15a61c`
- 251 檔（250 個負載檔案加 PACKAGE.json）；CRC、封裝清單、逐檔 SHA256、解壓後再核對均通過。
- 解壓目錄：`build/unity-candidate-extracted-018b9b11659f4db9a8ee0c949ce308d7`。
- 從上述解壓目錄獨立啟動，完成取得、對話、裝備／卸下／重裝、樓梯邊界及重設；六個骨架動作、實際音訊啟動、UI 語意與暫停／模式切換檢查通過。未使用 Unity 編輯器啟動遊戲。
- 產物包含原作來源資料與音訊，僅保留本地；GitHub 同步程式、新美術、可編輯來源、文件與授權，不同步此 ZIP。

操作見 [UNITY_PLAY_GUIDE.md](UNITY_PLAY_GUIDE.md)。美術預覽見 [骨架預覽](../art/unity/startroom-u4/previews/index.html)，可編輯來源 `art/unity/startroom-u4/startroom-rig.blend`。

## 最終二進位的短程畫面

| 解析度 | 本地目錄 | 結果 |
|---|---|---|
| 1920×1080 | `reports/unity/u4-shots-1920-544159722e9e406e935b20bd6a78603d` | 通過 |
| 2560×1440 | `reports/unity/u4-shots-2560-e7d77eef2cc74f8ca165e9aebf686b31` | 通過 |
| 3840×2160 | `reports/unity/u4-shots-3840-58ae9d3fb09e43f3b3e12805ecb51b1f` | 通過 |

每個目錄含四向、對話、四個取得姿勢、裝備、樓梯邊界與起點。最終建置僅將開發階段標籤改成「起始房間候選版」，素材與核心同 U4 已驗證版本。

原始證據：`reports/unity/u5-package.json`、`u5-extracted-launch.json`、`u4-rig-validation.json`、`u4-appearance-core.json`、`u4-python-regression.json` 與各 Godot 日誌。包內功能驗收文件記錄封裝前基準，最終解壓結果以本文件及外部報告為準。

## 範圍與限制

回歸細項見 [UNITY_U5_ACCEPTANCE.md](UNITY_U5_ACCEPTANCE.md)：7,370 次外觀來源更新零差異、Python 463 通過、Godot 裝備／戰鬥／事件／資源檢查通過。九項舊快照缺失與七項效能證據相依測試繼續明列。

**未執行負載、長循環、效能基準或實際 GPU FPS 測試。** 此候選版仍有後續美術精修空間，尤其臉部、髮束與材質豐富度；模型沒有宣稱完全等同插畫概念圖。樓下、LAIA、戰鬥、存讀檔、完整探索與 Stage B 整體未移植／未完成，Godot 基準保持不變。

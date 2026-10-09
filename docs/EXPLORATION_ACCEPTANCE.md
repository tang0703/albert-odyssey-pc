# MAP001 指定區域行走驗收

日期：2026-10-09。E1–E4 已完成；此版本正在執行 E5 Windows 畫面與 4K 長測，尚未標記整體交付通過。

## 已通過的來源與核心關卡

- E1：新具名起點、來源鎖、五段同步導航、四組各三次重播；Git `8e867ec`。
- E2：12 條原作軌跡、1,680 次更新、17 個狀態欄位及 caller 邊界比較零差異；Git `d1304dc`。
- E3：Godot 純核心 33,664 項檢查，1,680 次更新與來源完全一致；Git `b5607d6`。
- E4：最初 988 項介面檢查，涵蓋真正 InputEvent 鍵鼠事件、暫停、單步、重設、多方向、測試邊界、四條完整路線及不同時間切分；Git `2530969`。E5 加入尺寸防護後為 991 項。
- 載入器 32 項檢查，包括缺失、截斷、額外隱藏檔案、manifest 自行改寫與 560 次重播核對。
- 本地資料包獨立驗證 560 次更新、108 個已驗證查表格；13 項資料包故障測試通過。

詳見 [來源基準](EXPLORATION_CAPTURE_BASELINE.md) 與 [移動核心](EXPLORATION_MOVEMENT.md)。

## 渲染頻率一致性

每種時間分割都以四條原作路線、560 次更新逐次比較 17 欄位。
30／60／120 FPS 的時間分割與無畫面引擎迴圈均為零差異。
另以實際 GPU 畫面測得 30.009／60.021 FPS，對照零差異。
設定 120 FPS、停用 VSync 後，實際 GPU 僅達約 60.035 FPS，因此 **實際 120 FPS 渲染仍未驗收**。
不以設定值當作實測值，也沒有修改全域顯示卡設定。

## 回歸測試

- 全部 Python 測試共 173 項：164 通過，9 項因缺失舊快照而報錯；沒有新增失敗。
- 舊快照 SHA256：`615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab`。使用者已確認無備份，沒有更換原鎖定值。
- 原專案 Godot：14 項事件／存檔、9 項資源驗證台檢查通過。
- 戰鬥：核心 173、介面 417、動畫 39、QA 26、設定 5、6 組 FPS／速度、封裝 8、驗收器 16 項通過。
- 新行走套件：13 項資料包、12 項封裝、40 項 QA 驗收器故障注入檢查。合成防護測試與原作動態核對分開記錄。

詳細報告保存在本地 `reports/exploration/`，包括 `player-trace-suite.json`、`godot-movement-validation.json`、`test_ui.log`、`python-regression-final.log`、`battle-regression.log` 及 `ui-gpu-fps-*.json`。

## E5 待完成

三解析度實際畫面、正式匯出後操作測試、4K 600 秒穩定演出、程序記憶體／顯存／節點數、ZIP 解壓冷啟動及最終 Git 同步，均須完成後再填入實測值。

## 重新執行

從 `pc-remake` 目錄執行；工具、來源及同步捕捉須已備妥：

```powershell
.\tools\exploration.ps1 build
.\tools\exploration.ps1 test
.\tools\exploration.ps1 export
# 使用 export 回報的完整解壓路徑，OutputRoot 必須是新的資料夾。
.\tools\exploration_qa.ps1 -Executable 'G:\絕對路徑\MAP001-Walk.exe' `
  -OutputRoot 'G:\新的測試資料夾' -SkipSoak
.\tools\exploration_qa.ps1 -Executable 'G:\絕對路徑\MAP001-Walk.exe' `
  -OutputRoot 'G:\新的測試資料夾' -SoakOnly -SoakSeconds 600 -WarmupSeconds 15
```

量測期間不執行其他驗證；截圖與長測為不同程序。QA 固定輸出路徑拒絕覆寫舊證據。
完整套件來源提交與檔案雜湊記於 `BUILD-INFO.json`；ZIP 雜湊另存同層 `.sha256`，避免在 ZIP 內循環自我雜湊。

## 驗證界線

僅包含指定角色與 MAP001 已驗證查表範圍。固定鏡頭背景保持 320×224 比例，玩家以診斷標記顯示。未加入 NPC、事件、戰鬥串接、角色動畫、存讀檔或完整地圖。

原始光碟、BIOS、RAM、快照與包含原作背景的本地 ZIP 不推送 GitHub。舊快照缺失的 9 項回歸仍無法重跑，沒有以新來源雜湊替換。Stage B 整體未通過。

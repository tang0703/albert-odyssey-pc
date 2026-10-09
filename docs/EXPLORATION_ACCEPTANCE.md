# MAP001 指定區域行走驗收

日期：2026-10-09。**MAP001 指定區域行走、原作對照與 4K 60 FPS 驗證通過，提供本地 Windows 套件。**
原需求中的實際 120 FPS GPU 渲染仍未完成驗收，不能宣稱所有驗收項目都通過。完整 Stage B 亦未通過。

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
- 新行走套件：13 項資料包、12 項封裝、44 項 QA 驗收器故障注入檢查通過。合成防護測試與原作動態核對分開記錄。

詳細報告保存在本地 `reports/exploration/`，包括 `player-trace-suite.json`、`godot-movement-validation.json`、`test_ui.log`、`python-regression-final.log`、`battle-regression.log` 及 `ui-gpu-fps-*.json`。

## E5：Windows 畫面、啟動與效能

正式測量來源為乾淨提交 `83b19e0e0c59576c028a91fbf27f5ec974ac6f50`，
從 ZIP 全新解壓路徑執行 release EXE。Godot 4.7.2 `ed1daf0bf`、Compatibility／OpenGL 3.3、
RTX 4070 Ti SUPER、NVIDIA 617.14。詳細證據位於 `reports/exploration/qa-final-03/`。

|解析度|引擎進入至第一張畫面|引擎進入至穩定尺寸確認|程序啟動至確認標記被觀察|
|---|---:|---:|---:|
|1920×1080|77.454 ms|327.512 ms|949.387 ms|
|2560×1440|91.920 ms|358.549 ms|889.234 ms|
|3840×2160|111.944 ms|378.555 ms|978.171 ms|

三張 `screen.png` 的實際像素尺寸一致，文字、操作按鈕、形狀框及標記未見裁切。
每次啟動都是獨立程序，不需編輯器、原始光碟、BIOS 或快照；沒有清除 OS 磁碟快取，
所以數字不是冷快取性能保證。穩定尺寸確認含 250 ms 觀察；外部標記採 100 ms 輪詢。

長測與截圖分開執行，暖機 15 秒、實測 **600.010424 秒**。期間不執行其他驗證，
GPU 實際像素在量測前／後各核對一次；量測中讀圖與截圖均為 0 次。
逐幀視窗／縮放檢查 36,885 次，601 筆引擎樣本的視窗均為 3840×2160。

|量測項目|結果|
|---|---:|
|原始影格間隔數|35,990|
|平均 FPS|59.982291|
|P95|16.921 ms|
|最大間隔|86.492 ms|
|超過 50 ms|2 次，完整時點保留於報告|
|超過 100 ms|0 次|
|完成路線／差異更新|261／0（完成數包含暖機）|
|節點數|601 筆均為 94|
|程序採樣／GPU 採樣|561／54 筆|
|私有記憶體前／後段中位數|319.922 → 317.227 MiB，−0.8425%|
|Working set 前／後段中位數|239.957 → 238.980 MiB，−0.4070%|
|穩定期間私有／Working set 採樣峰值|320.496／241.012 MiB（程序第 20–610 秒）|
|含啟動的私有記憶體採樣峰值|410,136,576 bytes|
|含啟動的 OS peak working set|318,201,856 bytes|
|GPU dedicated／shared 採樣峰值|310.973／32.684 MiB|

前段中位數採程序第 75–135 秒，末段採最後 60 秒附近的獨立區段；各有 55／54 筆。
GPU 是 Windows `GPU Process Memory` 按該 PID 合計的計數器，約每 10 秒採樣，
涵蓋第 23.558–612.361 秒；採樣峰值不等於未間斷硬體峰值。
兩次尖峰為量測第 77.757724 秒（open 更新 78，86.492 ms）、
第 124.048058 秒（open 更新 37，61.719 ms）；沒有超過 100 ms 的尖峰。

初次外部驗收器將 release 版 `MEMORY_STATIC=0` 當成缺失，因而拒絕了本次量測。
Godot 官方文件明示該計數器在 release 版不可用；0 不能解讀成零記憶體用量。
依據：[Performance MEMORY_STATIC](https://docs.godotengine.org/en/4.6/classes/class_performance.html#class-performance-constant-memory-static)。
已修正外部驗收器，仍強制完整、非零的 OS 私有／Working set 採樣與 10% 增長上限。
44 項故障測試包含「內部不可用但外部正常」以及「外部缺失仍須失敗」。
原始 `report.json` 中的 allocator 中位數、增長及 `memory_target_met` 不作記憶體通過依據。

未修改原始報告或重新拼接時段；原失敗 `acceptance.json` 留存，重算另寫 `acceptance-reviewed.json`，
其 `full_acceptance=true` 僅指 4K 長測門檻。重算包含原始報告、程序採樣與驗收器雜湊。
獨立複核得到相同 FPS／P95／記憶體／節點結果。

|量測檔案|SHA256|
|---|---|
|`report.json`|`af67b3d4d5aa112836e53699121b29cf3ed6a4af854ece0e96ec62663f2a61f4`|
|`process-memory.json`|`0cfee7ca76f7e472d90dd5b7dbe69ed5812d96b05b8fee3add5596d281ef41bf`|
|`MAP001-Walk.exe`|`d34d36f3be1a6c49c56525ae86469b92e4f417ddf0b43cf00dd80c385c4b0562`|
|`MAP001-Walk.pck`|`90831ae12db988c64b726d0950535f47666b1eb1b55081270c8b24929a70adb1`|
|`scene/package.json`|`bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc`|

最終封裝只更新文件與外部驗收器；交付 EXE、PCK、場景識別須與上表一致，
另留 `reports/exploration/final-delivery-identity.json` 核對最終 ZIP 與乾淨來源提交。
PCK 精確 12 個資源、交付 14 檔（允許另有 console EXE）、場景資料精確六檔，
全部大小／SHA256 與解壓內容均由封裝工具核對。

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

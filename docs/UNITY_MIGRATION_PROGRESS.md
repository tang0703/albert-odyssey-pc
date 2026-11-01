# Unity 起始房間遷移紀錄

基準：`abd0f5d2d2afc3c55def08be0ec5746bd97a4956`。本輪只做到起始房間、Cirrus 取得／裝備及樓梯提交邊界，樓下、LAIA、戰鬥留在舊 Godot 專案。

## U1 工具與來源基準（已通過）

- 官方 release API 選定 Unity `6000.3.27f2`，revision `22188f149405`（2026-10-30 發布）；後續不自動升級。
- 使用者已確認符合 Unity Personal 資格、完成 Hub 啟用，並明確允許官方 Unity 安裝程式寫入必要安裝資訊。編輯器已實際成功解析 entitlement、建置及獨立啟動。
- Microsoft .NET SDK `8.0.427` 可攜版已核對官方 SHA512，`dotnet --version` 通過。未安裝 Visual Studio 或修改全域 PATH。
- Blender `5.2.3 LTS` 可攜版已核對官方 SHA256，背景模式啟動通過。
- Unity Hub 官方 x64 下載已驗證 Unity Technologies SF 簽章，解壓工具版供帳號啟用。舊 `UnityHubSetup.exe` URL 回傳 404 的嘗試保留，不當成有效下載；新 URL 為 `UnityHubSetup-x64.exe`。
- 原十一包共 254 檔及五份 GDScript 核心的 byte-length／SHA256 鎖定於 `unity-remake/SourceContracts/source-baseline.json`。首次鎖定前通過既有裝備包驗證；再執行不會覆蓋既有 lock。
- 七條裝備序列共 3,685 次更新（不含另外的終端邊界步）；已記錄參照雜湊。這是樣本盤點，尚非 C# 核心對照通過。
- Unity 本地預備資料只有六份必要來源與新的匯入 manifest；golden replay 不放入執行包。未取得 Unity 編輯器成功建置前，不宣稱套件可用。
- 三項 Python 防護測試與十四項純 C# 來源／整數語意檢查通過。C# 驗證使用 .NET 8，不代替 Unity 編譯與執行測試。

來源細節與每次執行紀錄存於本地 `reports/unity/`。工具下載存於 `G:/codex/SS/tools/_downloads`，執行檔存於 `G:/codex/SS/tools/pc-remake`。

## 必要演出清單

從已鎖定設備契約列出 12 個相關 PC 動作位置，包含：

- 表情 subtype 3 與 30 次等待更新。
- 原地朝向 0／2／4、退回動線。
- Cirrus animation index 5。
- 取得時的來源 Y 座標更新與玩家 animation index 24、25。
- 光效 actor 49 的出現、animation index 2 及移除。

數字是來源索引，不是新動畫時長。U2 必須按來源時序與裝置回應完整推演；U3/U4 再製作相符 3D 動作，不能將未知必要姿勢替換成待機。

## U1 實測結果

Unity 官方安裝檔 SHA256 為 `ee89d93435d342834926b4d47c7b1f2863e3ffd0e2cbd8676f4c1e8ced33aaa7`，官方 MD5 integrity 相符、Authenticode Valid。7-Zip 精簡版及完整 26.02 都無法展開新版 NSIS 容器，因此在使用者明確同意後執行官方安裝，exit code 0。沒有自行改寫 PATH。

2026-11-01，`u1-build-bf5e32eabad54138978ab33eb755888e.json` 記錄 Unity 6000.3.27f2 Windows 建置成功、零建置錯誤。獨立執行報告記錄 URP、RTX 4070 Ti SUPER 與七個 runtime source 檔案核對成功；僅五個畫面的短程啟動，不量測 FPS。

第一次 PowerShell 呼叫 GUI editor 未等待程序結束即返回；已修正為持有 PID、等待退出及驗證這一次的 build JSON，不能以 shell exit 0 判斷建置通過。第一次實際建置後來正常完成，保留其真實日誌。額外 license probe 因同專案已開啟而退出 1，記錄保留，不當成授權失敗。

## U2 核心準備（尚未通過灰模／Unity 整合）

純 C# 已從七條裝備流程起點連續運算 3,685 次更新，100,061 項檢查通過，包括來源角色、鏡頭、事件、物件、裝備、物品與劇情欄位、終端邊界、重設及非法操作。沒有回填後續期望狀態。另有包內四條移動路線 560 次更新、9,520 欄位比較通過；這只是完整 1,680 比較中的每條一次樣本，不冒稱全量已重跑。

修正過兩個跨語言細節：JSON null 不得變成 null-string token；32-bit 原始指標必須保留 unsigned 位元，不用 Int32 checked conversion 截斷。現有來源包與五份 Godot 核心仍通過位元組核對。

## 尚未通過的關卡

1. U2：Unity 內的核心執行、可操作灰模切片、完整 1,680 次移動及裝置／輸入整合驗證；純 C# 對照通過不代替它們。
3. U3：3D 房間及玩家造型審閱。未製作，也未核准。
4. U4/U5：正式模型動畫、完整流程、三解析度功能畫面與最終候選 ZIP。

U1 的方塊與地板範例只驗證工具；不作可玩灰模、更不是正式 3D 美術。最終候選檔名保留 `MAP001-Unity-StartRoom-Candidate-Windows-x64.zip`，未達關卡不以該名稱交付。

## 重跑入口

```powershell
pwsh -NoProfile -File tools/unity_u1.ps1 -Action sources
pwsh -NoProfile -File tools/unity_u1.ps1 -Action guard
pwsh -NoProfile -File tools/unity_u1.ps1 -Action build
pwsh -NoProfile -File tools/unity_u1.ps1 -Action launch
```

build／launch 需先完成工具與授權；每次用新輸出／日誌名稱，失敗證據不以成功重試覆蓋。

本輪未執行負載、長循環、效能基準或實際 GPU FPS 測試。九項舊快照缺失及七項效能相依測試的既有狀態不變；U1 不宣稱全套舊回歸已重跑。

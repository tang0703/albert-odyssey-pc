# MAP001 室內探索交付驗收紀錄

2026-10-15。**R1–R5 已完成：MAP001 同一室內擴展探索與鏡頭驗證通過。**

正式套件：`build/MAP001-Room-Windows-x64.zip`，54,033,566 bytes。
SHA256：`76a0a0b90bb9fa07b68f11ee9bbc3922ddc8e95c7cbab3a09225c9598162cced`。

## R5 正式長測

2026-10-15 主機前後觀測均為 `clear_in_sample_window`；未關閉使用者程序。
先前受背景負載影響的紀錄保留；本次隔離環境無 GPU 計數器的失敗探測也保留，
正式主機資料另存 `d0-20261015-host-preflight.json`／`d0-20261015-host-postflight.json`。

| 項目 | 結果 |
|---|---|
| 4K 穩定演出 | 600.016 秒，36,000 影格；平均 59.998 FPS |
| 影格時間 | P95 16.971 ms；最大 30.074 ms；無 >50 ms |
| 私有記憶體中位數 | 558,780,416 → 542,441,472 bytes，下降 2.92% |
| 節點數 | 固定 119 |
| GPU 專用／共用記憶體取樣峰值 | 395,280,384／40,550,400 bytes |

效能期間未截圖、未並行其他驗證。Release 引擎配置器記憶體不可用，使用 OS 程序記憶體；
GPU 數據每十秒取樣，前後負載觀測不宣稱能歸因整段期間所有背景活動。
原始證據：`reports/room/d0-20261015-soak/soak-4k`。
ZIP 清單、逐檔內容雜湊及解壓稽核通過；解壓後三解析度啟動證據位於
`reports/room/d0-20261015-extracted-qa`，套件稽核位於 `reports/room/d0-zip-audit.json`。

## 可執行候選版

本地目錄 `build/room-demo`，執行 `MAP001-Room.exe`。同層四個資料夾均須保留。
Windows x64、Godot 4.7.2 Compatibility；無需編輯器、光碟或 BIOS。
原有行走版及角色版 ZIP 未更動。

程式從乾淨提交 `799851bfbdc6d89363400964e1a725e01a1748d1` 匯出。
其後的 `277b6e3`、`cf3bc15` 修正宿主驗收工具的室內包路徑及路線識別，未改遊戲二進位。

| 檔案 | SHA256 |
|---|---|
| MAP001-Room.exe | `d34d36f3be1a6c49c56525ae86469b92e4f417ddf0b43cf00dd80c385c4b0562` |
| MAP001-Room.pck | `4f2a71bd3f7527ded4795715b7db6322315e0b73344f933b6befb1849f2f6428` |
| room/package.json | `4f5871775e4ff5de364cb78ed6aab695bcca5e60b57be4977d01270c7ed3e8d2` |

## 已通過

| 項目 | 實際證據 |
|---|---|
| R1 室內勘測 | 8 路線各三次重播，共 16,332 幀；613 個查表格全有實際來源證據 |
| R2 核心 | 5,061 次玩家、5,057 次完整鏡頭更新零差異；Godot 30,383 項檢查 |
| R3 畫面 | 854 幀、60,905,663 個非影子像素零差異；裝飾物 6／7 已解析 |
| R4 操作 | 三外觀 15,183 次更新零差異；61,061 項整合檢查 |
| 真實 GPU 對照 | RTX 4070 Ti SUPER，32 個來源視窗的非影子像素零差異 |
| 舊行走與角色 | 1,680 次移動、6,156 次三外觀回歸保持通過 |
| 戰鬥、資源驗證台 | 可用 Godot 核心、UI、演出、時序與封裝回歸通過 |
| Python | 完整批次 354 項：345 通過、9 項舊快照不可用；另新增室內封裝 5 項通過 |
| 宿主長測判定器 | 55 項合成故障／健康資料檢查通過，不能代替實際長測 |
| Windows 候選封裝 | 封閉 PCK 與四包清單、來源版本及內容雜湊通過 |

1080p、1440p、4K 均已從獨立程序啟動，保存實際截圖並檢查文字、角色、背景接縫與定位。
首次確認完整渲染面的宿主觀測值分別為 2,774.877／2,011.154／2,053.066 ms；輪詢粒度
100 ms，未清空 OS 磁碟快取，因此只代表新程序啟動，不能當作冷機磁碟效能。

本地證據：`reports/room/qa-release-3`、`r4-ui.json`、`r4-gpu.json`、`graphics-validation.json`、
`decoration-validation.json`、`acceptance-summary.json`。圖像／RAM／快照與含来源資料包不納入 Git。

## 2026-10-09 歷史待驗紀錄（已由上方正式結果完成）

宿主前置及複查仍發現背景遊戲負載，尚未開始 4K 600 秒量測，未關閉使用者程序。
來源觀測留於 `environment-preflight.json` 及 `environment-preflight-recheck.json`。
`acceptance-summary.json` 的 `passed` 為 false；效能欄位為 null。

1. 背景遊戲退出後重新做宿主前置觀測。
2. 獨立 4K 暖機及 600 秒重播，期間不截圖、不並行驗證；核對 FPS／P95／尖峰、程序記憶體、GPU 記憶體及節點。
3. 完成宿主後置觀測，匯總正式報告；若有可重現 >100 ms 尖峰，先定位修正。
4. 寫入候選包的正式驗收摘要並重新生成內容清單；產生 `MAP001-Room-Windows-x64.zip`，核對 ZIP／解壓內容及解壓後冷啟動。
5. 記錄 ZIP SHA256，提交最終 R5 紀錄並同步 GitHub。

```powershell
& tools/character_environment_probe.ps1 -ReportPath reports/room/environment-preflight-clear.json -Phase preflight
& tools/room_qa.ps1 -Executable G:/codex/SS/pc-remake/build/room-demo/MAP001-Room.exe -OutputRoot G:/codex/SS/pc-remake/reports/room/qa-isolated-soak -SoakOnly -SoakSeconds 600
& tools/character_environment_probe.ps1 -ReportPath reports/room/environment-postflight-clear.json -Phase postflight
& ../tools/pc-remake/python/Scripts/python.exe tools/summarize_room_acceptance.py --qa reports/room/qa-release-3 --soak reports/room/qa-isolated-soak --environment-pre reports/room/environment-preflight-clear.json --environment-post reports/room/environment-postflight-clear.json --out reports/room/acceptance-summary.json
```

舊 `0.savestate` 缺失的九項測試繼續列為未能重跑，鎖定雜湊未替換。
影子省略、出口測試邊界及實際 GPU 120 FPS 未驗收均保留；不代表相鄰場景、完整 MAP001 或 Stage B 通過。

階段提交：R1 `6ba3578`、R2 `9c66949`、R3 `3f20ae7`、R4 `7235625`。

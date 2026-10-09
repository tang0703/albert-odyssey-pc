# R1：MAP001 同室內範圍與參照勘測

2026-10-09；從 `c340cba` 接續。R1 已通過；本文件不宣告室內 Windows 版本交付。

## 範圍與證據

沿用原始具名起點，沒有改寫原作 RAM、光碟或舊存檔鎖。
8 條正式路線各重播三次，共 16,332 個模擬幀；每條路線的來源、工具、
按鍵序列、記憶體、CPU 執行點與畫面輸出完全一致。

| 路線 | 每次幀數 | 用途 |
| --- | ---: | --- |
| interior | 2,731 | 床邊、中央通道、桌子外圍及階梯前 |
| contacts | 1,102 | 接牆、轉角、跨格、釋放與補足查表格 |
| perimeter | 659 | 長時間壓牆、鏡頭跟隨及外圍路線 |
| visual-west | 284 | 西側家具與鏡頭來源畫面 |
| visual-east | 285 | 東側家具、階梯前與鏡頭來源畫面 |
| exit-top / exit-center / exit-bottom | 125 / 125 / 133 | 三個方向位置接觸階梯事件界限 |

前五條基準路線共 5,061 次角色更新、5,057 次完整鏡頭更新，Python 連續推演零差異。
四條路線在捕捉尾端停於鏡頭執行中途，報告保留未完成的 checkpoints，
沒有把它們當成完整鏡頭更新，也沒有把模擬幀尾直接當成完整邏輯更新。
其他兩次重播的所有輸出與基準完全相同。

以全部 17 個移動欄位建立可達狀態稽核，使用單方向及放開按鍵，
在原作事件界限前得到 36,424 個模型狀態、4,526 個位置、613 個必要查表格。
這個模型集合只用來找採樣缺口；613 格全部都有通過原作逐更新比較的實際查表紀錄。
沒有填滿外接矩形，也沒有以單一旗標判定牆壁。來源可達座標約為
X 572–852、Y 1606–1770，這些極值不是新的矩形允許域。

## 階梯測試邊界

原作載入的第一組記錄位於 `060CB55A`，目前有兩筆。
MAP001.TWN `0x1580` 的類型 0 記錄界限為 X 856–911、Y 1680–1688；
`0x1590` 的類型 2 記錄界限為 X 848–880、Y 1648–1696，皆包含上下界。
原作座標是每像素 16 個整數單位。來源記錄與載入後記錄已逐 bytes 綁定。

三條邊界路線分別在 `(848,1654)`、`(848,1686)`、`(850,1696)`
進入類型 2 消費端，將來源腳本指標 `260E2F1A` 交給事件建立函式，
再執行控制鎖定 handler `060A14DE`。第三條同時證實下邊界為包含關係。
該腳本對應 MAP001.TWN `0x2F22`。本輪不執行這個事件或場景切換，
新入口將在接觸來源事件矩形時顯示「測試邊界」並保留整次更新。
類型 0 的出口資料已綁定，但沒有宣稱本輪實際切換到相鄰場景。

## 鏡頭與同步

已定位 `0609B028..0609B290` 的跟隨程式及 `0609AE32` 的圖層迴圈。
目前兩層皆在角色更新後，先複製原鏡頭至顯示欄位，再做跟隨與夾限。
X 跟隨區間為畫面 136–200，Y 為 88–152；每次最大鏡頭位移 8 像素。
來源限界 X 512–640、Y 1536–1568，原始值、位移及顯示欄位均逐更新比較。
這些是此來源模式的證據，不是通用 Camera2D 行為。

東西兩條 v2 路線保留每幀兩個 VDP1 framebuffer、完整顯示暫存器、命令及掃描觀察。
原作角色命令與家具／前景合成的 569 幀探索性核對通過，未解釋像素為 0。
R3 仍須驗證完整捲動背景、家具排序、被省略物件及新 PC renderer。

## 重跑與本地結果

```powershell
./tools/room_capture.ps1 -Sequence data/room/routes/interior.txt -Output reports/room/new-interior-a -SampleEvery 32
# 正式路線須各有 a/b/c；visual-* 加 -VideoEvidence -SampleEvery 1，exit-* 加 -BoundaryEvidence -SampleEvery 1。
```

在 Git 根目錄使用 `../tools/pc-remake/python/Scripts/python.exe`：

```powershell
& ../tools/pc-remake/python/Scripts/python.exe tools/verify_room_survey.py --include-video --out reports/room/r1-survey.json
& ../tools/pc-remake/python/Scripts/python.exe tools/render_room_coverage.py reports/room/r1-survey.json --out reports/room/coverage.png
```

主報告：`reports/room/r1-survey.json`，SHA256
`a6144d7ee9dda764d27234d27030725fa6a0405d5ba300d1857a6fcad0548d69`。
原作圖像、RAM、快照、逐更新 fixture 與覆蓋圖均留在 ignored `reports/room`。
新增核心／資料防護測試 6 項及既有移動測試 8 項通過。
舊有三個資料包的 manifest SHA256 完全不變。

## 下一階段

R2 將把已比較的鏡頭算術與事件測試邊界移植成獨立 GDScript 核心，
以同一批來源 fixture 驗證，並擴展精確的查表聯集。
目前主要剩餘風險集中在 R3 的來源背景與省略物件遮擋稽核；
不因 Python 模型通過而提前宣告 R2–R5 完成。
既有影子、裝飾物 6／7、省略的九項舊快照回歸及 GPU 120 FPS 限制仍保留。

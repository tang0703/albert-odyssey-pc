# R3：捲動來源圖層與完整家具遮擋

2026-10-09。R3 來源驗證通過；室內入口與 GPU 驗收仍屬 R4／R5。

## 新發現與處理

東側路線中，原先省略的裝飾物 6／7 會遮住玩家。本輪已解碼並納入，不能沿用舊版的省略範圍。
只有原作影子繼續明列省略。物件 6 固定使用圖像 46；物件 7 使用 31 段、每段 5 次更新的
155 次更新循環，涵蓋圖像 16–31。來源為 TWN `0609DDB4` → `0609DE2C` → `0609DE9C` →
`0609E00A`，物件更新位於鏡頭更新之後、繪製之前。資料表和執行碼均綁定原來源雜湊。

新增三次東側逐幀捕捉，輸出逐檔雜湊完全相同。每次 284 個完整物件更新、9,658 項同步比較
零差異，包含兩個完整 60-byte 物件及圖片指標更新前／後檢查。具名起點落在物件迴圈尾端，
其繼承尾段另列，未當作新更新。五項 Python 測試涵蓋循環、全部圖像、來源變更及無效狀態。

## 圖像與時序證據

- 西側、東側及新增物件捕捉共 854 幀；60,905,663 個非影子像素逐點零差異。
- 502,286 筆可見來源圖樣檢查，包含非圖塊對齊與視窗邊緣；9,429 筆來源貼圖檢查。
- 玩家、鏡頭、物件均由起點連續推演。原作後續狀態只供核對，不回填模型。
- 鏡頭掃描暫存器、物件執行命令各自證明 3 次更新顯示延遲，未從玩家延遲直接套用。
- 94,017 個影子色盤像素明確排除；每段首張畫面繼承快照 framebuffer，未冒充新繪製證據。
- 所有身體／家具命令均有來源排序和幾何對照；未知命令拒絕，不以任意遮罩消除差異。

新增來源圖層為世界原點 `(512,1536)`、448×256 的背景與前景；涵蓋已確認鏡頭範圍及
320×224 視窗。新增 17 張装飾物圖像保留原圖像記錄錨點、色盤與多片組合。
原三包與高清素材未更動。輸出留在本地 `reports/room/visuals`，19 張 PNG；清單 SHA256：
`15f108d71fd2a918191d7f2f270d353eb67ba4925905e05be8c37a9815887864`。

## 重跑入口

```powershell
& tools/room_capture.ps1 -Sequence data/room/routes/visual-east.txt -Output reports/room/decor-east-a -SampleEvery 1 -VideoEvidence -DecorationEvidence
# b、c 使用獨立新輸出目錄，來源及输入維持相同。
& ../tools/pc-remake/python/Scripts/python.exe tools/validate_room_decorations.py --captures reports/room/decor-east-a reports/room/decor-east-b reports/room/decor-east-c --out reports/room/decoration-validation.json
& ../tools/pc-remake/python/Scripts/python.exe tools/validate_room_graphics.py --out reports/room/graphics-validation.json
& ../tools/pc-remake/python/Scripts/python.exe tools/build_room_visuals.py
```

擷取及素材匯出拒絕覆蓋既有目錄；重建請指定新捕捉目錄或先保留舊輸出。下一步 R4 為
第四個本地資料包、獨立室內入口、同步演出佇列與操作測試。上述來源像素核對不替代 GPU 畫面驗收。

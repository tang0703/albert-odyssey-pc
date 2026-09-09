# 第三段資料定位與座標候選排除

2026-09-09：MAP001.TWN 第三段的 3,740 bytes，已在同一固定 Ymir 存檔的
Work RAM High `0xF4000` 找到唯一且完整相同的區塊，對應 Saturn 位址 `0x060F4000`。
這證明第三段資料存在於原作工作記憶體；還不能證明碰撞、玩家座標或場景入口用途。

## 可重跑的來源證據

新增 `tools/probe_scene_metadata.py`。它先核對既有來源及存檔 SHA256，
再按照 Ymir v13 SystemSaveState 的序列化順序讀取兩組 1 MiB 工作記憶體。
WRAMLow 在存檔 `0xDD`，WRAMHigh 在 `0x1000DD`；末端必須緊接 `MSH2` 標記。
這些位址只適用於固定版本與檔案，不是通用存檔格式猜測。

第三段來源 payload 在 MAP001.TWN `0x2B37C`，整段雜湊與 RAM 比對納入報告。
可按 big-endian u16 計數、後接四位元組記錄的方式完整讀到區塊末端，
計數序列為 `433, 0, 20, 0, 1, 0, 477, 0`。
其中零值也可能是對齊用字，而不是空清單；目前不宣稱有八種遊戲資料類別。

前幾組的四個數值可被看成區域座標／範圍，但最後一組有大量第三／第四欄為零的記錄。
工具只輸出原始四個 byte 與來源偏移，角色一律為 `unassigned`。
未把這些資料轉為牆壁、可通行遮罩、事件觸發點或玩家出生點。

## 排除一個錯誤座標候選

`0x060D41A4` 附近有看似座標的數字，但 TWN.BIN 反組譯顯示這是色盤搬移記錄區：

- `TWN.BIN:0xAC3E..0xAD1C` 載入記錄區、計數、RAM 色盤工作區與 `0x25F00000`。
- 每筆 6 bytes，三個 word 分別作為 operation、word count、color-word offset 使用。
- offset 乘 2，形成色彩 RAM 位址；operation 0 分支複製 16-bit 色碼。
- 此存檔的待處理計數為 0，記錄區殘留內容不當作當下有效工作項目。

因此不能拿那裡的 `0x0020`／`0x0600` 等值當成鏡頭或玩家座標。
這是受來源雜湊、指令碼與 literal 值核對的靜態程式證據；沒有新增模擬器動態追蹤。

## 工具與測試

`tools/run.ps1 -Action test` 已加入探測器，輸出 `reports/scene-metadata.json`。
摘要為 `docs/scene-metadata-validation.json`，保留 `collision_verified=false`、
`player_coordinate_verified=false`，避免後續程式誤用未驗證欄位。

本輪新增 4 項測試，共 42 項 Python 測試通過；既有 Godot 14 項契約與 9 項驗證台檢查通過。
測試涵蓋工作記憶體邊界、來源變更拒絕、記錄長度、指令／literal 變更拒絕及完整區塊對照。

另新增 `tools/DumpSceneRanges.java`，用 Ghidra 匯出限定指令範圍。
本輪對本地 `pc-smoke` 的 TWN.BIN 使用 `-readOnly -noanalysis`；Ghidra 日誌確認修改已丟棄，
沒有變更原始遊戲或繁中化成果。範圍中沒有反組譯到的資料標成 `[undecoded]`，
不把所有 word 都當成可執行指令。

可在先前已建立的同一專案中重跑（需使用原有專案內 JDK／使用者目錄設定）：

```text
analyzeHeadless .../reports/ghidra pc-smoke -process TWN.BIN -readOnly -noanalysis
  -scriptPath .../pc-remake/tools
  -postScript DumpSceneRanges.java .../reports/camera-ranges.txt 0xAC00 0xACCE 0xAD0E 0xAE20
```

這是參考呼叫形狀，省略號須換成實際絕對路徑；不屬於一般 Python／Godot 測試的前置依賴。
Ghidra 範圍匯出與執行紀錄留在 reports，不把遊戲程式反組譯全文加入 Git。

下一步應追蹤 `0x060F4000` 資料的讀取者與移動判斷，而不是從視覺疊圖推斷碰撞。
場景入口、玩家座標、鏡頭規則與碰撞仍未驗收；Stage B 尚未通過。

後續已找到 `0x260F4000` 引用與旗標表展開例程，八組 count 的歧義已解除。
本文件及探測器保留當時的結構探測紀錄；最新已驗證結果見 [旗標表重建](SCENE_FLAGS.md)。

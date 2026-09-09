# 背景圖塊來源已接回 MAP001.TWN

後續進展：第二段排列與第四段色盤也已核對目前視窗，見 [來源場景](SOURCE_SCENE.md)。
下文保留本輪最初完成圖塊比對時的範圍。

2026-09-09：已確認 MAP001.TWN 的第一個圖形區塊可解出完整 256 KiB，
與固定 Ymir 存檔的 VDP2 VRAM `0x40000..0x7FFFF` **逐位元組完全相同**。
NBG0 的 164 個、NBG1 的 176 個不同圖塊位址全部取得來源對照。
兩個數量分屬各層，可能重複，不代表合計 340 個獨立美術。

## 來源與格式

原始檔仍由 `source-lock.json` 固定雜湊。MAP001 的圖形區段從 `0xF230` 開始，
連續六筆 `u16 tag、u16 index、u32 payload_length`（big-endian）區塊，
最後四個 bytes 為 `FFFFFFFF`。六個 tag 依序 1..6，index 都是 1。
此邊界只對目前固定的 MAP001 驗證，尚未宣稱適用所有 TWN。

| 項目 | 區塊 1 | 區塊 2 |
|---|---|---|
| Payload 起點 | `0xF238` | `0x26C1C` |
| Payload 長度 | 96,732 bytes | 18,264 bytes |
| 解碼後長度 | 262,144 bytes | 65,536 bytes |
| 已知用途 | 背景圖塊區完全命中 | 尚未確認，保留為未指派資料 |

Payload 以 `05` 與 big-endian u32 解碼長度開頭，後面是 LSB-first 控制位元：
1 表示 literal，0 表示兩個 bytes 的後向複製。第一個 byte 為距離低八位；
第二個 byte 的高四位為距離高位，低四位加 3 為長度，允許重疊複製。
這與先前文字探測工具使用的 nibble 分配不同，舊模型的未命中不能排除本區塊。

解碼到宣告長度即停止，容器長度須符合四位元組對齊。
區塊 1 剩餘三個尾端 bytes 為 `010101`，在報告原樣保留，不假設填充一定是零。
錯誤模式、過大輸出、截斷、無效後向距離、超出輸出長度與額外尾端資料會拒絕。
未追蹤 CPU 解壓函式或 DMA 呼叫；目前是完整資料一致的靜態證據。

## 整合與驗證

`tools/decode_map_graphics.py` 產生來源解碼與全區比較報告。
`tools/decode_background.py` 現在使用原始檔解出的像素，並為每個圖塊提供穩定 ID、
壓縮區塊偏移、解碼後偏移與雜湊；**排列頁與色盤仍取自同一份存檔**。
這不是已完成的獨立場景載入器。

可用 `tools/run.ps1 -Action test` 重跑。產物：

- `reports/background-source.json`：六個區塊、兩段解碼結果、尾端 bytes、全區雜湊核對。
- `reports/source-background/tiles.bin`：來源解出的背景圖塊。
- `reports/source-background/block2-unassigned.bin`：用途尚未確認的第二段。
- `reports/background-layers.json`：新增 `decoded_source` 與每層 `decoded_source_tiles`。

原有 `exact_source_tiles` 仍指「不解壓的直接位元組比對」，值為 0；
新欄位 `decoded_source_tiles` 分別為 164、176，兩者不是互相矛盾。

新增 5 項測試，總計 33 項 Python 測試通過，既有 Godot 14 項契約與 9 項驗證台檢查通過。
涵蓋 literal、重疊複製、距離高位與長度低位、損毀／截斷拒絕、容器及整個 256 KiB 比對。
重新生成的兩張背景頁與兩張視窗 PNG，SHA256 均與上一輪記憶體版本完全相同。

沒有將來源 BIN／PNG 放入 Git；只提交程式、測試、說明與摘要。
背景圖塊來源已解決，但排列、原作動態更新、實際上傳呼叫、事件與碰撞仍待追查。
Stage B 整體尚未通過，未新增模擬器執行或完整遊戲畫面驗收。

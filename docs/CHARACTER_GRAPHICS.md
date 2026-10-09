# MAP001 玩家圖像來源與呈現證據

角色目前以「MAP001 玩家」識別。以下是原作素材解碼及觀察，不把截圖裁切當成圖像資源，也不以角色外觀推定姓名。

**階段狀態：**A1 的來源、像素解碼、已捕捉命令綁定與時序證據已完成。本文的逐像素前景分類是 A2 的來源對照證據；A2 的任意行走家具排序、遊戲端分層與整合驗收仍需獨立完成，不能只因這份報告通過就標記 A2 完成。

## 可重跑工具

```powershell
..\tools\pc-remake\python\Scripts\python.exe -m unittest discover -s tests -p test_character_graphics.py -v

..\tools\pc-remake\python\Scripts\python.exe tools/validate_character_graphics.py `
  --frame reports/exploration/e1-nav-05/frame-000600 `
  --snapshot-sha256 72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54 `
  --out reports/exploration/character-source-pose-01

..\tools\pc-remake\python\Scripts\python.exe tools/validate_character_graphics.py `
  --capture reports/character/cardinal-a `
  --out reports/character/graphics-cardinal-a
```

輸出資料夾必須不存在，且必須位於本地 ignored `reports`。原作 PNG、調色盤、RAM、存檔及逐幀圖像不能提交 Git。單張模式要求明確的快照 SHA256；v2 模式先呼叫 `verify_character_capture.inspect`，通過來源、完整輸出清單、命令執行配對、同步及 framebuffer 證據後才進行圖像核對。

## 原始資源鏈

| 層級 | 本地證據 |
|---|---|
| 玩家 | 控制 slot 0，物件 `0x060C8758`，長度 `0x70` |
| 當前圖像 | actor `+34` 是圖像索引，`+58 = 0x20220158` 是 40 項指標表；`+5C` 必須等於該索引指向的記錄 |
| 拼合記錄 | `u16` 件數，接著每件 `s16 dx, s16 dy, u16 attributes` |
| 貼圖群組 | actor `+64 = 0x20220350`，40 項指標表；每組 `u16 count` 及逐件 `u16 texture_id` |
| 壓縮貼圖 | actor `+68 = 0x20220498`，43 項相對偏移；每筆 `u16 tag, id, attributes, size` 及壓縮串流 |
| 光碟檔對應 | `PARTY0.PTY + 0x0C` 的 `0x5B94` 位元組，與 low WRAM `+0x20000` 全段完全一致 |
| 調色盤 | `MAP001.TWN + 0x652DC` 的 128 位元組，與 CRAM `+0x800` 完全一致 |

`PARTY2.PTY` 也含同一份第一資源區塊。因此 `PARTY0.PTY` 是精確來源對照，單靠相同位元組不能判定原作當時究竟讀入哪個檔案。

三份來源檔的完整 SHA256 固定於 `tools/character_graphics.py`；來源檔變更、截斷及執行中變更不得默默接受。報告保留來源檔路徑、長度、SHA256、偏移、RAM 位址與命令原文。

## 解壓與像素

`TWN.BIN + 0x1ED8E`（執行位址 `0x060AED8E`）是此資源的解壓例程。控制位元由低位至高位；1 是 literal，0 是兩位元組參照：

- 距離為 `lo | ((hi & 0xF0) << 4)`。
- 長度為 `(hi & 0x0F) + 3`。
- 使用 4096 位元組滑動環；初始寫入位置是 0。
- SH-2 只清空前 `0xFEE` 位元組；讀到尚未初始化的末端 18 位元組會被工具拒絕。
- 最後一次 copy 在所需長度達成時立即結束，與 `DT R6` 返回時點一致。

前 40 張貼圖為 32×40，最後三張為 16×24、16×16、16×16。來源記錄間有 0–3 個零對齊位元組；最後一筆到固定資源區塊末端有 5 個零位元組，工具只接受這份已鎖定來源的已知尾端。

目前核對模式是 8-bit 儲存的 64 色 VDP1 色庫（color mode 2）、VDP2 sprite type 6、CRAM mode 1。來源索引 0 為透明。Ymir `ConvertRGB555to888` 使用 `component << 3`，並未做低位複製；以 31 轉為 255 會造成錯誤像素對照。工具沿用捕捉時的色彩偏移寄存器，不推測其他混色模式。

## 第一張姿勢的實證

已保存 `reports/exploration/character-source-pose-01/report.json` 及解碼 PNG：

- image 0 → texture 4，來源記錄 `PARTY0.PTY + 0xDE0`。
- 1280 個解壓位元組與 VDP1 VRAM `+0x7C180` 完全一致，SHA256 為 `04940a52d988ce36dd33c74e7c00ba9d1a96560b63d573e712df02a672f2a9d1`。
- actor 原始座標 `(0x2CE0, 0x65A0)`，除以 16 得世界腳底 `(718,1626)`；固定相機 `(544,1536)` 得畫面腳底 `(174,90)`。
- image 記錄偏移 `(-16,-35)`，VDP1 body 命令 `+0x180` 的四頂點為 `(158,55),(189,55),(189,94),(158,94)`。
- 解碼後 588 個非透明像素與同一份快照的 video RGBA 全數相同。
- 附近 `+0x160` 使用同一貼圖但幾何縮短、反向且色庫不同，屬投影候選；不把它混成身體貼圖。

這份舊 seed 的 RAM 命令表會在 `0x280` 遇到 opcode F，因此報告只稱命令候選及可見像素吻合，`command_execution_verified` 明確為 false。實際執行證明須由新版 v2 捕捉建立。

## v2 動態呈現模型

工具把以下證據分開：來源解碼、實際 command fetch/execute、command-time texture/CRAM blob、draw bank、逐行 compose bank、完整 video、seed 繼承。

四條正式路線共 684 幀均通過下列關係：

1. `execute[f]` 觀察到的 actor 等於 `sample[f-1]`。
2. 真正 body 命令的圖像、位置與鏡射，對應 `sample[max(f-2,0)]`。
3. 命令的位置使用 `sample[f]` 的 `SCXIN0/SCYIN0`。相機捲動時，執行當下舊寄存器值不能代替命令即將呈現時的相機。
4. 該 draw bank 在 `video[f+1]` 的 224 條掃描線被讀取。因此呈現的身體對應 `sample[max(video_frame-3,0)]`。
5. 最初 video 的身體來自 seed framebuffer。工具要求該 bank 的完整 SHA256 與 seed 相同，另做像素核對；不捏造捕捉前的命令執行事件。
6. 實際背景掃描使用 `vdp1_begin` 時的相機；工具要求所有可見掃描期間的完整寄存器觀測一致。CPU 在可見掃描結束後、`software_video_complete` 回呼之前已更新下一個相機，不能以回呼末值反推剛完成的畫面。
7. 掃描後的 VBlank 會清除剛顯示的 bank。用來核對的完整 framebuffer 是前一個 sample 的同 bank，且 SHA256 必須等於 `software_video_complete` 當下該 bank 的 SHA256；不能使用已清除的 frame-end bank。

這是一個每份捕捉都必須再次通過的有限場景模型，不能推廣為所有 Saturn 遊戲、場景或速度下的固定延遲。`+14` bit 0 與觀察到的 CMDCTRL 水平鏡射相關性逐幀比較；其他圖像屬性、垂直鏡射及多件拼合尚未通過時會拒絕。

原作動態相機必須保留用於原作像素核對；PC 固定鏡頭以同一世界腳底重新投影。不能縮小既有碰撞驗證範圍掩蓋捲動差異。`0x060DDDC4` 的回寫資料是玩家世界座標，不能直接當作相機座標。

## 遮擋及目前界線

工具分別比較身體的 16-bit framebuffer 色碼與最終 RGBA：

- framebuffer 色碼不同：保留為 VDP1 後續寫入或其他圖形作用候選。
- framebuffer 色碼相同但 video RGBA 不同：保留為 VDP2 合成或色彩作用候選。
- 差異逐像素記錄，不能自動當作解碼失敗，也不能刪去差異後宣稱通過。

正式四路線已完成**全部身體非透明像素**的正反預測，不只對有差異的點找相似顏色：

| 路線 | 幀數 | 身體像素 | 原身體可見 | VDP1 物件覆蓋 | NBG 前景覆蓋 | 未解釋 |
|---|---:|---:|---:|---:|---:|---:|
| cardinal | 364 | 206566 | 195939 | 833 | 9794 | 0 |
| corners | 170 | 96094 | 96094 | 0 | 0 | 0 |
| open | 118 | 67811 | 64738 | 3073 | 0 | 0 |
| release | 32 | 18268 | 18268 | 0 | 0 | 0 |
| 合計 | 684 | 388739 | 375039 | 3906 | 9794 | 0 |

VDP1 覆蓋由身體之後實際執行的命令決定。其貼圖必須完整匹配 `MAP001.V1N`（SHA256 `dcad16cc0fe4f843fbb3eba134adf264c66352ab590e4ace14381cd0b6fbf9a4`），色庫必須匹配 `MAP001.TWN` 的來源偏移；每個非透明 texel 依命令原文及鏡射預測寫入色碼，再和完整 framebuffer 比較。

NBG0/1 使用原始 layout、tile、palette。compact pattern bit 13（VDP2 pattern bit 29）搭配 `SFPRMD=5` 產生優先權 3，玩家 sprite type 6 的色码 `0x20xx` 經 PRISB 得優先權 2。非透明前景點蓋住優先權 2 的角色，與原作像素全部相同。工具也逐點核對 source layout 與呈現 bank 的 pattern，不能用任意圖片當遮罩。

核准索引：`reports/character/presentation-index.json`。其 SHA256 為 `3ccaed1cf54eb3c17873120c3795c8d89e711998b342d66e8b42dfd7579e8d38`，指向四份 `graphics-final-<route>-a/report.json`。每份明列 `passed`、`source_command_binding_passed`、`command_execution_verified`、`observed_delay_profile_passed`、`visible_composition_passed`；`counts.unexplained_pixels` 必須是 0。早期 `graphics-*-a`、`-v2`、`-v3` 報告只保留診斷歷程，包裝不能自行挑舊版。

`reports/character/foreground-source/nbg-priority-foreground.png` 是固定 `(544,1536)` 相機的 320×224 透明前景，依來源優先權產生，附獨立 manifest。它只代表 NBG 層；家具須依獨立場景排序模型決定身體前後，不能把所有家具固定畫在身體之上。

29 項合成測試涵蓋解壓位元組語意、環回及未初始化區、透明與 RGB555、正負座標、左右/上下鏡射、圖像唯一綁定、來源截斷、4-bit 物件 texel、framebuffer 覆蓋與前景 pattern。這個關卡只驗證身體的非透明像素；身體之外的投影、陰影及其他場景像素不在本關卡範圍，仍不宣稱已重建通用 VDP1 變形、陰影、整體 VDP2 合成器或全遊戲角色系統。

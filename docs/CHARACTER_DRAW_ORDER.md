# MAP001 玩家與場景物件繪製順序

本文件記錄原作排序程式、來源命令核對方法與使用邊界。這不是完整 Saturn 場景光柵器，也不表示裝飾動畫、影子或任意地圖已完成還原。

## 可重跑入口

```powershell
..\tools\pc-remake\python\Scripts\python.exe -m unittest discover -s tests -p test_character_draw_order.py -v
..\tools\pc-remake\python\Scripts\python.exe tools/character_draw_order.py `
  reports/character/cardinal-a reports/character/corners-a `
  reports/character/open-a reports/character/release-a `
  --output reports/character/draw-order-validation.json
```

驗證器先呼叫 `verify_character_capture.inspect`，驗證封存來源、工具、逐檔雜湊、回呼順序、影像與時間邊界；再解析 `command_execute_before` 的實際執行順序。既有 A1 四組三次重播另由 `character-reference-lock.json` 與 `replay-*.json` 鎖定。本驗證逐組讀取，不同時保留多份完整回呼資料。

## 原作排序規則

來源為 `work/extract/TWN.BIN` 與 `work/extract/0`。完整 SHA256 及以下位元組區間由工具固定並驗證，報告亦保存。

| 程式範圍 | 說明 |
|---|---|
| `06095030–0609580D` | 掃描場景物件與角色、插入排序桶、分階段繪製 |
| `06098D46–0609935B` | 場景物件圖像子件、座標、調色盤與優先序輸出 |
| `06086F20–0608705B` | 優先序鏈尾端插入，按優先序走訪並建立 CMDLINK |

先掃描 `060CA358` 起的 64 個場景物件，間距 `0x3C`；再掃描 `060C8758` 起的 32 個角色，間距 `0x70`。各陣列依 slot 由小到大。活動、隱藏、圖像及角色 parent 狀態均參與來源篩選；本模型只接受已證實的室內分支與單一受控玩家。

物件／角色 `+0x16` 的 `0x10` 決定是否進入 Y 排序表；此旗標與碰撞沒有通用對應關係。排序鍵為：

```
key = trunc_toward_zero((world_y_raw - camera_y_raw) / 16) + 256
```

原座標單位為 1/16 像素。初始鍵須在 40–700。若鍵已被占用，往下一格尋找空位，最多至 767。家具先插入，所以同鍵角色可能被推到其後；多次衝突也可能跨越其他物件的初始鍵。這不能以一般穩定 Y 排序替代。原作在桶全滿時有覆蓋行為，本有界模型拒絕該未驗證狀態。

未進入 Y 表的物件先產生命令；Y 表則先走影子階段，再走角色本體／家具階段。這只是命令產生順序。核心另將命令接入優先序 FIFO 鏈，超出 256 個優先序時夾到 255，最後以優先序由小到大執行。室內普通家具及角色為 10，slot 6、7 的裝飾物請求 612、1124 等值而夾到 255，因此它們雖然較早取得命令地址，實際在普通家具／角色之後執行。

**不可依命令地址大小排列。** 例如 `0x100` 的装飾命令可能在 `0x260` 之後執行；工具使用已驗證的實際 execute 回呼序列。

## 家具資料介面

`tools/character_draw_order.py` 提供：

- `scene_from_snapshot(high, low, ...)`：提取來源世界位置、影像記錄、子件偏移、貼圖位置、尺寸、palette、朝向及排序資訊。呼叫方先驗證捕捉 manifest。
- `bucket_order(objects, actors)`：輸入 `slot / y_sorted / y_raw / camera_y_raw`，傳回直接清單、排序後清單及各鍵移位過程。
- `priority_order(pieces, 256)`：保留同優先序 FIFO 的核心排序。
- `compare_commands(scene, events)`：以圖像、尺寸、palette、色彩模式、朝向與四頂點辨識子件，再比較完整本體／物件次序；缺失、多出、重複或順序錯誤均拒絕。

固定鏡頭的 PC 顯示可用 `(544,1536)` 像素重新投影；原作對照保留其實際捲動相機，不縮小原先 108 格碰撞驗證域。已捕捉相機範圍 X=512–544、Y=1536–1554 像素，次要位移為零。模型不推導或宣稱還原鏡頭跟隨規則。

| slot | 世界座標（像素） | 圖像子件偏移 | runtime texture ID | 尺寸 |
|---:|---|---|---:|---|
| 0 | 800,1744 | -14,-19 | 249 | 24×24 |
| 1 | 680,1648 | -24,-40 | 253 | 48×40 |
| 2 | 714,1696 | -21,-24 | 247 | 32×24 |
| 3 | 752,1696 | -21,-24 | 247 | 32×24 |
| 4 | 752,1745 | -8,-40 | 257 | 16×24 |
| 5 | 757,1756 | -8,-32 | 263 | 16×16 |

上述 ID 是執行期貼圖表索引，不能直接當作 MAP001.V1N 檔案索引。PNG 導出必須另外比對來源位元組。子件偏移來自 `+0x30` 所指的影像記錄，每筆包含 signed X、signed Y、attributes；`attributes & 255` 加上物件 `+0x0E` 得到 runtime texture ID。`source_anchor=-offset` 只描述此原始記錄座標，不宣稱是視覺腳底。

## 時間邊界與證據範圍

執行幀 `f` 的玩家及六件家具使用來源狀態 `max(f-2,0)`；幾何投影相機取目標 sample `f` 的 VDP2 SCXIN0／SCYIN0（N0、N1 必須一致，fractional scroll 必須為零）。不能把整個來源 RAM 快照稱為同步完成的繪圖狀態：例如 corners f56，來源 f54 的相機 RAM 尚為 X540，而實際命令及目標 VDP2 已是 X538。報告分別記錄兩個來源時點。

slot 7 是原作裝飾動畫。`RunFrame` 邊界常落在 `0609DDxx` 物件更新迴圈，讀到的圖像指標可能在其更新前或後。工具只允許相鄰兩個封存快照 `max(f-2,0)`、`max(f-1,0)` 的完整 slot 7 記錄，逐子件以來源圖像、四頂點、palette 及次序綁定；報告記錄匹配快照，且 `decoration7_animation_timing_validated=false`。這是來源命令辨識與優先序核對，不是裝飾動畫的連續重播模型。

來源主迴圈依序呼叫角色更新（`0609159A`）、物件更新（`060915A6`）、繪製（`060915DE`），支持需要區別這些階段。若今後要製作裝飾動畫，應補其函式入口／出口同步採樣，不沿用玩家動畫的時間模型。

影子只被明確辨識為先於本體的獨立 `0x27C0` 路徑，本工具不驗證影子幾何或混色。VDP2 前景與逐像素顯示合成由 character_graphics 的獨立驗證負責；不能拿本工具的命令排序通過代替完整畫面通過。

## 具體遮擋核對與測試

- cardinal f9：玩家本體在桌子之前執行，桌子可遮住玩家。
- open f31：桌子在玩家之前；兩張椅子在玩家之後，可遮住玩家鞋子。
- 測試覆盖同鍵家具／角色、連續桶衝突、負數除法、越界／溢位、同優先序 FIFO、命令地址與執行序不同、缺少／重複／陌生命令、mirror／palette／模式改動、來源雜湊與 RAM 截斷拒絕。

本次正式結果：13/13 合成測試通過；四條唯一路線共 684 幀、9,594 筆 execute 回呼通過。其中 7,542 筆為完整綁定的角色本體／場景子件，另 2,052 筆為每幀兩個狀態命令與一個明列排除幾何驗證的影子命令。未綁定本體／物件命令與排序差異均為零。slot 7 有 122 幀使用相鄰較晚的封存記錄。

完整結果為本地 `reports/character/draw-order-validation.json`（904,822 bytes；SHA256 `bb21c005b63d2ae2ff4909115d32ad96fafe7dbfe4d8897bedc11f6edcc0eab8`）。原作 RAM、圖片、捕捉輸出與此大型報告留在本地，不加入 Git。

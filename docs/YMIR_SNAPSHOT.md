# 同一存檔的顯示資料與色盤樣本

## 2026-09-09 本輪結果

新增 `tools/read_ymir_state.py`，從單一既有 Ymir 存檔取出 VDP1／VDP2 VRAM、
CRAM、framebuffer、10 個 VDP1 暫存器、142 個 VDP2 暫存器及繪圖狀態。
這些區域共用同一存檔來源，不混合先前分開擷取的 RAM。

存檔 SHA256：`615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab`。
僅支援經核對的 cereal little-endian v13 格式與這一份 fixture，
`savestate-lock.json` 固定長度、SHA256、VDP 區域起點及暫存器順序。
不是通用即時存檔讀取器，不會自動接受另一份存檔；原始存檔不納入 Git。

| 核對項目 | 存檔值 | 意義 |
|---|---|---|
| VDP 區域 | `0x203551` | `VDP#` 標記之後，先讀取固定長度記憶體陣列 |
| RAMCTL | `0x1100` | CRAM mode 1，2048 個 RGB555 色碼 |
| SPCTL | `0x0036` | sprite type 6；色碼低 10 位與優先權分離 |
| CRAOFB | `0x0040` | sprite 色盤基底為 1024 |
| BGON | `0x000B` | 取得 NBG0、NBG1、NBG3 啟用狀態，尚未還原地圖排列 |
| drawing | `true` | 存檔當下仍處於繪圖中 |
| COPR × 8／nextCommandAddress | `0x400` | 當下執行位置，與從 0 重新追蹤的末端不同 |

這次存檔的 VRAM、CRAM 雜湊與先前鬆散 dumps 不同，進一步說明不能混用兩套資料。
framebuffer 則比對相同；單一相同區塊不足以證明整體狀態一致。

## 修正「非法指令停止」的解讀

已查閱固定 commit `54fead6a0001d3e4b6741a8d095ee8342266c3dc` 的
[Ymir VDP1ProcessCommand](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/src/ymir/hw/vdp/vdp.cpp#L1012)。
沒有 END 且非 skip 的非法命令會提前返回本次取指成本，未呼叫 VDP1EndFrame，
也未走到更新 nextCommandAddress 的程式碼。因此不能將 0xF 當成正常 END。
這是固定版本模擬器的程式行為，不是已驗證的 Saturn 硬體行為。

從本次存檔的位址 0 靜態重追命令鏈會在 `0x2E00` 遇到 0xF；
但存檔的真實執行位置是 `0x400`。這次證據不支持「原作當時已執行到 0x2E00」的說法。
下一步需核對命令表更新／緩衝切換及執行進度，不能只憑 RAM 靜態列表下結論。

## 色盤解碼與產物

6 筆命令的紋理完整位元組、尺寸與深度可對上 MAP001.V1N。
以此存檔的 bank、sprite type、CRAM offset 及 RGB555 值產生 6 張 RGBA 樣本。
從內容可看到家具等場景物件；不將其認定為主角動畫或已確定用途的角色素材。
重複來源 ID 保留為候選，不武斷選擇。

解碼器目前只接受核對過的 16／64 色 bank、CRAM mode 1、sprite type 6、
16-bit framebuffer 與 ECD disabled。處理 SPD、色碼遮罩、RGB555 展開與 signed-9 色彩偏移；
未知模式、mesh、色彩運算或特殊 shadow 色碼會拒絕，不猜測替代色盤。

執行 `tools/run.ps1 -Action test` 後產生：

- `reports/coherent-vdp-snapshot.json`：記憶體來源範圍與雜湊、暫存器、繪圖狀態、素材來源與限制。
- `reports/snapshot-palettes/command-*.png`：原尺寸 RGBA 素材，未鏡射、扭曲或拼合。
- `reports/snapshot-palettes/contact.png`：3 倍最近鄰排列供人工檢查，不是超解析度美術。

目前沒有套用最終畫面的裁切、優先權、背景遮擋或合成，也沒有完成原作截圖逐像素比較。
可稱為「該存檔色盤的素材樣本」，不能稱為完整原色場景驗收。

## 驗證與下一步

本輪新增 6 項測試；合計 23 項 Python 測試通過，另有既有 Godot 14 項契約檢查
與 9 項驗證台檢查通過。驗證涵蓋輸入雜湊／截斷拒絕、暫存器讀取、色盤與優先權
位元遮罩、RGB 通道、透明像素、signed 色彩偏移及不支援模式拒絕。
本輪沒有新增模擬器執行或 4K 效能測試。

下一個關卡是取得對應畫面並核對實際執行中的命令表，再利用本輪已取得的 VDP2
圖層／圖塊暫存器還原背景排列。碰撞、事件入口與戰鬥規則仍未完成，Stage B 尚未通過。

格式與色彩規則依據：
[序列化順序](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/apps/ymir-sdl3/src/serdes/cereal_savestate.hpp#L526)、
[存檔欄位](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/include/ymir/savestate/savestate_vdp.hpp)、
[色盤查詢與 type 6](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/src/ymir/hw/vdp/renderer/vdp_renderer_sw.cpp#L5309)、
[暫存器定義](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/include/ymir/hw/vdp/vdp2_regs.hpp)。
下載的原始碼保留在上層 tools；雜湊記錄在 fixture lock，未將整份第三方原始碼放入此倉庫。

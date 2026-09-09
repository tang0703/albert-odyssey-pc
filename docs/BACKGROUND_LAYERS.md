# 背景圖層還原：2026-09-09

後續進展：圖塊已從 MAP001.TWN 解壓並完成整區比對，見 [背景來源](BACKGROUND_SOURCE.md)。
下文保留最初直接比對未命中的結果；現在產圖已改用來源像素，排列與色盤仍來自存檔。

已從上一輪固定的同一份 Ymir 存檔還原 NBG0、NBG1 的靜態背景頁與視窗。
可辨識床鋪、桌面、窗戶、木地板與地毯。這是記憶體資料的分層解碼，
不是整個村莊、碰撞地圖或完整遊戲畫面驗收。

| 項目 | NBG0 | NBG1 |
|---|---|---|
| 圖塊 | 16×16、256 色 | 16×16、256 色 |
| 排列 | 每項 4 bytes、每頁 32×32 項 | 同左 |
| VRAM 排列頁起點 | `0x00000` | `0x02000` |
| A/B/C/D 平面 | 四個平面引用同一頁 | 四個平面引用同一頁 |
| 頁面尺寸 | 512×512 | 512×512 |
| 不同圖塊位址數 | 164 | 176 |
| 整數捲動座標 | X=544，Y=1536 | 同左 |
| 當前視窗 | 320×224 | 320×224 |

工具解析 two-word pattern 的圖塊位址、色盤與水平／垂直翻轉，按 2×2 個 8×8 cells
排列成 16×16 圖塊。色彩來自同一存檔 CRAM，索引 0 依 BGON 設定保留透明。
視窗依捲動座標跨越平面，不能把大於 512 的座標直接截斷成圖外。

## 產物與重跑

`tools/run.ps1 -Action test` 會執行新工具 `tools/decode_background.py`，產生：

- `reports/background/nbg0-page-00000.png`、`nbg1-page-02000.png`：512×512 RGBA 圖層頁。
- `reports/background/nbg0-viewport.png`、`nbg1-viewport.png`：320×224 的分層視窗。
- `reports/background-layers.json`：每個排列項目的 VRAM 位址、原始 word、圖塊位址／雜湊與來源比對。

PNG 與詳細報告保留本地；Git 只收程式、測試、說明與雜湊摘要。
來源存檔、CRAM 與 VRAM 仍受既有 SHA256 鎖定。

## 已驗證與未解決

新增 5 項測試：四個 cell 的位置、色盤／翻轉／透明、排列步幅與來源位址、
跨平面回繞、實際暫存器與拒絕不支援設定、兩層實際資料解析。
合計 28 項 Python 測試、既有 Godot 14 項契約與 9 項驗證台檢查通過。

對 MAP001.SNF、MAP001.TWN、MAP001.V1N 做完整 256-byte 圖塊直接比對，
兩層都沒有高資訊量圖塊的精確命中。這只排除本次直接位元組比對，
不能證明來源不在這些檔案，也不能斷言採用哪一種壓縮。
下一步需追查來源解壓、重排或上傳流程，才能把 VRAM 位址接回原始檔偏移。

目前不模擬 VRAM 存取時序、視窗裁切、優先權、色彩運算／偏移、NBG3 或 VDP1 精靈合成。
只接受本次已核對的顯示模式、圖塊格式與整數 1:1 捲動；不支援設定明確拒絕。
沒有把兩層猜測合成、添加碰撞或擴張成未確認的地圖。
Stage B 仍未通過；下一個驗收點是背景來源追溯及與原作同一畫面的比對。

格式依據為固定 Ymir commit `54fead6a0001d3e4b6741a8d095ee8342266c3dc`：
[背景頁與圖塊處理](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/src/ymir/hw/vdp/renderer/vdp_renderer_sw.cpp#L4980)、
[two-word pattern 欄位](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/include/ymir/hw/vdp/renderer/vdp_renderer_defs.hpp#L70)、
[頁面位址計算](https://github.com/StrikerX3/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/include/ymir/hw/vdp/vdp2_defs.hpp#L145)。

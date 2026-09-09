# Stage B：VDP1 命令鏈與素材綁定

## 本輪結論（2026-09-09）

已實作嚴格 CMDCTRL 命令鏈追蹤，取代把連續記憶體掃描當成繪圖順序的做法。
以既有 BizHawk `ascii_proof_page_01` 快照為基準，走訪 31 筆命令，包含 3 筆跳過、
25 筆紋理命令。9 筆紋理命令的尺寸、位元深度與完整像素雜湊可對上 MAP001.V1N。
其中 4 筆只有單一來源候選，5 筆有重複素材候選，共 18 個可能來源 ID；
不能把這個數字解讀成 18 個已辨認角色或獨立動畫影格。

命令鏈沒有取得合法 END：在 `0x2E40` 的 skip-next 後，`0x2E60` 讀到
`CMDCTRL=0x060F`，低四位命令碼 0xF 不在手冊合法清單內。
工具保留前綴證據，但輸出 `rejected_incomplete`，不宣告完整畫面重現。
未修改來源 RAM、補寫 END 或跳過未知指令使它「通過」。

## 可重跑

執行 `tools/run.ps1 -Action test` 會包含命令鏈測試與來源驗證，並產生：

- `reports/vdp1-trace.json`：命令順序、原始欄位、鏡射、局部座標、色彩模式、
  SPD/ECD 設定、精確來源候選與停止原因。
- `reports/capture-audit.json`：8 個既有 VDP1 快照與 3 個相關 RAM／framebuffer 檔案的核對結果。

`capture-lock.json` 固定這 11 個本地輸入的 SHA256；新快照不會自動被工具接受。
這些雜湊證明檔案身分，不證明擷取同步或完成一幀。原始快照仍留在 Git 外。

## 手冊依據與處理範圍

追蹤支援 next、assign、單層 call/return 及其 skip 形式；END 優先於其他控制欄位。
拒絕迴圈、越界、不對齊、巢狀 call、無 call 的 return、非法命令與步數超限。
跳過的局部座標命令不改變後續座標狀態。

紋理比對同時檢查完整封裝像素、寬高與深度；保留所有重複候選，不擅自選一個 ID。
座標保留原始 word 及 signed-16 解讀供診斷，目前沒有實作硬體座標範圍、裁切、
縮放／扭曲取樣、mesh、Gouraud、優先權或最終合成。因此「命令前綴引用」不等於可見像素。

基準前綴有 23 筆 16 色 bank 命令及 2 筆 64 色 bank 命令。
SPD/ECD 已解析成明確欄位；尚未套用為最終透明圖。原色仍須同一快照的 VDP2 設定及 CRAM。

參考 Sega 原廠手冊的保存版本：
[CMDCTRL](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_10.htm)、
[CMDLINK](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_20.htm)、
[CMDPMOD](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_30.htm)、
[色彩模式](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_36.htm)、
[SPD](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_35.htm)、
[ECD](https://www.infochunk.com/saturn/segahtml_en/hard/vdp1/hon/p06_34.htm)。

## 快照稽核與下一個驗收點

8 個已找到的 VDP1 快照都在遇到合法 END 前碰到命令碼 0xF，停止位置分別為
`0x480`、`0x2E60` 或 `0x2E80`。這不能直接斷言快照損毀；
仍需查明是命令更新中的狀態、原作依賴未定義指令停止，或擷取時點／執行狀態造成差異。

Ymir 同資料夾內找到 4096 bytes CRAM、VDP2 VRAM 與 VDP1 framebuffer，
但尚無經核對的同步暫存器紀錄。檔案時間相同不足以證明同一顯示狀態，
不能與另一個 BizHawk 快照混用來宣稱還原原色。

下一個驗收點是取得同一暫停點的截圖、兩組 VRAM、CRAM 及 VDP1/VDP2 暫存器：

1. 核對 VDP1 執行／結束狀態與命令位址，解釋 0xF 的實際行為。
2. 核對 VDP2 sprite type、色彩 RAM 模式／偏移與優先權，再建立命令色盤對應。
3. 取得 VDP2 圖層、pattern-name、字元圖塊、捲動與平面位址設定，再追溯背景來源。

碰撞、動畫時序、事件入口與戰鬥規則仍是後續獨立關卡。
本輪無需使用者補填未知格式；以上資料須從模擬器或逆向結果取得。

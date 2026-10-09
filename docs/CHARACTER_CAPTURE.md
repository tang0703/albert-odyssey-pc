# A1：MAP001 角色同步捕捉基準

本關卡完成同一室內種子的四條路線、各三次逐幀重播與來源驗證。這是 **CPU／VDP 同步捕捉與重播通過**，不代表角色名稱、圖像組合、動畫模型或高清演出已驗收；原作 Stage B 亦未因此通過。

版本化入口為 [character-reference-lock.json](../character-reference-lock.json)。清單釘選室內種子、既有來源清單、v2 建置與來源程式、四份路線、十二份 capture manifest、四份重播報告及驗證工具。原作 RAM、framebuffer、CRAM、紋理 blob、畫面、savestate 與完整報告保留於被忽略的 `reports/character/`，不納入 Git。

## 已鎖定來源與執行方式

- 種子沿用 `exploration-reference-lock.json` 的正式 `e1-nav-05/frame-000600/state.savestate`，SHA256 `72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54`。
- Ymir v0.3.3 revision `54fead6a0001d3e4b6741a8d095ee8342266c3dc`；cereal revision `ebef1e929807629befafbb2918ea1a08c7194554`。
- 新捕捉器放在 `tools/ymir_character_capture/`，只建置到 `reports/character/ymir-character-capture-build/`。
- v2 執行檔 SHA256 `9aa73006b6da2e0408ff2e542d3750faaf7cbeb0db48944b33b94d18465cdfd3`。
- 原版 `vdp.cpp` SHA256 `ab9cfce4c31f81e80874579779d8eefa976113a34a159036600fc4d9118e1202`；新建置內的觀察副本 SHA256 `ea4a29677f739b2ddcc7b88f26a4c4595a3ee112a2688a659a10e03b5b1e8997`。

官方 public callback 可觀察換 framebuffer 與 draw-finished，但沒有逐命令回呼。因此 CMake 在新 build 目錄產生單一 VDP translation unit 副本，只插入 const observer 呼叫。原固定 checkout 不被修改；完整插入程式、來源／副本 SHA 與所有 v2 原始碼 SHA 保存在 build manifest。

核心、音訊、VDP1／VDP2 都不另開執行緒；使用 Virtual RTC，沿用載入快照的時間，SH-2 cache 設定與 v1 相同。捕捉器沒有寫遊戲 RAM、改角色位置或注入動畫索引。

## 可重跑命令

```powershell
./tools/ymir_character_capture/build.ps1
./tools/ymir_character_capture/capture.ps1 `
  -Ipl 'G:/codex/SS/EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin' `
  -Disc 'G:/codex/SS/Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue' `
  -LoadState reports/exploration/e1-nav-05/frame-000600/state.savestate `
  -Sequence data/character/routes/cardinal.txt `
  -SampleEvery 1 -Output reports/character/cardinal-new-a

& ../tools/pc-remake/python/Scripts/python.exe tools/verify_character_capture.py `
  reports/character/cardinal-a reports/character/cardinal-b reports/character/cardinal-c `
  --out reports/character/replay-cardinal-new.json
```

輸出目錄必須不存在。路線檔每行是一個按鍵及模擬幀數；毫秒按鍵工具沒有參與正式採樣。capture wrapper 釘選 BIOS、CUE、全部引用光碟軌、種子與路線檔，捕捉後重查雜湊。重新驗證時需保留 build 及其觀察副本；不能用另一個 executable 冒充已鎖定版本。

## 採樣時點與圖像資料

每個 RunFrame 都要求恰一次 software video callback。每個 CPU hook、VDP event、逐幀摘要共用 `event_index`，另記 `frame` 與 Ymir `scheduler_count`。同 scheduler count 的事件仍以全域序號排序。scheduler 是 Ymir 批次事件時鐘，不是實體 Saturn 的逐微操作測量。

- CPU hook 保留 16 個暫存器、PR、R4 物件完整 112 bytes，以及 watch 的 raw bytes／SHA。包含 input gate、actor loop、dispatch、velocity、動畫 timer `060AC0B6`、reader `060AC20C`、image pointer `060AC34A`、collision entry 與實際 PR 返回。
- 初始 `sample_boundary` 位於載入種子後、第一次 RunFrame 前，event index 為 1。第 N 幀樣本位於 RunFrame 返回後，緊接該幀摘要。
- 每採樣幀保存 WRAM-high／low、VDP1／2 VRAM、CRAM、兩個各 256 KiB 的 VDP1 framebuffer、named VDP1 寄存器與 142 個 VDP2 寄存器；首尾另外保存官方完整 state。
- 每個真正 `command_execute_before` 保存執行當時 32-byte command、紋理 span、CRAM，以及適用時的 LUT／Gouraud table。payload 以 SHA256 去重 blob 保存，並非拿幀末 VRAM 代替。`command_fetch` 與 renderer dispatch 前後分別記錄。
- public swap callback 在 bank bit 翻轉前，另有 `vdp1_swap_after_flip`；每條 VDP2 render line 都記當時使用的 bank 及其歸屬的 `compose_video_serial`。
- 最終 RGBA／PPM 屬於 software video callback；初始 frame 0 沒有新 video callback，不補造初始畫面。

**畫面完成後，VDP1 可能已清除同一 bank。** 因此 post-RunFrame 的同 bank 檔不一定就是剛合成影片所讀的內容。圖像驗證必須先依逐行 bank 與 callback 當時 framebuffer SHA 找到相同 payload，再比對像素；若沒有相同 hash 的已保存 bytes，應補抓資料，不能憑 bank 編號推測。從 command 執行到可見畫面的延遲仍屬後續圖像／動畫驗證。

`sample.vdp2.VCNT` 是內部垂直計數；address-ordered register 的 VCNT 是外部讀取 latch。驗證器將後者與 `VCNTLatch` 比較，不把這兩者混為一談。

## 無效 fetch 的明示壓縮

固定版本 Ymir 在非法 opcode 讀取時可能停在同一地址反覆 fetch。三幀小樣實際發生 335,632 次 fetch，只有 39 次真正 renderer dispatch。全部原始紀錄為 662,020,339 bytes，不能把這些非法重讀稱為圖像繪製。

v2 對相鄰同地址、同 32 bytes、同 bank 的非法 fetch 使用 `command_fetch_repeat`：首筆完整事件保留，摘要記錄其引用、重複次數、全域序號區間及首尾 scheduler count。任何其他 VDP event、CPU hook、幀摘要、換幀、bank 或命令 bytes 變更都終止該 run。所有有效 fetch 與實際 execute 前後仍逐筆記錄。

摘要不保留區間內每次非法 fetch 的 PC、actor、寄存器與個別時點，不宣稱這些 context 一直相同。全域 event count 包含壓縮前所有 fetch；不能使用 JSONL 行數代替。驗證器拒絕範圍重疊、跨 hook、錯命令、錯 bank、遺漏次數或在摘要中附帶未記錄 context。

## 驗證結果與界線

| 路線 | 每次更新 | 次數 | 每個輸出檔比較 |
|---|---:|---:|---|
| cardinal | 364 | 3 | 零差異 |
| corners | 170 | 3 | 零差異 |
| open | 118 | 3 | 零差異 |
| release | 32 | 3 | 零差異 |

共 684 次獨立路線更新、三重採樣 2,052 次。來源、建置與輸入序列先通過完整 integrity gate，再比較全部 manifest 所列輸出。重播比較逐份釋放大型 event 資料，只保留比較所需身份與 SHA；不因此省略任一檢查。

36 項無原作素材的合成故障測試通過，涵蓋來源／副本改動、revision 錯誤、重複 execute、缺少 fetch 或完成回呼、缺失／亂序 render line、未觀察 bank 變更、command-time payload、snapshot register／framebuffer 不一致及無效 RLE。測試紀錄為 `reports/character/capture-verifier-tests.log`。

三幀小樣另通過：兩次 v2 各 54 個輸出 SHA 全同；與 v1 共用的 28 個原始 payload（包含首尾完整 savestate）全同；明示 RLE 版與未壓縮 v2 的 50 個 frame／blob 檔全同。RLE trace 為 2,055,187 bytes，展開事件計數 336,428，順序無缺口。此小樣沒有使用 SCSP 差異豁免。

已封存的 v1 六份工具原始檔、舊執行檔及舊 build manifest 全部保留，v1 執行檔仍為 SHA256 `a567a976d9162318346fc2308a31d3a115673757d9a37fee619c7dd239741e0c`。舊 `615107b2…` savestate 仍缺失，相關九項回歸沒有被本輪種子取代或宣稱復原。

後續關卡需分別完成：受控物件到圖像的身份與位置綁定、原作動畫狀態／顯示時序核對、高清四向造型審閱，再製作核准的 52 張高清圖與整合。這份捕捉報告不能代替上述驗收。

# Ymir 同步捕捉器

本地逆向驗證工具；固定 Ymir 0.3.3 原始碼及 cereal 1.3.2，直接使用官方核心與 v13 序列化。沒有更改遊戲 RAM、略過 BIOS／光碟相容性檢查或以牆鐘時間模擬逐幀。

`build.ps1 -Fetch` 首次下載原始碼與相依模組；其後 `build.ps1` 使用已固定的本地來源。需要已安裝的 Visual Studio 2022 C++ 工具。所有設定只作用於本次建置，產物在 `reports/exploration/ymir-capture-build`。

以 `capture.ps1` 執行可以記錄 BIOS、CUE、全部 CUE track、初始快照、輸入序列、執行檔及所有輸出的 SHA256；C++ CLI 本身只記錄快速 XXH128 比對摘要，不能代替來源 SHA256 清單。

```powershell
./tools/ymir_capture/capture.ps1 -Ipl BIOS.bin -Disc GAME.cue -LoadState seed.savestate `
  -Sequence sequence.txt -Output reports/exploration/capture-unique-name `
  -TraceFunction 0x060AB61A -HookPC 0x060AAEAC -WatchRange 0x060C8758:0xE00
```

輸入檔每列 `單一按鍵 幀數`。允許 `none up down left right start a b c`；可用 `#` 註解。例：`right 12`、`none 3`。不接受複合方向。`SampleEvery` 預設 1，每幀保存 RAM/VDP/畫面；導航可調大以減少資料量，所有幀仍各自执行一次 `RunFrame`。

## 邊界與輸出

- `frame=0` 是載入後、尚未推進的初始狀態。此時沒有新的渲染回呼，因此不附畫面；不能將後續畫面當作 frame 0 的截圖。
- 其後每次 `RunFrame` 同步完成且必須有恰一個軟體渲染回呼，再取得 RAM/VDP/register snapshot。CPU、VDP1、VDP2、音訊不另開執行緒；RTC 使用 virtual 模式並保留已載入快照時間。冷開機固定 1994-01-01 UTC。
- `frames.jsonl` 記錄每幀方向、實際 peripheral 輪詢次數、函式呼叫數、WRAMHigh XXH128 和指定 WRAM watch ranges。
- `frame-xxxxxx/` 包含高低 WRAM、VDP1/VDP2 VRAM、CRAM、320/352 等實際尺寸的 RGBA 畫面與 PPM、sample JSON。初始與最末幀另有官方完整 `state.savestate`，所有 VDP 暫存器可由該完整快照核對。
- `hooks.jsonl` 的 `pc` 回呼發生在執行指令前，含 `r[16]`、PR、R4 物件的 0x70 bytes、指定 watch ranges。`--trace-function` 在入口記錄 R4 與 PR；到達 PR 且不在 delay slot 才記錄 return，配對的 `function_call_index` 相同。這是所指定函式的呼叫計數，**不是已證實的玩家更新序號**。尚需用真實輸入與物件證據確認玩家身份。
- 每筆 hook 與 sample 都附同一邊界的 `flags_sha256`，來源為 WRAMLow 的 `0x10000:0x20000`（Saturn 位址 `0x20210000`），方便標準庫驗證旗標表在採樣／函式內是否改變。
- 呼叫跨越最後一幀時 `pending_calls` 會非零；分析器不得拿沒有 return 的 entry 推導完整位置修正。
- 快照內原始 WRAM 陣列的 byte order 沿用 Ymir 保存格式；本工具不自行對位元組重新排列。
- 輸出資料夾必須不存在，禁止覆寫已有證據；失敗的部分資料不會有 `capture.json` 完成標記。

本工具不證明碰撞已还原。必須先完成同一 seed／同一按鍵序列至少三次重播，再與原版 SDL 畫面及資料交叉核對。原始光碟、BIOS、RAM、畫面及快照留在本地，不加入 Git 或可分享套件。

`verify_backend.py` 可重跑真實 seed 的三次逐檔比對、密集／稀疏採樣、trace 開關、快照接續及無效輸入拒絕。首次實測相同 seed/configuration 的 35 個資料檔三次完全相同；密集／稀疏採樣也完全相同。開關 debug trace 或把 3 幀拆成 1+2 幀時，完整快照的 SCSP 音訊區有差異；其他狀態区段、高低 RAM、VRAM、CRAM、像素皆相同。報告保留完整 state 不同及差異 bytes 數；不可將其宣稱為完整模擬器跨模式一致性。正式移動對照固定 trace 設定、每次從同一 seed 開始。

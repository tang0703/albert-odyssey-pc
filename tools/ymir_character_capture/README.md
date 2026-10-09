# Ymir character capture v2

獨立的 MAP001 角色動畫證據捕捉器。沿用 Ymir v0.3.3、revision
`54fead6a0001d3e4b6741a8d095ee8342266c3dc`。不寫入遊戲 RAM，不使用桌面操作；
原 `tools/ymir_capture`、其 build／輸出及第三方 checkout 均保留不動。

## 建置與使用

```powershell
./tools/ymir_character_capture/build.ps1
./tools/ymir_character_capture/capture.ps1 `
  -Ipl 'G:/codex/SS/EMU/yabause-0.9.15-win64/Bios/SEGA101a[U].bin' `
  -Disc 'G:/codex/SS/Albert Odyssey - Legend of Eldean (USA) (RE)/Albert Odyssey - Legend of Eldean (USA) (RE).cue' `
  -LoadState reports/exploration/e1-nav-05/frame-000600/state.savestate `
  -Sequence reports/character/input.txt -Output reports/character/capture-a
```

輸入一行一個按鍵及 RunFrame 次數，例如 `none 3`。CLI 沿用 v1，支援 `--sample-every`、
`--hook-pc`、`--trace-function`、`--watch-range`。所有輸出必須使用不存在的新目錄。
建置只寫 `reports/character/ymir-character-capture-build`；證據應保留於本地 `reports/character`。
預設 wrapper 追蹤 input gate、actor loop、dispatch、velocity、動畫 timer／reader／image pointer、
collision entry 及實際 PR 返回，並觀察動畫 root `0x20220010:0x340`。

## 唯讀觀察副本

此 Ymir 版本有 public draw-finished／framebuffer-swap callbacks，沒有 command callback。
`instrument.cmake` 核對原 `vdp.cpp` SHA256 後，在新 build 生成單一 translation unit 副本，
只加入接收 const Scheduler／VDPState 的 observer 呼叫。它記錄 command fetch、實際 renderer
dispatch 前後、begin、end、swap 後狀態；不改控制流程、cycle budget 或遊戲資料。
原來源及生成副本 SHA、完整 patch 內容、v2 全部來源 SHA、舊 v1 前後 SHA 均記錄於 build manifest。
Callback 只在初始快照載入完成後啟用。所有核心與渲染工作同執行緒，RTC 與 SH-2 cache 設定沿用 v1。

## 資料介面

每筆事件、hook、frame summary 均含 `frame`、`scheduler_count`、全域遞增 `event_index`。
`frame=N` 是第 N 次 RunFrame 內／返回邊界，不代表事件在該畫面一定可见。
同 scheduler count 內以 event_index 表示觀察順序；scheduler 是 Ymir 的事件批次計時，不冒充
實體 Saturn 每一條 CPU 或 GPU 微操作的精確時刻。

`frame-NNNNNN/`：

- 保留 v1 的 `wram-high.bin`、`wram-low.bin`、`vram1.bin`、`vram2.bin`、`cram.bin`。
- `vdp1-fb0.bin`、`vdp1-fb1.bin` 各 0x40000 bytes，是同時點兩個硬體 framebuffer 的原始 bytes。
- `video-rgba.bin`／`video.ppm` 是 software renderer 的最終合成畫面；初始 frame 0 若未產生 video
  callback，沒有畫面檔，不能拿下一幀代替初始畫面。
- `sample.json` schema `ao_ymir_frame_sample_v2`；boundary 為 `initial_before_RunFrame` 或
  `after_RunFrame_return`。`vdp1` 包含 10 個 register、erase latches、display/draw bank、drawing、
  framebuffer dimensions、spillover cycles；`vdp2` 包含 142 個 named uint16 register 及 display latches。
  色盤／優先權／色彩運算所需 RAMCTL、SPCTL、CRAOFA/B、PRIS*、CC*、CLOF* 等均明列。
- 首尾保存官方完整 `state.savestate`。所有 hash 以實際 bytes 計算，不以副檔名推定內容。

`vdp-events.jsonl` schema `ao_ymir_vdp_event_v2`：

- `kind`: `command_fetch`、`command_execute_before`、`command_execute_after`、`vdp1_begin`、
  `vdp1_end`、`vdp1_swap_after_flip`、`public_vdp1_swap_before_flip`、
  `public_vdp1_draw_finished`、`public_vdp2_draw_finished`、`software_video_complete`、`sample_boundary`。
  `vdp1_end_requested` 是遊戲寫入 ENDR 後；與正常 END command 分開。
- `vdp2_render_line` 是唯一小型事件：保存 line、display/draw bank、scheduler/event 序號、
  `compose_video_serial`，觀察點在實際 RenderLine 呼叫前。固定單執行緒 renderer 的 sprite 層
  使用同一 `m_state.displayFB`。需逐行核對；不能用 RunFrame 返回後的 bank 猜測剛輸出的畫面。
- command 事件含 `command_address`（VDP1 VRAM 相對 byte offset；硬體位址加 `0x25C00000`）、
  `command_hex`（當時實讀 32 bytes）、`end`、`skip`、`valid_opcode`。
  fetch 可包含 skip／END／非法命令；只有 execute_before/after 證明進入 renderer dispatch。
- Ymir 會對非法 opcode 不斷重讀同一 command。相鄰相同非法 fetch 以 `command_fetch_repeat`
  記錄，指向首筆完整事件 `repeats_event_index`，保存同一完整 32 bytes、bank、`repeat_count`、
  `event_index..event_index_last` 與 `scheduler_count..scheduler_count_last`。不保存區間內每次無效
  fetch 的個別 PC／actor／時點；所有真正 renderer dispatch 仍逐筆完整記錄。
  任何 hook、其他事件、換幀、bank 或命令 bytes 變更都終止此 run。repeat 範圍不得跨越其他事件。
  全域 event_count／fetched_commands 包含全部壓縮前 fetch；不可用 JSONL 行數取代事件計數。
- `command_execute_before.texture` 為當時 CMDSRCA／CMDSIZE／color mode 所指定的 packed span，
  含 `vram_address,bytes,width,height,color_mode,sha256`。支援 raw span 擷取模式 0..5，
  不宣稱已解碼／可見；模式 6/7 沒有推測 span。VRAM span 按 0x80000 環繞。
- `cram_sha256` 每事件都指向當時完整 4096-byte CRAM；texture、LUT、Gouraud 和 CRAM
  全部存於 `blobs/<sha256>.bin`，內容去重，防止拿幀末資料冒充命令執行時資料。
- `vdp2_registers_be_hex` 是 register address 0x000..0x1FE 的 256 個 big-endian words，
  使用 `Read<true>`，沒有 register read 副作用。named sample register 是同 boundary 的補充。
- 除小型 render-line 事件之外，所有事件含 display/draw bank、EDSR/COPR/LOPR、current/next command、PC、VCNT/HCNT、phase、
  slot 選中 actor 的原始 112 bytes。`player_actor_address` 只標示受控物件，不斷言角色名稱。
- 非 command 事件保存兩個 framebuffer 的 SHA；software_video_complete 另保存合成畫面 SHA。
  public swap callback 發生於 bank bit 翻轉前；`vdp1_swap_after_flip` 是翻轉後。

`hooks.jsonl` 保留 v1 欄位，watch 加 SHA256，另加同步 scheduler/event 標記。
`frames.jsonl` 保留逐 RunFrame 摘要。`capture.json` schema `ao_ymir_character_capture_v2`。
`manifest.json` schema `ao_ymir_character_capture_manifest_v2`；完整釘選來源（含 CUE 每軌）、
build、執行時工作目錄、絕對路徑參數及所有輸出 SHA；wrapper 再次核對輸入未變。

## 驗證界線

命令實際執行不等於其像素可見：仍需核對 clipping、色碼透明、priority、遮擋及 buffer 顯示時序。
52 張高清稿是後續製作配額，不是已證明的原作 PNG 數量；A3 審閱前不製作整組高清動畫。
同一 seed／trace 組態的 v2 重播必須逐檔相同。與 v1 比較原有 RAM／VDP／pixel payload；
如完整 state 有差異，須分類並保留證據，不能靜默忽略 SCSP 或其他欄位。

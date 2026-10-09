# MAP001 探索 E1：同步捕捉與重播基準

日期：2026-10-09。此文件記錄本輪新建基準，不取代舊 `savestate-lock.json`。

**E1 已通過：完整導航鏈已由最終捕捉器重新建立，正式室內起點與四組各三次同步重播已核對來源，並確認控制入口更新節拍。** 此結論只涵蓋來源、採樣與重播；碰撞模型、玩家身份、涵蓋範圍、Godot 行走及 Windows 交付須由 E2–E5 分別驗收。

## 1. 固定來源及新的起點

版本化入口為 [exploration-reference-lock.json](../exploration-reference-lock.json)，`reference_id=map001-freewalk-20261009`。該清單固定新 seed、完整來源／建置清單、五段導航及十二份正式 capture manifest 的路徑與 SHA256；只把清單加入 Git，資料本體留在本地。舊 `savestate-lock.json` 不變。

正式起點為 `reports/exploration/e1-nav-05/frame-000600/state.savestate`，5,782,514 bytes，SHA256：

`72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54`

該快照的官方 v13 system 區段為 NTSC、320 時脈模式，VDP2 `TVMD=0x8000`，實際渲染 320×224、非交錯掃描。原作室內畫面保存在 `reports/exploration/nav-05.png`；原始畫素來自該段末幀的軟體渲染回呼，不是桌面擷取。固定鏡頭為 `(544, 1536)`。`e1-scene-final/scene-validation.json` 已將兩個背景圖層及完整 65,536-byte 場景旗標表重新對照來源；它不驗證人物、前景效果或碰撞。

來源清單為 `reports/exploration/sources-20261009.json`，SHA256：

`4a1c95c875f5b86553dd7b83b69d333ac6f1acec7366b5b2681b5bbd694982d2`

該清單包含原始 CUE、22 個 track、BIOS、SDL Ymir、獨立 profile 設定、捕捉器與建置清單。主要識別值：

| 項目 | 固定識別 |
|---|---|
| 原始 CUE SHA256 | `b04a42abde684fd98a5e9b1d7469ed8f277a5cb670064472982ea014193ea56e` |
| BIOS SHA256 | `96e106f740ab448cf89f0dd49dfbac7fe5391cb6bd6e14ad5e3061c13330266f` |
| SDL Ymir 0.3.3 SHA256 | `3cd7a5805403f04c1ec1f6e2904184537ca408b634cb3a82f591caf985919949` |
| 最終捕捉器 SHA256 | `a567a976d9162318346fc2308a31d3a115673757d9a37fee619c7dd239741e0c` |
| Ymir 原始碼 commit | `54fead6a0001d3e4b6741a8d095ee8342266c3dc` |
| cereal commit | `ebef1e929807629befafbb2918ea1a08c7194554` |

核心載入時另以 Ymir 的 XXH128 驗證實際 BIOS `D49063DD5320C8C7B1989060784CECB8` 與光碟 `D8562E1863DD5A2595CBE2D3A50EDFA4`；沒有略過官方 `LoadState` 相容性檢查。SHA256 與 XXH128 各司其職，不能互換。

## 2. 從冷開機到室內 seed 的來源鏈

建立了獨立 `reports/exploration/ymir-profile`，沒有覆寫舊 dialogue-trace profile 或舊鎖定清單。SDL 階段完成 BIOS 初始化、啟動原作並在燃燒村落開場暫停封存；後續導航全部由核心捕捉器載入前段末快照並精確計數 `RunFrame`。

| 階段 | 按鍵／幀數 | 末快照 SHA256 |
|---|---|---|
| 開場封存 | GUI 暫停快照，沒有可靠的絕對幀序號 | `a58db1319a17601bb0b70cae2725c99f9e19d4524621c0a4b1b786c5c86731a9` |
| e1-nav-01 | `none 1200` | `09b9fe42df0d34dda8c2eb0d296b511b1298983d08ddc0ca21fbd48ed34bc771` |
| e1-nav-02 | `none 6000` | `a4ae6d25b8a7fb25070cd53324657855bd19ffb35396d09c19f0660b09fd5cd9` |
| e1-nav-03 | `none 6000`，到室內床邊對話 | `56770a037c7afb00ef221f4d33c547f53404c8b1865bdd7c35f44c4e62ecdad7` |
| e1-nav-04 | `c 3`、`none 180`，重複四次，共 732 幀 | `5a5213befcad867590fbc2cc2841ce0b692400e5d95ead17d165f0ed65613656` |
| e1-nav-05 | `none 600`，形成正式起點 | `72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54` |

每段輸入快照 SHA256 已與前段輸出核對。新增 release 組直接使用正式 e1-nav-05 路徑；其餘三組使用相同位元組的舊命名。完整來源鏈、各 manifest 雜湊及工具版本保存在 `reports/exploration/backend-frequency.json` 的 `navigation_lineage`。

正式 `e1-nav-01`–`e1-nav-05` 全部由最終捕捉器 `a567a976…` 重新執行，具有完整工作目錄、來源及輸出雜湊。早期 `nav-01`–`nav-03` 使用首版 `464ca053…`，缺少新版欄位；`nav-04`–`nav-05` 已使用最終工具。這些歷史檔案保留原狀，不修改 manifest 以補造驗收。

最終 `e1-nav-05` 與早期 `nav-05` seed 的 5,782,514 bytes 完全一致，SHA256 均為 `72d9fa56…`。因此正式 cardinal／corners／open 三組重播雖記錄舊路徑，實際輸入與新 canonical seed 是相同狀態；三組都使用最終捕捉器。`tools/exploration_reference.py` 已逐一驗證來源、五段新導航的接續及十二份正式 capture，結果為 `reports/exploration/reference-validation.json` 的 `source_integrity=passed`、`synchronized_sampling_passed=true`。

SDL profile 的 RTC 是 Host、VDP 渲染分執行緒、導航 CD 速度係數為 200。同步捕捉器使用 Virtual RTC、沿用快照時間、關閉額外渲染執行緒，核心 CD 速度預設為 2。這些設定差異已記錄；GUI 操作與開場封存只用來建立 seed，**沒有把人工按鍵時長、F2／F12 順序或 GUI 截圖宣稱為逐幀同步證據**。開場封存自己的 `e1_passed=false` 仍然保留；後來的同步核心採樣與重播是新增的獨立證據。

## 3. 同步邊界及函式觀測

捕捉器由官方 `ymir::Saturn` 核心運行。CPU、VDP1、VDP2、SCSP 在同一執行緒完成每次 `RunFrame`；要求恰有一次軟體畫面完成回呼，返回後才擷取 RAM、VDP、暫存器與快照。沒有以睡眠毫秒數推斷已經跑過幾幀。

- `frame=0` 表示載入完畢、尚未呼叫 `RunFrame`，標記為 `initial_before_RunFrame`。不借用下一幀畫面充當初始截圖。
- `frame>=1` 的 RAM／sample／PPM 在該次 `RunFrame` 返回後記錄；核心在 VDP2 blanking/sync 邊界返回。畫面屬於剛完成的幀，並非宣稱每個像素與所有 CPU 指令在同一瞬間發生。
- 每筆 entry／return／指定 PC hook 在執行該指令之前記錄，包含執行幀、PR、R0–R15、入口 R4 所指物件的 0x70 bytes 及指定 watch ranges。
- 函式入口 `0x060AB61A` 保存 PR；到達該 PR 且不在 delay slot 時才記錄 return。相同 `function_call_index` 配對兩端，避免把猜測的 RTS 附近地址當作完成。
- `flags_sha256` 在每一筆 hook 及每個 sample 的當下對 `WRAMLow[0x10000:0x20000]` 計算。分析器可拒絕函式內或採樣間旗標表改變的證據。
- 幀序號和函式呼叫序號均相對於該次執行；`function_call_index` 不是未經驗證的全球玩家更新計數。PC hook 的 R4 也不能自動視為玩家。

`capture.ps1` 在執行前後核對輸入 SHA256，保存工作目錄、完整參數、build 清單和每個輸出的 SHA256；輸出資料夾必須不存在。整體 manifest 的完整性不能單獨證明執行同步，因此驗收同時使用已核對核心程式、同步回呼條件及三重重播。

## 4. 原作參照的實際更新節拍

**此固定場景／工具組態的邏輯步長為 `176473 / 10546875` 秒，約 16.7322548148 ms；頻率約 59.7648082143 Hz。** 這是 Ymir 實際被採樣的模型時脈，不是實體 Saturn 振盪器測量。不能直接採用 60 Hz，也不能拿 GUI 的名義 `kNTSCFrameRate=59.9400599401 Hz` 代替。

推導與實測互相核對：

1. 快照 system 區段確認 NTSC、`ClockSpeed::_320`；時脈為 `39375000 × 8 × 15 / (11 × 16) = 295312500 / 11 Hz`。
2. `TVMD=0x8000` 對應 320 像素、224 可見行、非交錯。固定來源 `vdp.cpp` 的水平 phase 為 `320 + 54 + 26 + 27 = 427` dots，dot multiplier 為 4，每行 1708 主時脈週期。
3. 非交錯 NTSC timing table 在 263 行後回到下一幀，因此 `RunFrame` 完整週期為 `1708 × 263 = 449204` scheduler cycles。
4. `449204 ÷ (295312500 / 11) = 176473 / 10546875` 秒。e1-nav-01–03、cardinal 三次、corners 三次及 open 三次的保存端點 scheduler 差分符合該週期，端點容許最多 1 cycle 的指令越界。e1-nav-04 總段多 1 cycle、e1-nav-05 少 1 cycle，與 CPU 指令越過排程邊界的端點差異相容，沒有整幀缺漏。
5. cardinal 每次 240 幀、corners 每次 170 幀、open 每次 118 幀，九次 trace 的控制入口 `0x06094AFC` 及物件調度入口 `0x060AA0DE` 均在每個幀序號恰出現一次。觀測到的碰撞函式也每幀一次；這不外推成「所有場景、所有物件永遠每幀一次」。

數值、公式、保存端點、逐幀呼叫數分布及固定原始碼檔案 SHA256 均在 `backend-frequency.json`；主要程式參照為：

- [clocks.hpp](https://github.com/ymir-emu/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/include/ymir/sys/clocks.hpp#L89)：NTSC 320 時脈比例。
- [vdp.cpp](https://github.com/ymir-emu/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/src/ymir/hw/vdp/vdp.cpp#L591)：水平／垂直 timing tables 與 dot multiplier。
- [saturn.cpp](https://github.com/ymir-emu/Ymir/blob/54fead6a0001d3e4b6741a8d095ee8342266c3dc/libs/ymir-core/src/ymir/sys/saturn.cpp#L502)：`RunFrameImpl` 返回邊界及排程推進。

Godot 建議以此有理數步長累積獨立邏輯 tick，渲染仍可為 30／60／120 FPS。不可直接把 `_process`、動畫影格或固定 60 次物理更新當成原作一次移動更新。任意中途快照的第一次 `RunFrame` 可能不足整幀；本正式 seed 已在完整幀返回邊界。

## 5. 重播結果、剩餘限制及關卡判定

| 證據 | 結果 | 能支持的結論 |
|---|---|---|
| `reference-validation.json` | 完整來源、五段新導航接續及十二份正式 capture 通過 | 新基準來源鏈與同步重播完整性 |
| `backend-validation-final/result.json` | 9 項後端檢查通過；相同 seed／設定三次 35 個資料檔完全相同 | 捕捉器基礎同步、重播、稀疏採樣及非法輸入拒絕 |
| `cardinal-replay.json` | 三次 × 240 幀、各 240 函式呼叫；輸出零差異；timing 通過 | 正式 seed 的一組完整輸入序列可重播 |
| `corners-replay.json` | 三次 × 170 幀、各 170 函式呼叫；輸出零差異；timing 通過 | 第二組完整輸入序列可重播 |
| `open-replay.json` | 三次 × 118 幀、各 118 函式呼叫；輸出零差異；timing 通過 | 第三組完整輸入序列可重播 |
| `release-replay.json` | 三次 × 32 幀、各 32 函式呼叫；輸出零差異；timing 通過 | 滑移產生後放開按鍵的完整序列可重播 |
| `e1-scene-final/scene-validation.json` | 兩個背景圖層來源匹配；旗標表 65,536 bytes 一致 | 指定場景資料有來源依據 |
| `backend-frequency.json` | 時脈公式、scheduler 差分、控制與調度入口每幀一次一致 | 本場景的模擬邏輯步長已確認 |

四份正式 replay 報告的 `movement_model_evidence_passed=false` 是刻意區分驗證責任：它們驗完整性及重播，沒有驗證碰撞模型，不能拿 E1 的結果宣稱 E2 通過。

已知 SCSP 差異：在 3 個 neutral frame 的後端診斷中，開關 debug trace 的完整快照有 62 bytes 差異；把 3 幀拆成 1+2 並重載快照有 61 bytes 差異。所有差異都位於有標籤的 SCSP 音訊區段；兩個 SH-2、SCU、SMPC、VDP、CD、RAM 與渲染像素相同。完整 state 的 `complete_state_equal=false` 仍保留在報告，首輪嚴格失敗也保留於 `backend-validation-initial/result.json`。這不保證更長時間的跨模式音訊／狀態一致性；正式三重重播要求同一 seed、同一 trace 組態及所有輸出完全相同。

舊 `savestate-lock.json` 仍鎖定 `615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab`。使用者已確認沒有備份；9 項需要舊 fixture 的回歸仍屬來源缺失，不能用本輪新 seed 改雜湊替換、靜默略過或宣稱復原。本輪另建來源鎖及證據鏈。

**綜合 E1 通過依據**是可追溯來源＋同步核心採樣＋固定室內 seed＋四組各三次完全一致重播＋已確認節拍。人工 GUI 起始段、單一檔案雜湊、背景匹配或 SCSP 範圍外一致性，任何一項都不能單獨滿足 E1，更不代表 E2、原作 Stage B 或可玩 Windows 交付已完成。

所有 BIOS、光碟、RAM、原作圖像及快照留在本地 `reports`／來源目錄。此文件與工具可加入 Git，含來源素材的資料包不可隨之推送。

重跑 E1 整合驗證：`python tools/exploration_reference.py --out reports/exploration/reference-validation.json`。該工具核對版本化鎖、來源、背景輸出、完整導航與四組三重重播；只有全數通過才回報 `e1_passed=true`。

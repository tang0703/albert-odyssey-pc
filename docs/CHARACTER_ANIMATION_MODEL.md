# MAP001 受控角色：原作動畫狀態模型

本模型固定玩家物件 `0x060C8758`、動畫 root `0x20220010`，還原四方向站立／行走的原始動畫選擇、游標、計時、圖像索引及鏡射旗標。不依物件地址推定角色姓名，也不把動畫索引直接當作圖片資產 ID。

既有 v1 四條路線各三次，共 **1,680 次原作更新，Python 與 Godot 連續模型零差異**；新 v2 十二次採樣加長四方向路線，共 **2,052 次更新也全數一致**。模型每條序列只從初始快照讀取一次狀態；後續只接收已對齊的遊戲輸入字，並由既有移動核心產生位置與接觸結果。觀測到的 actor 僅作期望值，不注入模型。

## 原始欄位

word 為 big-endian 16-bit，pointer 為 big-endian 32-bit。所有列出的欄位均以完整遮罩比較。

|actor 偏移|模型欄位|已確認用途|
|---|---|---|
|`+06`|`status_word`|移動狀態與原作動畫旗標；步進可 OR `0x80`，循環可 OR `0x100`|
|`+14`|`render_flags_word`|bit 0 依動畫紀錄的 flags bit `0x04` 設定；其他位元保留|
|`+26`|`heading`|0 右、2 下、4 左、6 上|
|`+2C`|`animation_cursor`|紀錄內 byte offset，行走正常值為 0／3／6／9|
|`+30`|`animation_timer`|當前時間計數器|
|`+32`|`animation_duration`|前一次解碼留下的 duration cache|
|`+34`|`image_index`|動畫紀錄選出的 image index|
|`+36`|`animation_index`|動畫指標表索引|
|`+58`|`image_table_root`|本角色固定為 `0x20220158` 的 image pointer table|
|`+5C`|`image_pointer`|`image_table_root[image_index]` 的讀取結果|
|`+60`|`animation_root`|本角色固定為 `0x20220010`|

另外一併比較既有移動核心的 17 欄；去除重複後共 25 個狀態欄位。`+06` 的 `0x80`／`0x100` 在此起始狀態已設定，不能把它們當作已實測的單幀 pulse 或自行每幀清除。

## 真正的執行順序

`0x060AAE20` 先選擇動畫，再依序呼叫：

1. `0x060AC0B6`：增加 timer，依**舊的 duration cache** 決定是否推進 cursor。
2. `0x060AC20C`：讀取新 cursor 的 duration、image index、record flags；遇到 duration 0 循環至 cursor 0。
3. `0x060AC34A`：由 image pointer table 查出 `+5C`。
4. 碰撞與 caller 後續處理。

有方向輸入時，speed 例程選取 `animation_index = 8 + heading`。中立輸入則由 caller 設定 `cursor = 0`、`animation_index = heading`，**沒有把 timer 歸零**。

timer 每更新先加 1。若達到舊 duration，timer 清零、cursor 前進 3 bytes。鎖定的站立／行走紀錄只有 flags 0 或 4，沒有 `0x80` 附加位移紀錄。來源程式雖有 5-byte 位移紀錄路徑，本模型遇到不同來源或未支援效果會拒絕，沒有靜默略過。

這個順序造成三個必須保留的行為：

- **起步常先顯示第二個 pose。** 穩定站立時 cursor=0、timer=0、duration=1；切換行走後先依舊 duration 判斷，timer 立即歸零，cursor 從 0 進到 3。既有路線共 13 個 unique 起步，13 個皆從第二 pose 開始。
- **行走中轉向保留 phase。** cursor、timer 不因方向不同歸零。例如 corners 第 25 更新，向下改向左，cursor 仍為 6，timer 由 7 變為 8。若轉向恰好碰到到期時間，仍正常推進一格。
- **停止時仍可能保留非零 timer。** 例如 corners 第 70 更新，timer 由 2 變為 3；cursor=0、新 duration=1。下一更新才依 duration=1 清 timer。不能要求每個輸出狀態都符合 `timer < duration`。

碰牆也不會自動停止動畫：有方向輸入但碰撞修正使位置不動時，原作仍保持 moving 狀態與行走計時。

## 圖像索引與鏡射

四方向使用的來源紀錄如下。表列為原始順序，穩定站立後起步先進入第二個值。

|方向|站立 animation/image|行走 animation|四個行走 image index|record 鏡射 bit|
|---|---|---:|---|---:|
|右|0／1|8|9、10、11、12|1|
|下|2／0|10|5、6、7、8|0|
|左|4／1|12|9、10、11、12|0|
|上|6／2|14|13、14、15、16|0|

左右方向的 animation index 不同，卻會選到相同的 image index 與 image pointer；鏡射由 `+14` bit 0 區別。圖像指標表共 40 個 entries，模型只使用原作動畫實際選中的 index，不以地址等差關係替代查表。

本文件的狀態核對不代表已證明最後 VDP1 command 的顯示內容、部件位置、透明色、反射／陰影或畫面遮擋。這些必須由新的同步顯示證據與圖像解碼驗證另外綁定。

## 來源鎖定

|來源範圍|SHA256|
|---|---|
|TWN.BIN|`fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6`|
|animation bank `20220010..20220157`|`ed78a1ab97ce9f799c3ae52c1b87920027b6ae15f893d26ec65511c534858d46`|
|image pointer table `20220158..202201F7`|`308a402aaa5b8c848569c7c29010a2790f7230be16c7f64f3bc21c36eafd12f0`|
|既有 16 組 active animation 指標／紀錄摘要|`e316125b1d085bdf18b62401bcf5b8fcb976f79827d2176a98c284ba30f9e99a`|

模型另核對 timer、record reader、image pointer reader、caller 和 idle selection table 的程式範圍雜湊，以及 RAM 中相同程式碼。完整原始資料留在本地，不把反組譯全文、RAM 或原作圖像加入 Git。

## 工具與結果

- `tools/character_animation.py`：`profile_from_snapshot()`、`state_from_actor()`、`step_game_input()`、`step()`。每步回傳完整新狀態及 timer／decode／image pointer／collision 前的 checkpoint。
- `tools/validate_character_animation.py`：依 capture manifest 版本選用對應 integrity verifier，再比較連續模型。支援 `validate_evidence()`，但傳入證據必須先由版本化 capture verifier 接受。
- `tests/test_character_animation.py`：12 項測試，涵蓋 40-tick 週期、起步、停走、轉向、source／root／cache 拒絕、boundary 整步保留、重新初始化，以及 v2 缺少 bank watch／必要動畫 hook 的拒絕。
- `exploration-demo/character_animation_core.gd`：純 `RefCounted` 動畫核心，只管理 12 個動畫／共用欄位；接收既有 movement core 的結果，不自行計算移動、碰撞、畫面時間或圖片解碼。
- `exploration-demo/tests/test_character_animation.gd`：以相同 1,680 次原作更新驅動兩個 Godot 核心，55,484 項檢查通過，含來源與狀態故障拒絕。報告位於 `reports/character/godot-animation-validation.json`。未提供本地來源參數時只能執行防護檢查，會明列 `source_comparison_status=not_run`。

既有 v1 十二次驗證結果位於本地 `reports/exploration/character-animation-validation.json`；fixtures 與測試紀錄同目錄。除了更新後結果，還比較 dispatch、velocity entry、record reader 入口、collision 入口，以及可用的 frame 末快照。

故障測試刻意修改第 1 更新的觀測 timer，只有第 1 更新被判定不符；後續預測不受它影響，檢查模型沒有以原作後續狀態重設自己。

v1 僅有起始／末尾 source bank 快照，沒有每個 hook 的 bank watch，因此報告保留 `source_bank_each_hook_verified=false`。v2 新增相關 hooks、共同 scheduler 時序、bank watch 與逐幀 RAM；其結果必須另外實跑，不能由 v1 成績代替。

正式 v2 結果位於 `reports/character/animation-validation.json`：四方向 364、轉角 170、空地 118、放開 32 更新，各三次；共 2,052 次更新、每個採樣 hook 的 bank watch 與所有 frame 末快照均通過。Godot 同組驗證位於 `godot-animation-v2-validation.json`，67,760 項檢查通過。v2 必須有 timer、record reader、image pointer reader hooks 及每 hook 的 source bank watch，缺少任何一項會拒絕。這些是角色狀態證據；VDP1 執行、VDP2 合成與可見像素仍由獨立圖形驗證報告負責。

Godot 整合時，先用 Python profile metadata、328-byte animation bank 與 160-byte image pointer table 呼叫 `configure()`；程式會核對固定 source／code pins 與原始內容雜湊。每個邏輯 tick 先以自己的前一狀態執行既有 `movement_core.step_game_input()`，再把回傳值交給 `character_animation_core.step_after_movement()`。成功才同時接受兩個新狀態；測試邊界保留全部舊狀態。`initial_state()` 用於重設，`image_index`、`image_pointer`、`render_flags_word & 1` 供後續演出層使用。完整圖片載入、可見 draw command 與高清映射須另行驗證。

## 高清演出邊界

原作每個步行 pose 為 10 個邏輯 ticks，一輪四個 pose 共 40 ticks。後續每個原 pose 的三張高清演出畫面，只能等分其 10 ticks 的呈現時間，不增加原始 pose 數、不修改 timer／cursor、不把一輪延長為 120 ticks。起步與轉向必須沿用此模型的原作 phase。

高清 52 張素材、插值、圖像替換與 Godot 顯示層不在本 Python 原作狀態模型內。此階段不改既有 movement core、來源 locks、地圖規則或角色名稱。

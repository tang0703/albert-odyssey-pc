# MAP001 指定區域移動核心與本地資料包

本輪使用 MAP001 的固定室內畫面，以診斷標記顯示玩家位置、朝向及碰撞矩形。原作輸入、速度表、形狀及位置修正經同步捕捉核對，再移植成不依賴畫面或牆鐘時間的移動核心。這份文件記錄來源與模型證據；Windows 畫面、操作及效能驗收由交付報告另外記錄。

## 來源與可重跑基準

基準識別為 `map001-freewalk-20261009`，`exploration-reference-lock.json` 鎖定五段導航、具名初始快照、場景來源核對和四組各三次的重播。舊 `savestate-lock.json` 保持原狀，缺失的歷史快照沒有以新雜湊替代。

|來源|SHA256|
|---|---|
|MAP001.TWN|`8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9`|
|TWN.BIN|`fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6`|
|核心程式 0|`95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff`|
|具名初始快照|`72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54`|
|展開後旗標表|`78863dedbf02a07158821486a059af56f31a0b18d11a9eee6a7986dd10943e5b`|
|玩家動畫表與紀錄|`e316125b1d085bdf18b62401bcf5b8fcb976f79827d2176a98c284ba30f9e99a`|

原作圖像、RAM、BIOS、光碟與快照不納入 Git。`reports/exploration/` 保留本地同步證據與詳細分析。檔案存在、靜態程式比對或來源雜湊通過，都不能單獨代替原作動態驗證。

## 已確認的更新流程

`06094AFC` 依 `060C27AE=0` 選取 `060C8758` 的 112-byte actor。捕捉中每幀恰一次 input gate、actor loop、正常 dispatch、animation 及 collision；有方向輸入時再經速度例程。碰撞返回使用函式入口 PR 配對真正返回 caller 的時點。

位置為原始 16-bit word，每像素 16 個單位。形狀 ID 1 的五個 signed words 是 `[-192,-96,64,384,192]`；本碰撞例程使用左、上、寬、高，對應位置中心周圍 `[-12,-6,24,12]` 像素的地面矩形。第三個 word 的用途仍未知，沒有當作角色高度或圖像腳底錨點。

本控制 gate 由原作寫入 speed index 3，四方向移動表為每更新 32 個原始單位，即 2 像素。觀察到的原作節拍為 `176473 / 10546875` 秒，約 **59.7648082143 Hz**。渲染頻率與此邏輯節拍分離。模擬器按鍵注入到遊戲輸入字有兩幀傳輸延遲；PC 核心直接接收對齊後的 `game_pad_word`，不另外加入這段延遲。

更新依序處理：

1. 輸入清理、朝向及移動旗標。
2. 速度表與待機／行走動畫選擇。
3. 消費前次排入的 slide，清空 queue。
4. 先修正 X，再用已修正的 X 處理 Y。
5. 中心旗標、selector、mode；本次新排入的 slide 留到下一更新。

鎖定的玩家動畫紀錄沒有位置附加量，因此診斷標記核心可省略圖像動畫計數器。不同動畫 root、來源雜湊、玩家形狀、控制 gate 或 dispatch mode 都拒絕啟動。`0x20` 沒有被當作通用障礙；本 selector 的阻擋遮罩依原作例程選定。

## 動態覆蓋與比較

四條路線各重播三次，共 **1,680 次更新、零差異**。Python 從初始狀態連續推演，每次只接受原作遊戲輸入字，不注入後續 actor 狀態。比較 17 個已確認欄位的完整 word／byte 遮罩：X/Y、status、flags、selector、mode、dx/dy、slide X/Y、speed、heading、shape、animation index、free direction、center flag、contact bits。

下一輪 dispatch、末尾 RAM 快照及舊 X/Y 全域寫入也逐次核對，檢查 collision caller 尾部是否另外改動這些欄位。模型不宣稱還原所有 112 bytes，也不包含圖像繪製。

|路線|每次更新數|實際覆蓋|
|---|---:|---|
|cardinal|240|四側接觸與持續壓牆；左／右／上／下接觸 39／36／30／50 次；17 次跨格；4 次放開|
|corners|170|4 次排入並消費垂直 slide；20 次跨格；3 次直接轉向；家具轉角|
|open|118|全部沒有接觸；上／右各 8 次、下 39 次、左 27 次空地移動；20 次跨格|
|release|32|第 26 更新排入 slide_y=32；第 27 更新輸入中立仍移動並清空 queue；第 28 更新停止|

通過路線的形狀邊緣與中心查表聯集為 **108 格**。這不是把座標外框填成矩形。若試算下一整步時任何查表 index 超出此聯集，核心回傳 `test_boundary` 並保留原狀態，包括 contact bits；介面顯示「測試邊界」，不冒充原作牆壁。

## 核心與資料介面

- `tools/exploration_movement.py`：`step_game_input(state, game_pad_word, profile)` 回傳 `(new_state, diagnostics)`；`step(state, direction, profile)` 提供單方向名稱介面。
- `tools/validate_player_trace.py`：先驗證同步捕捉的來源與時點，再執行完整更新對照。
- `tools/exploration_bundle.py`：建立與獨立驗證本地資料包。

正式資料包只包含六個直接檔案：

|檔案|用途|
|---|---|
|`package.json`|來源識別、固定鏡頭、viewport、payload 大小與 SHA256|
|`nbg0.png`、`nbg1.png`|來源比對通過的 320×224 RGBA 背景|
|`flags.bin`|65,536-byte 旗標表|
|`profile.json`|原始起點、形狀、邏輯節拍、欄位約定及 108 格範圍|
|`traces.json`|四條 unique 軌跡的輸入與期望狀態，共 560 更新|

建置輸出預設為 `exploration-demo/generated/scene/`。父資料夾的 `.gdignore` 阻止 Godot 產生 `.import` 旁檔；`.gdignore` 不在六檔資料包內。另產生 `exploration-demo/bundle-pin.json`，由應用程式匯入 PCK，保存受信任的 `package.json` 雜湊。Windows 匯出時，六檔資料包由封裝流程放在執行檔旁 `scene/`。

`build` 會重跑完整參照來源驗證與四組十二條動態 trace，全數通過才寫入輸出。已有輸出時，先依原 pin 完整驗證；只覆寫核准六檔，遇到未知檔案拒絕繼續，保留該檔案。Pin 必須放在資料包外。

`verify` 不需要光碟、BIOS、RAM 或原始快照，但必須使用外部受信任 pin。它核對精確檔案清單、雜湊、大小、來源紀錄、profile、PNG 尺寸及全部 560 次移動；profile 範圍必須精確等於 trace 的查表聯集。不能直接把待驗證 manifest 自己的雜湊當作信任來源。

在 `pc-remake` 目錄執行：

```powershell
& ..\tools\pc-remake\python\Scripts\python.exe tools/exploration_bundle.py build
$scenePin = Get-Content exploration-demo/bundle-pin.json -Raw | ConvertFrom-Json
& ..\tools\pc-remake\python\Scripts\python.exe tools/exploration_bundle.py verify `
  exploration-demo/generated/scene --manifest-sha256 $scenePin.manifest_sha256
& ..\tools\pc-remake\python\Scripts\python.exe -m unittest discover -s tests -p test_exploration_bundle.py -v
```

13 項合成資料包測試涵蓋缺檔、未知檔、截斷、SHA 錯誤、manifest 改寫、未知 profile／shape、domain 擴大、路徑逃逸、錯誤 PNG、trace 缺失／分歧、來源程式變更、JSON 重複 key，以及錯放 pin；這些測試不內嵌原作圖像或 RAM。原作來源建置與動態對照另外實跑。

## 驗證界線

本核心限指定場景、受控角色、動畫來源與已採樣區域。完整地圖、鏡頭捲動、NPC／其他 actor 碰撞、事件、角色動畫、原作戰鬥及其他形狀尚不在此驗收內。Stage B 不因此整體通過。含原作背景的本地資料包及 Windows ZIP 留在本機，不納入 Git 或公開套件。

# A2：MAP001 原作角色動畫與遮擋整合驗收

日期：2026-10-09。A1 提交為 `f00877c`；A2 提交由主線審閱本文件後建立，本文件不預填提交雜湊。

**A2 指定範圍通過。** 已在獨立角色入口接入原作四方向待機／行走、六件靜態場景物件、來源支持的排序與 NBG 前景優先權。這是原作像素版的整合基準；受控物件仍稱「MAP001 玩家」，沒有藉物件位址推定角色姓名。

A3 的四方向高清造型尚未獲得審閱核准；計畫中的 52 張高清圖尚未製作。A6 新素材效能測試及新版 Windows ZIP 交付尚未進行。完整地圖、鏡頭跟隨、其他場景、事件及原作戰鬥仍不在本關卡，Stage B 不因此整體通過。

## 本次結果與可查證紀錄

| 驗證項目 | 結果 | 本地證據 |
|---|---|---|
| 原作角色動畫連續模型 | 12 條捕捉、2,052 更新零差異；Godot 67,760 項檢查通過 | `reports/character/animation-validation.json`、`entry-animation-validation.json` |
| 家具／玩家命令順序 | 684 幀、9,594 筆 execute 回呼；玩家／物件零未綁定、零排序差異 | `reports/character/draw-order-validation.json` |
| 來源套件對原作畫面 | 680 幀、386,387 個原作玩家不透明範圍像素零差異，涵蓋四向 20 姿勢 | `reports/character/runtime-pixel-fixtures.json` 的 `cpu_validation` |
| 真正 GPU 合成 | RTX 4070 Ti SUPER、Compatibility／OpenGL 3.3；80 組、107,871 像素零差異 | `reports/character/gpu-compositor/source.json`、`source-engine.log` |
| GPU 原作子集 | 上列包含 28 個原作案例，各測 1×／2×；56 組、80,655 個指定遮罩像素零差異 | 同一 GPU 報告，排除 `synthetic_` 案例 |
| GPU 合成器合成資料 | 24 組、27,216 像素零差異；1×／2×／7×、透明洞、非零位置、前後畫序、兩種縮放方式 | 同一 GPU 報告，`synthetic_` 案例 |
| 角色 UI 整合 | 12,371 項檢查、4,104 次更新通過；原作像素／診斷標記兩模式各跑同一組 2,052 更新 | `reports/character/entry-test_character_ui.log` |
| 角色包來源 loader | 55 項檢查通過，`source_package_status=passed` | `reports/character/entry-loader-validation.json` |
| 角色包故障測試 | 11 項通過 | `reports/character/entry-test_character_bundle.log` |
| 原移動回歸 | Python／Godot 原有 1,680 更新零差異；Godot 33,664 項檢查通過 | `reports/exploration/player-trace-suite.json`、`godot-movement-validation.json` |
| 原入口及戰鬥回歸 | 探索 Godot／封裝／QA fixture 與戰鬥核心、UI、時序、封裝檢查保持通過 | `reports/character/a2-exploration-regression.log`、`battle-regression-local.log` |
| 舊探索 PCK 內容範圍 | 12 個核准資源，無角色入口、角色素材或新增來源檔混入 | `reports/character/a2-legacy-pck-check.json` |
| 全部 Python 測試 | **291 項：282 通過、9 項既知來源錯誤；沒有新增失敗** | `reports/character/a2-python-final.log` |

來源套件比對排除每條路線第一張繼承 seed 的 video，共四張。它們沒有捕捉前的 command execution 證據；不能拿 A1 已驗證 seed bank 的結果，冒充這次套件合成器已重播捕捉前命令。680 幀與 A1／排序分析的 684 幀屬不同驗收分母。

GPU 比對的 expected PNG 直接來自封存原作 `video-rgba.bin`，按當時相機重新投影到固定鏡頭；遮罩來自獨立解碼的來源玩家不透明像素。預期值不是用被測 Godot shader 生成，也不是將比對失敗像素刪除後得到的結果。背景／家具遮擋像素仍留在此範圍內接受比較。

主要紀錄 SHA256：

- GPU 正式報告：`ab9c0f323b7e80dbe9c56da6d13391c6820142c76ae3e6eafeae33029a0418e2`。
- 原作 GPU fixture／CPU 合成報告：`19f904a26610d30b1158f3f5c28973b6b3ab28181bb88b7f189101966a4b4ad9`。
- 排序報告：`bb21c005b63d2ae2ff4909115d32ad96fafe7dbfe4d8897bedc11f6edcc0eab8`。
- 全 Python 回歸紀錄：`b57ad97fb5fa2b5b2143d50e99ba3da330d3ca0b01b66e397b84094671d1c4e5`（291 項、39.516 秒；程序 exit 1 因下列 9 項既知來源錯誤）。

## 套件與執行介面

既有場景包 `exploration-demo/generated/scene` 維持六檔：`flags.bin`、`nbg0.png`、`nbg1.png`、`package.json`、`profile.json`、`traces.json`。來源清單 SHA256 仍為 `bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc`。

新增角色包 `exploration-demo/generated/character` 是**另一個 33 檔套件**，包含 `package.json` 及 32 個 payload：四向各一待機＋四步行姿勢，共 20 張原作 PNG、六家具 PNG、來源 NBG 前景、動畫資料、圖像表、模型與外觀／圖層設定。其 `package.json` SHA256 為：

```
ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21
```

`character-pin.json` 同時釘住角色與場景包，loader 檢查完整清單、雜湊、尺寸、透明度、來源身份、鏡射、錨點、姿勢及排序設定。缺資料或未知條件會拒絕啟動／查詢，不靜默改用診斷人物。原作圖像、動畫資料、RAM、快照、完整報告與含來源套件均留在本地忽略目錄，不加入 Git。

主要程式介面：

- `character_animation_core.gd`：`configure(profile, animation_bank, image_table)`、`step_after_movement(state, movement_result)`；獨立於 Node、FPS 與真實時間。
- `character_loader.gd`：`load_verified(directory, manifest_sha256, scene_manifest_sha256)`、`lookup(bundle,state)`、`draw_order(bundle,displayed_actor,camera)`；預載原作圖片並拒絕未知映射。
- `character_main.tscn/.gd`：獨立入口，沿用既有移動／碰撞與操作；可切換原作像素與診斷標記。暫停、單步、重設、失焦和多方向輸入仍沿用原驗證台約定。
- `character_layer.gd` 與 `character_priority.gdshader`：使用 map-local 矩形和 `canvas_size` 取樣來源前景。後畫的低優先 sprite 在前景處寫入前景 RGB，仍保留 sprite alpha，因此不會漏出先畫的高優先 sprite；透明洞保留先前畫面。
- `character_draw_order.py`：重建原作家具先插入、碰撞桶往後移及命令優先序 FIFO。命令配置地址不等於實際執行順序。

每個主要步行姿勢持續 10 次邏輯更新，一輪 40 次；轉向保留相位、起步可能由第二姿勢開始，停步與碰牆行為依來源模型。原作顯示延遲以本場景已驗證的三次更新處理，不以動畫 FPS 猜測。PC 固定鏡頭為 `[544,1536]`，原作採樣中的相機捲動仍保留作來源核對；沒有縮小既有 108 格驗證域。

## 重跑方法

以下從 `G:/codex/SS/pc-remake` 執行，使用專案既有工具，不修改系統 PATH 或登錄檔。

```powershell
./tools/character.ps1 test
./tools/character.ps1 gpu-test
./tools/character.ps1 run
```

`build` 只在完整本地來源及已驗證報告存在時使用：`./tools/character.ps1 build`。舊資源驗證台、探索入口與戰鬥 demo 保留。`test` 已包含來源 loader 參數及 11 項 runtime-pixel 故障測試；`gpu-test` 另以實際 GPU 執行來源 fixture，並要求 `source_fixture_status=passed`。無畫面測試不能替代 GPU 驗收；單獨跑 loader 若未附來源參數只會執行防護檢查，`source_package_status=not_run` 不算 55 項來源驗收。

完整 loader 來源命令：

```powershell
$godot = '../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe'
$pin = Get-Content exploration-demo/character-pin.json -Raw | ConvertFrom-Json
& $godot --headless --path exploration-demo `
  --log-file G:/codex/SS/pc-remake/reports/character/loader-rerun-engine.log `
  --script res://tests/test_character_loader.gd -- `
  --bundle=G:/codex/SS/pc-remake/exploration-demo/generated/character `
  ("--manifest-sha256=" + $pin.manifest_sha256) `
  ("--scene-manifest-sha256=" + $pin.scene_manifest_sha256) `
  --report=G:/codex/SS/pc-remake/reports/character/loader-rerun.json
```

來源像素／fixture 可重新產生到**新的檔案與同名資料夾**；工具拒絕覆蓋既有 fixture 圖片資料夾：

```powershell
& ../tools/pc-remake/python/Scripts/python.exe tools/validate_character_runtime_pixels.py `
  --out G:/codex/SS/pc-remake/reports/character/runtime-pixel-fixtures-rerun.json
```

實際 GPU 命令必須省略 `--headless`。測試以 PNG 預期值與實際 GPU readback 做 exact RGBA 比對。以下保留程序環境設定並在完成後復原；可將 fixture 換成剛重建的路徑。

```powershell
$gpuReports = 'G:/codex/SS/pc-remake/reports/character/gpu-compositor'
$savedAppData = $env:APPDATA
$savedTemp = $env:TEMP
$savedTmp = $env:TMP
try {
  $env:APPDATA = "$gpuReports/appdata"
  $env:TEMP = "$gpuReports/temp"
  $env:TMP = $env:TEMP
  New-Item -ItemType Directory -Force -Path $gpuReports,$env:APPDATA,$env:TEMP | Out-Null
  & ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe `
    --path exploration-demo --rendering-method gl_compatibility `
    --log-file "$gpuReports/source-rerun-engine.log" `
    --script res://tests/test_character_compositor.gd -- `
    --fixtures=G:/codex/SS/pc-remake/reports/character/runtime-pixel-fixtures.json `
    --report=G:/codex/SS/pc-remake/reports/character/gpu-compositor/source-rerun.json
} finally {
  $env:APPDATA = $savedAppData
  $env:TEMP = $savedTemp
  $env:TMP = $savedTmp
}
```

不傳 `--fixtures` 只驗合成資料。headless 執行會明示 `SKIP_REAL_GPU_REQUIRED`，不能據其 exit 0 宣稱 GPU 驗收通過；正式報告須有 `headless=false`、實際 adapter、`passed=true` 及 `source_fixture_status=passed`。

全部 Python 測試命令為 `python -m unittest discover -s tests -p 'test_*.py' -v`；本輪使用專案 Python，程序 APPDATA、TEMP、TMP 分別位於 `reports/character/a2-python-final-appdata`、`a2-python-final-temp`。完整 stdout／stderr 保存在 `a2-python-final.log`，沒有將失敗靜默排除。

## 舊快照、視覺與交付界線

全 Python 的九項錯誤與前一份 `a2-python-regression-local.log` 名稱集合完全相同：background 2、map_graphics 1、scene_flags 1、scene_metadata 2、source_scene 1、ymir_state 2，均因舊 `0.savestate` 身份／來源雜湊不符。所需舊 SHA256 為 `615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab`。使用者已確認沒有備份；舊鎖、測試與快照雜湊均未更改，不能寫成全測試通過。

本次實際三解析度 PNG 為 `reports/character/native-1080p.png`、`native-1440p.png`、`native-4k.png`。主線已目視檢查，對應 native JSON 確認實際 viewport 為 1920×1080、2560×1440、3840×2160。它們是**截圖模式**，沒有穩定演出計時、600 秒樣本或可用 FPS／記憶體成長門檻；JSON 中的零值不能當成效能結果。

GPU 合成器驗收只覆蓋合成資料與來源玩家不透明範圍。投影／陰影像素、裝飾物 slot 6／7 的 PC 顯示與動畫、整個房間逐像素相等皆未還原。排序工具曾辨識 slot 6／7 命令的來源及優先序，並明列 slot 7 相鄰快照邊界；這不等於把其動畫加入 PC 套件。六家具加來源前景以外的場景效果不得用本報告推定完成。

舊 `MAP001-Walk` 的 12 資源 PCK 檢查只證明封裝內容範圍，未在此關卡重新聲稱 Windows 冷啟動、ZIP 解壓或新版交付通過。角色包與六檔場景包繼續分開。後續依序進入 A3 四向高清造型審閱；核准後才製作整組高清動畫並重新做三解析度、4K 長測與交付。A2 的原作像素效能或舊版數據都不能代替 A6 新素材驗收。

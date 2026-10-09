# MAP001 高清角色驗證台：Windows 交付與 A6 驗收

**目前狀態：工具契約已建立；正式高清套件、Windows 交付與 A6 效能驗收待實際素材完成後執行。** 本文件不以合成測試、A2 原作像素結果或舊版 ZIP 宣稱高清交付完成。四方向造型已核准，52 張高清姿勢正在製作。

## 交付結構與來源

預定新版 ZIP 為 `build/MAP001-Character-Windows-x64.zip`，執行檔為 `MAP001-Character.exe`。保留原有 `MAP001-Walk-Windows-x64.zip`，不覆蓋既有交付。新版 ZIP 若已存在，封裝工具拒絕覆寫，須另選新版本路徑。

Windows 套件包含獨立 EXE／PCK、操作及授權文件、BUILD-INFO 與三個外置資料包：

| 資料夾 | 契約 | 用途 |
|---|---:|---|
| `scene` | 6 檔 | 已驗證背景、碰撞、移動 profile 與路線 |
| `character` | 33 檔 | A2 原作角色、六家具、前景及動畫模型 |
| `character-hd` | 58 檔 | 52 張姿勢 PNG、四張 atlas、appearances 與 package manifest |

52 張姿勢是四方向各一待機、12 張行走。原作參照圖、imagegen 中間產物、RAM dump、完整 savestate、光碟、BIOS 及測試報告不進入交付包。批准資料包中具明確用途與固定白名單的小型動畫／旗標資料仍按各包規格保存。含原作素材的套件僅限本地，不同步 GitHub。

`audit_character_package.py` 檢查三個獨立 pin、彼此來源關係、所有外置包語意與逐檔 SHA256。PCK 僅接受已列名的 compiled scripts／remaps、角色入口、shader、三 pin 與引擎必要 metadata；不接受內嵌 generated 圖片、參照 PNG 或測試。`main.gd` 作為角色入口基底保留；舊 `main.tscn` 及美術審閱腳本 `character_art_review.gd` 明確排除。

Godot 4.7.2 實際 `project.binary` 保留 `application/run/main_scene=res://main.tscn`，執行時透過 `_custom_features=character_demo` 與 `application/run/main_scene.character_demo=res://character_main.tscn` 選取角色入口。驗證器要求這三項完全吻合，並拒絕任何額外 main_scene feature 覆寫；僅放入角色場景或單獨存在覆寫設定都不算通過。

BUILD-INFO 記錄完整 Git 提交、是否有未提交變更、Godot 版本、建置時間、三 pin SHA256 及逐檔清單。ZIP 在解壓前先驗檔名／大小／CRC／SHA256，拒絕 traversal、重複及大小寫別名、連結、額外或缺失檔案；只解壓至全新目錄，再對完整交付重新驗證。上述封裝檢查不自動給予冷啟動或效能通過。

## 後續建置入口

新增 Godot preset 1 為 `Windows Character Workbench`，feature 為 `character_demo`，preset 0 的舊探索輸出保留。主線必須先完成 A4 真實批准素材、A5 整合及相關測試，再進行匯出；不能用測試替身補齊檔案數量。

從 `G:/codex/SS/pc-remake` 執行，下列為正式素材完成後的命令契約：

```powershell
# 保留 A2 的 33 檔來源包建置入口；此命令不會批准 HD。
./tools/character.ps1 build

# 只有完整 A4 審閱通過的 52 張素材 manifest 才能建立 HD 包。
./tools/character.ps1 hd-build `
  -ArtManifest G:/codex/SS/pc-remake/reports/character/<已核准素材>/manifest.json `
  -ArtSha256 <完整64位SHA256>

./tools/character.ps1 test
./tools/character.ps1 run
./tools/character.ps1 export

# 再次交付必須使用新的 ZIP 名稱，舊檔不覆寫。
./tools/character.ps1 export `
  -ZipPath G:/codex/SS/pc-remake/build/MAP001-Character-Windows-x64-<版本>.zip
```

`build` 也接受相同兩個素材參數，依序建置來源包與 HD 包；`hd-build` 直接沿用已驗證來源包。`test`、`run`、`export` 都要求正式 HD pin 與實際 58 檔，不以測試替身補齊。`gpu-test` 仍專供 A2 原作像素合成比較，不冒稱高清效能驗收。

`export` 先重跑完整角色測試，要求來源比較及真正的 HD UI 一致性通過，再用 preset 1 匯出到新的 `build/character-staging-<UUID>`。只複製三包固定核准清單及文件，資料來源不在匯出時重新抽取。測試前後及匯出後核對來源程式、設定與三 pin SHA；Git 提交及 dirty 狀態變動也會中止封裝。`entry-export-inputs.json` 保存當次輸入雜湊，`entry-package-audit.json`、`entry-zip-audit.json` 保存實際交付結果。

套件與 ZIP 解壓驗證全部通過後，才以不覆寫的目錄重新命名方式發布暫存內容：第一次使用 `build/character-demo`；若該目錄已存在，改用 `build/character-demo-<UUID>`，舊版一律保留。中途失敗只留下本次暫存資料供診斷，不逐檔更新既有 release；發布時發現目標已出現也會拒絕，不能合併或覆寫。

封裝工具的 `build-info` 與 `zip` 都再次驗證實際 HD 包及 PCK 主入口；尚未產生／核准時應失敗。ZIP 解壓到 build 內的全新 UUID 目錄。最終交付應從解壓後的 EXE 執行 QA，而非依賴編輯器、原始來源目錄或任意工作目錄。

## 三解析度與 4K 長測

`tools/character_qa.ps1` 使用新 EXE 與 `ao_pc_character_ui_qa_v1` 引擎報告。報告必須明示 `appearance_mode=hd`，且 `hd_manifest_sha256`、`character_manifest_sha256` 與實際啟動套件一致；原作像素模式或舊探索報告不能通過高清驗收。

```powershell
./tools/character_qa.ps1 `
  -Executable G:/codex/SS/pc-remake/build/character-unzip-<唯一版本>/MAP001-Character.exe `
  -OutputRoot G:/codex/SS/pc-remake/reports/character/qa-hd-<唯一版本> `
  -WarmupSeconds 15 -SoakSeconds 600
```

預設先做 1920×1080、2560×1440、3840×2160 三張獨立截圖，再啟動新的 4K 長測程序。可用 `-SkipSoak` 做截圖，或 `-SoakOnly` 單獨執行長測；短於 600 秒的診斷不能得到完整 A6 驗收。

各程序開始與結束都核對完整交付檔案及 EXE／PCK／三 manifest；程序層 APPDATA、TEMP、TMP 位於本次 reports 內，完成後復原。舊探索與新角色 QA 共用排他鎖，另檢查是否有其他 Godot／遊戲或 Python 驗證程序；正式測量不與其他驗證並行。工具不清除作業系統檔案快取，因此冷啟動紀錄表示新程序啟動，不冒稱首次磁碟讀取。

穩定測量期間不存截圖、不做 GPU 像素 readback；尺寸逐幀檢查，實際像素只在計時前後核對。外部 Windows 程序記憶體按秒取樣，GPU Process Memory 約每十秒讀取 dedicated／shared 計數器。

通過門檻：

- 原始逐幀 interval 重新計算平均至少 59 FPS、P95 不超過 20 ms；完整測量至少 600 秒。
- 每個超過 50 ms 的影格保留時間、路線與更新位置。最大值超過 100 ms 時完整驗收暫不通過，另做可重現性與根因檢查，不刪除尖峰。
- 無來源狀態差異，完整循環至少四條路線；HD 模式及三資料包身份不得變動。
- 暖機後的獨立前後取樣窗，程序 private bytes 與 working set 中位數成長各不超過 10%；節點數穩定。
- 程序記憶體、GPU dedicated／shared 觀測必須跨越完整測量，保存峰值與間隔。release 的 Godot allocator 若全為 0，記為 unavailable；不得把它當成零使用量，外部程序記憶體仍為必要證據。

輸出包括 `report.json`、`process-memory.json`、`launch.json`、`package-before.json`、`package-after.json`、`acceptance.json`、engine log；截圖模式另存 `screen.png`。實際 screenshot、frame time、RAM／VRAM 峰值、ZIP SHA256 與最終 commit 將在真正執行後填入下表。

## 本輪交付狀態

| 項目 | 狀態 |
|---|---|
| 封裝工具合成故障測試 | 11 項通過；不含真實 HD 素材驗收 |
| QA 判定器合成故障測試 | 48 項通過，見 `reports/character/a6-qa-contract-tests.log`；不代表渲染實測 |
| build／test／export 腳本契約 | 43 checks 通過，含暫存發布、失敗保留及舊版不變；見 `reports/character/a6-entry-contract-tests.log`。程序及素材核准採測試替身，未執行真 HD 匯出 |
| 52 張 HD／四 atlas／完整包 | 待正式素材製作及驗證 |
| 原作與 HD 相同行動結果、真實流程 | 待 A5 正式整合驗收 |
| 三解析度實際 PNG | 待新 HD 素材驗收；A2 截圖不替代 |
| 4K 600 秒效能與 RAM／VRAM | 待執行 |
| Windows 匯出、ZIP 與解壓冷啟動 | 待執行 |
| 新交付 SHA256／Git 提交 | 待正式交付後記錄 |

本輪依然只包含 MAP001 已驗證室內域。影子、裝飾物 6／7、完整鏡頭及其他場景未因此還原；高清造型與過渡影格是批准的新製作素材，不冒充原作逐幀畫面。

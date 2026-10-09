# MAP001 高清角色驗證台：Windows 交付與 A6 驗收

2026-10-09。**52 幀素材、三外觀整合、三解析度畫面、解壓冷啟動及 4K 600 秒驗收通過。** 本輪完成範圍為「MAP001 指定區域玩家動畫與高清演出驗證通過」，不代表完整地圖或 Stage B 整體通過。正式包的來源提交與 ZIP 身份由 `BUILD-INFO.json`、ZIP 旁的 SHA256 及 `docs/CHARACTER_RELEASE.json` 記錄。

## 交付結構與來源

正式 ZIP 使用 `build/MAP001-Character-Windows-x64.zip`，執行檔為 `MAP001-Character.exe`。保留原有 `MAP001-Walk-Windows-x64.zip` 及本輪候選包，不覆蓋既有交付。新版 ZIP 若已存在，封裝工具拒絕覆寫，須另選新版本路徑。

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

## 建置入口

Godot preset 1 為 `Windows Character Workbench`，feature 為 `character_demo`，preset 0 的舊探索輸出保留。匯出前要求 A4 真實批准素材、A5 整合及相關測試；不能用測試替身補齊檔案數量。

從 `G:/codex/SS/pc-remake` 執行：

```powershell
# 保留 A2 的 33 檔來源包建置入口；此命令不會批准 HD。
./tools/character.ps1 build

# 只有完整 A4 審閱通過的 52 張素材 manifest 才能建立 HD 包。
./tools/character.ps1 hd-build `
  -ArtManifest G:/codex/SS/pc-remake/art/characters/map001-player/walk-v1/manifest.json `
  -ArtSha256 a782d63d90e32647f4f3d94bc33da6a0f05a5d1267d6893d3a49ce7aba96fcb2

./tools/character.ps1 test
./tools/character.ps1 run
./tools/character.ps1 export

# 再次交付必須使用新的 ZIP 名稱，舊檔不覆寫。
./tools/character.ps1 export `
  -ZipPath G:/codex/SS/pc-remake/build/MAP001-Character-Windows-x64-<版本>.zip
```

`build` 也接受相同兩個素材參數，依序建置來源包與 HD 包；`hd-build` 直接沿用已驗證來源包。`test`、`run`、`export` 都要求正式 HD pin 與實際 58 檔，不以測試替身補齊。`gpu-test` 仍專供 A2 原作像素合成比較；A5 的高清 GPU 合成另以 `tests/test_character_hd_compositor.gd` 驗證，兩者都不代替長時間效能驗收。

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

輸出包括 `report.json`、`process-memory.json`、`launch.json`、`package-before.json`、`package-after.json`、`acceptance.json`、engine log；截圖模式另存 `screen.png`。`collector-operations.json` 記錄 Process.Refresh、CIM 守衛及 GPU 計數器呼叫區間；不包含 Refresh 之後程序記憶體屬性 getter 的完整耗時。這些時序只供關聯檢查，不能直接證明尖峰原因。

## 已完成的功能與回歸

| 項目 | 狀態 |
|---|---|
| 52 張 HD／四 atlas／完整包 | 52 張 512×512 RGBA、四張 2048×2048 圖集；21 項美術工具測試及 15 項高清包測試通過 |
| 真實素材 UI 與相同行動結果 | 24,775 checks；2,052 次來源更新 × 三外觀 = 6,156 次，零差異 |
| 原作移動 | 1,680 次對照維持零差異；高清外觀不寫回核心 |
| 動畫選圖／狀態 | 48,235 checks；包含暫停、單步、轉向、切換、多方向、失焦、重設與缺圖拒絕 |
| 真實高清 GPU 合成 | 16 項比較、4,910,080 像素；72 像素最多 1/255 線性量化差，其餘相同；15,710 個前景樣本零差異 |
| 封裝故障／腳本契約 | Python 11 項、PowerShell 43 checks 通過；實際 PCK 及三來源包另經完整審核 |
| QA 判定器與取樣故障 | 53 checks 通過；這些是判定器測試，不代表渲染效能 |
| 環境負載分類 | 11 項離線測試通過；長測後的獨立即時觀測無已知背景遊戲及待查高負載 |
| 原有 Python | 338 項中 329 通過；9 項因舊 `0.savestate` 缺失無法重跑，沒有替換來源鎖 |
| 原有 Godot／戰鬥 | 資源驗證台、探索核心、戰鬥核心／UI／演出／時間及封裝回歸通過 |
| 三解析度與解壓冷啟動 | 1080p／1440p／4K 實際候選 EXE 通過，角色腳底、文字、家具與目標圈已檢視 |

三解析度證據在 `reports/character/qa-hd-candidate-screens-v2/`。完整 A4／A5 依據與已知美術差異見 `CHARACTER_STAGE_A4.md`、`CHARACTER_STAGE_A5.md`。四方向 GIF、逐格板及 52 張原尺寸 PNG 可從 `art/characters/map001-player/preview.html` 離線檢視；不必載入原作素材。

## A6 效能與尖峰檢查

測試機為 Ryzen 7 9700X、16 邏輯處理器、系統可見記憶體約 31.6 GiB、RTX 4070 Ti SUPER 16 GB；Windows 11 Home 10.0.26300、NVIDIA 617.14、Godot 4.7.2 Compatibility。完整機器觀測留在 `reports/character/a6-hardware.json`。

前兩次 4K 長測均保留，**不計為完整驗收通過**：

| 600 秒量測 | 平均 FPS | P95 | 最大影格 | Private 中位數增長 | Working set 中位數增長 | 節點 |
|---|---:|---:|---:|---:|---:|---:|
| `qa-hd-candidate-soak` | 59.874 | 17.067 ms | 290.403 ms | −0.443% | −1.741% | 117 |
| `qa-hd-candidate-soak-v2` | 59.900 | 17.097 ms | 301.497 ms | +0.061% | +1.100% | 117 |

後續宿主唯讀檢查發現 `bg3.exe` 自 13:12:38 起執行，檢查時仍有約 29% 3D GPU、9.4 GiB 專用顯存及 14.3 GiB private bytes。這是當時觀測，不能回推兩輪每個尖峰的負載，也不能單憑相關性認定根因。使用者已同意自行儲存退出，接著以相同 EXE／PCK／素材重新量測，沒有降低門檻或刪除尖峰。

另一次 180 秒函式邊界診斷平均 59.998 FPS，完整影格最大 33.322 ms，遊戲 `_process` wall span 最大 2.414 ms；沒有超過 50 ms。此診斷時長、執行方式與量測開銷不同，只用來縮小原因，不能替代 600 秒正式驗收。RenderingServer 前後訊號包含引擎／驅動等待，不是 GPU 執行時間。

使用者退出背景遊戲後，新的宿主觀測確認該程序不存在，接著對相同候選包重測。`reports/character/qa-hd-clean-soak/soak-4k/acceptance.json` 的 `full_acceptance=true`：

| 最後完整長測 | 結果 |
|---|---:|
| 解析度／暖機／量測 | 3840×2160／15 秒／600.012026 秒 |
| 實際影格數 | 35,990 |
| 完成路線／來源差異（含暖機累計） | 261／0 |
| 平均 FPS／P95 | 59.982／17.061 ms |
| 最大影格 | 77.941 ms |
| 超過 50 ms | 2 筆：2.391719 秒的 77.941 ms、25.576831 秒的 71.116 ms |
| 超過 100 ms | 0 筆 |
| Private 前後窗中位數 | 410,152,960 → 409,116,672 bytes（−0.253%） |
| Working set 前後窗中位數 | 267,055,104 → 256,606,208 bytes（−3.913%） |
| 節點 | 全程 117 |
| 程序 Private 取樣峰值 | 497,352,704 bytes（包含啟動） |
| 程序 Working set 取樣峰值／OS 高水位 | 270,032,896／333,602,816 bytes（包含啟動） |
| 程序 GPU 專用／共享記憶體取樣峰值 | 393,179,136／34,271,232 bytes |
| 新程序啟動至首次可確認畫面 | 1,910.571 ms（100 ms 輪詢，未清空磁碟快取） |

程序記憶體約每秒採樣，GPU 約每十秒採樣，峰值不等於連續硬體量測的絕對峰值。引擎 release allocator 回報 0，記為不可取得；記憶體驗收使用 Windows 程序數據。量測期間無截圖與 GPU readback，開始前與結束後各核對一次實際像素尺寸。

此輪修正了測試時存在外部遊戲負載的環境；相同程式未再出現 >100 ms 尖峰。這不證明某一驅動、遊戲或取樣器是舊尖峰的唯一原因。前兩輪完整資料、32 MiB private 暫升及操作時序分析繼續保留在 `reports/character/soak-spike-review.json/md`。

Windows 最終 ZIP 必須與已測試候選 EXE、PCK、三資料包逐檔比對，並從新的解壓目錄再次做三解析度啟動。比對結果另記於 `docs/CHARACTER_RELEASE.json`；只有程式與資源逐位元組相同才沿用本輪長測，不能因為檔名相同便沿用效能結果。

後續重測前可執行 `./tools/character_environment_probe.ps1` 留存短時間 CPU／GPU／VRAM 及程序身份。它不關閉任何程序，不更改系統設定；已知背景遊戲會阻擋，未識別高負載會列待查，正常桌面負載仍保留觀測。這只檢查當時取樣窗，不能宣稱整場測試或歷史環境均獨立。

## 套件來源及限制

已測試候選來源為 `9fdbfcca407a9ed8419357bd310d3a133154e87d`，建置時工作目錄乾淨。候選包 `MAP001-Character-Windows-x64-candidate.zip` 的 SHA256 為 `fd2cfae3a388ce4678d001acc3519ce272ada7c003df1c2ee61485cea1edff27`。這不是最終指定檔名的雜湊；正式交付後在 ZIP 旁另附 `.sha256`，BUILD-INFO 記錄其實際來源提交，避免把 ZIP 自己的雜湊寫進 ZIP 造成循環。

| 包 | Manifest SHA256 |
|---|---|
| 場景 | `bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc` |
| 原作角色 | `ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21` |
| 高清角色 | `00f009e7eded1ab6a3a5fb8b4c621ab03c705b43b701822eb62fb601718e511c` |

真實 GPU 的 120 FPS 尚未實測；30／60／120 的時間分割測試只證明邏輯一致性。舊存檔 SHA256 `615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab` 的九項來源回歸仍列為未能重跑，未改雜湊假稱恢復。

本輪依然只包含 MAP001 已驗證室內域。影子、裝飾物 6／7、完整鏡頭及其他場景未因此還原；高清造型與過渡影格是批准的新製作素材，不冒充原作逐幀畫面。

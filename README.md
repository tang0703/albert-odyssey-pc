# Albert Odyssey 高清 2D PC 重製

目前交付的是 **Godot 資源驗證台與可重跑的逆向／匯入工具**，不是已完成的可玩切片。
Stage B 仍未通過，尚未實作原作地圖探索、碰撞、完整事件或戰鬥。

## 使用

在此目錄使用 PowerShell：

```powershell
.\tools\bootstrap.ps1
.\tools\run.ps1 -Action test
.\tools\run.ps1 -Action run
.\tools\run.ps1 -Action qa
.\tools\run.ps1 -Action export
.\tools\package.ps1
```

`bootstrap.ps1 -SkipDownload` 驗證現有快取，不下載。Godot 4.7.2 與相同版本模板以官方
SHA512 清單校驗；Python Pillow 11.3.0 / NumPy 2.3.2 安裝在上層 `tools/pc-remake/python`。
Krita 使用已固定 SHA256 的 5.3.3 官方便攜封裝，雜湊是本輪官方 HTTPS 下載後固定，
不宣稱已驗證發行者簽章。工具安裝於專案上層的工具目錄，不修改全域 PATH。

本專案假設位於既有 Saturn 專案下，從上層 `work/extract` 與 `translation/zh-TW`
讀取本地資料。工具下載需要網路；來源、依賴及工具備齊後，匯入、測試與執行可離線。
首次建立隔離環境需要可執行的 Python 3.13 與既有 7-Zip。

## 目前可用

- 137 段、241 頁 MAP001 具名繁中對話，依原始檔雜湊、段落雜湊、位址與英文字串核對。
  這是現有主語料的 MAP001 子集，不包含所有 NPC、旁白、選項補充，也不代表全文抽取完畢。
- MAP001.V1N 的 253 筆索引紋理解碼，輸出 PNG 與尺寸、來源位址、深度及雜湊。
- 既有 VDP1 RAM 擷取比對：242 筆紋理的封裝像素資料完全相同；不是新增模擬器執行驗收。
- VDP1 命令鏈追蹤與 9 筆前綴命令的來源綁定；既有快照未通過完整命令鏈驗證，
  詳見 `docs/VDP1_TRACE.md`，不可視為一幀原作畫面已重現。
- 單一 Ymir 存檔的顯示暫存器與色盤解析，產生 6 張有來源比對的 RGBA 素材樣本。
  詳見 `docs/YMIR_SNAPSHOT.md`；尚未完成場景合成或原作畫面比較。
- NBG0／NBG1 的背景頁與捲動視窗解碼，可查看床鋪、窗戶、地板等分層內容。
  圖塊已接回 MAP001.TWN 壓縮區塊，完整 256 KiB 與 VRAM 一致。
- 已驗證室內視窗的排列與色盤也已接回來源；每層 280 項及兩張 PNG 完全吻合。
  鏡頭仍採固定參照情境，尚無完整場景載入器。詳見 `docs/SOURCE_SCENE.md`。
- 第三段資料已定位至原作工作記憶體；尚未確認碰撞／場景入口用途，見 `docs/SCENE_METADATA.md`。
- 已依原程式將第三段展開成旗標表，65,536 bytes 與存檔完全一致；旗標用途待查，見 `docs/SCENE_FLAGS.md`。
- 已重建角色座標查表與兩個局部狀態更新例程，並定位位置修正分支；完整碰撞尚未完成，見 `docs/ACTOR_FLAGS.md`。
- 三解析度文字／素材驗證台、對話切換、頁面界限與瀏覽歷史基礎。
- PC 中介事件 VM、明確文字等待、邏輯 tick 等待、條件分支及未知指令拒絕。
  VM 目前僅有合成契約測試，尚未接入原作事件翻譯器及地圖。
- PC 版本化存檔元件與備份替換；尚未連接遊戲場景。存檔必須在明確安全點進行。
- AIFF 檔頭與樣本長度驗證；FFmpeg 已完成一個本地 PCM WAV 轉換樣本。

## 資料與 Git

`source-lock.json` 固定本輪輸入來源。來源變更會拒絕匯入，不自動接受新雜湊。
需先核對原始來源、描述表與譯文是否仍對齊，再經審閱更新鎖定檔。
Godot 的 `generated/package.json` 是 Python 輸出，不手動維護。

此目錄是獨立 Git 倉庫，分支 `main`；作者僅在本倉庫設定為 MK。
程式、測試、格式說明與摘要納入 Git；原始光碟、BIOS、抽出素材、生成結果、
工具二進位、個人設定、快取與本地打包均不納入。Git LFS 已在本倉庫啟用，
供未來可納入版本管理的原創大型美術使用；目前沒有原始遊戲素材被加入 Git。

`build/windows/ao-asset-workbench.exe` 與 `.pck` 為本地開發工具。
本地 PCK 包含由使用者來源抽出的資料，不是可公開發行的遊戲套件。
原始映像與 BIOS 不放入任何打包；沿用上層 LOCALIZATION.md 的發行規則。
Godot 與第三方聲明位於 `licenses`，Windows 套件亦附帶。

## 驗證與限制

測試與短時渲染紀錄位於 `reports`，摘要見 `docs/STATUS.md`。
Godot 在一般沙箱中會記錄 Windows 憑證庫／user:// 快取存取錯誤；
來源測試、匯出及三解析度截圖仍可完成。這些不是遊戲邏輯通過證明，
也未藉由改動系統憑證、安全設定或權限來消除。

系統字型使用 Windows 的 Microsoft JhengHei／Microsoft YaHei 作為本地原型顯示，
不複製或再散布系統字型。正式跨平台版本需另選並附帶允許發行的繁中字型。

下一階段依 `docs/STATUS.md` 的來源與驗收關卡推進，不能以診斷灰階圖當成完成的高清美術。

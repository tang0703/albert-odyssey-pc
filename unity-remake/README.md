# MAP001 Unity 起始房間切片

獨立 Unity 6.3 LTS 專案。Godot 專案、來源包與既有交付不變。

U1／U2 已完成；U3 第二版方向已核准，U4 已接入 22 骨、六動作及 URP 材質。候選驗收與限制見 docs/UNITY_U5_ACCEPTANCE.md。

入口工具：`tools/unity_source_baseline.py` 核對十一份來源／外觀包，另複製核准的最小執行資料至忽略版本管理的 `Assets/StreamingAssets/SourceLocal`。重播期望值留於本地測試資料，不打入執行包，也不能用它們驅動核心。

工具與驗收紀錄見 `docs/UNITY_MIGRATION_PROGRESS.md`。本輪不執行負載、長循環、效能基準或實際 GPU FPS 測試。

U2：`pwsh -NoProfile -File tools/unity_u2.ps1 -Action build` 建置灰模；`-Action launch` 執行一次自動操作與畫面檢查。正常遊玩直接開啟 `reports/unity/last-u2-build.txt` 指向目錄中的 `MAP001-Unity-U2.exe`，不附測試參數。

操作：方向鍵／WASD 移動，Enter 互動／翻頁，E 裝備，方向鍵選項、Enter 確認、Esc 返回。Space 暫停、`.` 單步、R 重設，F1 診斷、F2 膠囊／標記。灰模家具只是位置參照；碰撞由鎖定來源核心計算，沒有 Rigidbody 或 Root Motion 位移。

灰模繁中使用本機 Microsoft JhengHei 動態字型，不打包 Windows 字型檔；正式交付字型仍列 U4 待辦。TMP 官方必要資源及 Liberation Sans 的 OFL 隨原資源保留。

正式骨架版：`pwsh -NoProfile -File tools/unity_u4.ps1 -Action build`；短程檢查 `-Action launch -Width 1920 -Height 1080`，提醒分支加 `-Route reminder`。此流程不作效能測試。封裝需乾淨來源提交：`python tools/unity_package.py --build <建置目錄>`。

新版使用隨附 Noto Sans CJK TC（OFL），F2 切換 3D／診斷標記；詳細操作見 `docs/UNITY_PLAY_GUIDE.md`。`tools/unity_u4_validate_rig.py` 用 Blender 背景模式重開來源核對權重、UV、循環與根骨；`tools/unity_u4_assets.py verify` 核對素材雜湊。

# 落點左側事件候選交付

套件名稱：`MAP001-Landing-Event-Candidate-Windows-x64.zip`。最終版本、SHA256、解壓啟動及測試結果記錄於 `LANDING_EVENT_CANDIDATE_RELEASE.json`；套件內 `BUILD-INFO.json` 記錄二進位來源提交與逐檔雜湊。

功能範圍為單向下樓、左側 LAIA 事件與經來源驗證的最小後續行走區域。事件在本場景恢復控制；不載入第三場景。前版行走、角色、室內、事件、互動、裝備及轉場套件保留。

候選封裝僅接受九包核准清單、必要 Godot 程式及授權、來源／演出報告與三解析度短程截圖。原始光碟、BIOS、RAM、快照、擷取工具與未核准腳本均不打包。原作素材及含素材 ZIP 留在本地。

功能驗收與效能分開：`functional_passed` 只有在來源、核心、介面、畫面、回歸及封裝通過後才設為 true；完整 `passed` 保持 false，狀態為 `performance_validation_deferred_by_user`。本輪不執行效能或負載測試。

尚未完成：來源影子、自由 NPC 互動、目的地整室探索、雙向往返、戰鬥串接、存讀檔、完整音樂播放、前版效能驗收及 Stage B 整體。缺失舊快照的九項回歸與效能證據相依測試保持明列。

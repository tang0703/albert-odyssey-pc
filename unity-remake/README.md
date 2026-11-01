# MAP001 Unity 起始房間切片

獨立 Unity 6.3 LTS 專案。Godot 專案、來源包與既有交付不變。

目前是 U1 工具與來源基準階段，並非可玩或美術候選版。只完成實測的關卡才記錄通過；不可將空白範例當成起始房間移植完成。

入口工具：`tools/unity_source_baseline.py` 核對十一份來源／外觀包，另複製核准的最小執行資料至忽略版本管理的 `Assets/StreamingAssets/SourceLocal`。重播期望值留於本地測試資料，不打入執行包，也不能用它們驅動核心。

工具與驗收紀錄見 `docs/UNITY_MIGRATION_PROGRESS.md`。本輪不執行負載、長循環、效能基準或實際 GPU FPS 測試。

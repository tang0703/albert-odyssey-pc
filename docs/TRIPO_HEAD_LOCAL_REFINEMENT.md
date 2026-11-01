# Tripo 頭部：保留方向的本地局部修整

2026-11-01。使用者回覆「接近我要的方向」，視為頭臉與髮型方向確認，
不視為最終人物、美術或 C2 通過。這次只做本地靜態修整；新增 API 任務 0、費用 0 點。

## 本次採用

- `art/local/tripo-head-v1/refined-08/`：從未修改的 `prepared-02` 建立。
- 鼻翼小幅收窄、降低突出量，嘴角局部柔化；保留原眼部幾何與自訂法線。
- 修改 2,956 個頂點；修改範圍外 990,562 個頂點逐座標不變。
- 保留原有 993,520 頂點、1,888,606 三角面；仍不是最終遊戲拓樸。
- 可編輯 `.blend` 中 `Local_Face_Refine_01` 形變值可關閉，還原基底幾何。
- Unity 使用形變後烘成的靜態 FBX，不依賴執行時形變權重。

原始 GLB、prepared-02、舊 Hunyuan 模型與舊 v2 模型雜湊均未改動。
未替換正式遊戲玩家、房間、來源包或規則。

## 未採用的嘗試與缺口

- refined-01～05：眼球刻線經表面擬合仍留下裂痕，不採用。
- refined-06：局部三角面鬆弛造成眼部破面，不採用。
- refined-07：保留眼部幾何但全域重算法線，使刻線變得更明顯，不採用。
- refined-08 保留原眼部與來源法線。**眼球刻線清理仍未完成**，不是已修復。
- 髮根、羽飾銜接、眼部最終拓樸、UV、材質、骨架與動畫仍待後續工作。

以上嘗試及日誌留在本地，沒有以反覆生成消耗點數。

## 實際審閱與檢查

- 審閱頁：`art/local/tripo-head-v1/review-local-01/review.html`。
- 36 張 Unity URP 實際畫面，中性／暖光、四向／斜側與頭臉近景。
- 比較欄為核准方向的 Tripo 原始樣本與 refined-08；同鏡頭、光線、灰色材質。
- 圖片沒有後製修形；46 張圖嵌入 HTML，避免外部路徑造成破圖。
- 20 組方向／光線／裁圖切換以 DOM 替身檢查圖片鍵值；不是實際瀏覽器操作驗收。
- 獨立 Blender 重新開檔檢查：形變基底、拓樸、有限座標、保護範圍、來源與匯入雜湊通過。
- 3 項 Unity 來源契約防護測試通過。
- Unity 建置及短程擷取成功，沒有截圖逾時。
- 擷取日誌仍有 `d3d12: failed to query info queue interface (0x80004002)`；保存警告。
- 完整來源、產物及 HTML 雜湊在本地 `report.json`、`review-lock.json`、`refined-08/validation.json`。

本次僅靜態造型審閱，**沒有動畫、蒙皮、負載、長循環或 GPU FPS 測試**，
也沒有宣稱完整遊戲功能或美術驗收通過。

## 重現

1. Blender 執行 `tools/tripo_head_local_refine.py -- --out refined-<新兩位版本>`。
   預設只修鼻翼與嘴角；`--experimental-eyes` 僅保留失敗研究用途，不是合格修整。
2. `tools/tripo_head_unity_review.ps1 -Action build -ArtVersion refined-08`。
3. 同工具 `-Action capture`。
4. `tools/tripo_head_review_page.py --capture <目錄> --prepared refined-08 --out <新目錄> --local-refine`。

每次使用新目錄保留歷史；所有本地模型與圖像維持本地，Git 只提交工具與說明。

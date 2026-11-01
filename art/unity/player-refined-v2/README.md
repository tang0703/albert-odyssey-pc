# MAP001 玩家重做 v2：靜態輪廓審閱

使用者於 2026-11-01 要求依原概念圖重做頭臉、髮型與服裝輪廓，並以 Unity 實際畫面審閱。v1 已退回；此版不是核准造型或正式遊戲替換。

開啟 `review.html` 查看原概念、v1／v2、中性光／暖光四方向、臉部及 45° 房間比例。圖片全部內嵌，不需要同目錄圖片路徑或 JavaScript。原概念局部以 SVG 視窗裁切檢視，沒有修改其像素；Unity 圖像未經修圖。

## 可編輯來源

- `player-refined.blend`：原生分區材質與 UV。`MAP001_PLAYER_REFINED_STATIC` 是合併輸出網格；隱藏的 `EDITABLE - unrigged reference surfaces` 集合保留獨立表面。編修時先隱藏合併網格，再開啟該集合，避免兩份模型重疊。
- `player-surface.fbx`、`surface-materials.json`：本次 Unity 審閱使用的網格、線性色彩與粗糙度。由 URP Lit 呈現，沒有相片或概念圖看板。
- `player-textured.blend`、`player-static.fbx`、`textures/`：2048px UV 烘焙試作，存在細節黑邊，沒有作為最終材質通過；本次正式審閱改用分區材質隔離問題。
- `geometry.json`、`material-manifest.json`、`review-lock.json`：幾何檢查、輸入雜湊、渲染來源與待審閱狀態。

## 本輪範圍與限制

從新的曲面重建，沒有呼叫舊版 `build_player`。包含較窄的眉眼、連續下巴、交疊髮束、頭帶／羽飾、收腰上衣、袖口、分片衣襬、圍巾、褲管與靴型。高度 1.125、腳底 Z=0。

仍是造型稿：髮束層次、神情、布料細節與概念插畫有差異，需使用者審閱。表面模型未做最終變形拓樸、骨架、權重或動畫，不應直接當成已可用遊戲角色。沒有執行玩法回歸、負載、長循環、效能基準或 GPU FPS 測試。房間、Cirrus、來源狀態與舊美術未變。

前幾輪 Unity 捕捉、無陰影／無法線診斷及建置日誌保留於本地 `reports/unity/character-*`。截圖生成成功只代表擷取成功，不代表使用者造型核准。

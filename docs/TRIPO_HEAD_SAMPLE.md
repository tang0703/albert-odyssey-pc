# Tripo 頭部樣本 01：Unity 靜態審閱

2026-11-01。使用者核准一次 40 點試作，已生成並完成 Unity 靜態對照。
這是頭部造型樣本，**尚未通過美術審閱**，不代表 C2、人物整合或最終拓樸完成。

## 輸入與實際費用

- 四張已核准彩色概念頭部裁圖：front / left / back / right。
- 六張使用者線框截圖只有圖片，作形體審閱參考；沒有上傳到本次任務，沒有取得或還原其原始網格。
- Tripo CLI 0.9.0，海外區 ov，H3.1：`v3.1-20260211`。
- 唯一付費步驟：`POST /v3/generation/multiview-to-model`。
- `texture=false`、`pbr=false`、`geometry_quality=detailed`、seed `20261101`。
- 任務 `890ddc6a-987d-4a73-8600-0bf1f2cce70e`：成功，**實扣 40 點**。
- 合計 **40 點**；生成後查詢剩餘 **460 點**、凍結 **0 點**。
- 無自動重抽、雲端貼圖、綁骨、動畫或付費轉檔。Blender 本地匯出不使用 API 點數。

## 本地成果

根目錄：`art/local/tripo-head-v1/`，所有生成物、圖片及模型留本地。

- `tripo-out/player-head-tripo-01-890ddc6a/`：原始 GLB、服務預覽、task.json。
- `prepared-01/`：初次方向診斷，保留。此版診斷名稱不代表已對準的角色方向。
- `prepared-02/`：將原始 +X 朝向旋轉 -90 度至 Blender -Y，歸一展示高度；原始 GLB 不變。
- `prepared-02/head-editable.blend`：可編輯靜態網格。
- `prepared-02/head-palette.fbx`：Unity 審閱用 FBX，僅灰色材質。
- `review-01/review.html`：自包含審閱頁；概念／前次 Hunyuan refined-02／新樣本對照。
- `review-01/unity/`：36 張 Unity URP 實際畫面，中性及暖光、四面與斜側、頭臉近景。
- `review-01/report.json`、`review-lock.json`：來源、費用、圖片與產物雜湊。

頭部展示高度統一為 1，但外接盒包含頸部／圍巾，不能當成精確頭身比量測。
檢查光線不是正式房間照明。原始模型有 993,520 個頂點、1,888,606 個三角面，
目前是雕塑／重拓樸參考，不能宣稱已具備合格的遊戲網格、UV 或蒙皮。

## 檢查結果與限制

- Unity 獨立建置及短程擷取成功；36 張 900×900 圖片可讀，沒有本次截圖逾時。
- 審閱頁嵌入 46 張圖片（36 Unity、4 概念、6 線框），不依賴外部圖片路徑。
- 三項來源契約防護測試通過；原 v2 與前次 Hunyuan `.blend` 雜湊保持不變。
- 本次未替換正式玩家或修改房間、來源包及規則；沒有重跑整場遊戲功能驗收。
- Blender 在寫使用者縮圖快取時有權限訊息，模型保存與四方向輸出成功；原始日誌保留。
- Unity 日誌有 `d3d12: failed to query info queue interface (0x80004002)`；程序正常退出，36 張畫面完整。保留此診斷，不將它描述為零警告執行。
- 觀察：新樣本臉頰、下巴及髮束銜接較完整；鼻翼、嘴角、眼球刻線、髮根與羽飾仍待精修。
- 無貼圖；虹膜配色、皮膚及布料材質尚未驗收。沒有承諾或執行下一次付費生成。
- **動畫、蒙皮、負載、長循環及實際 GPU FPS 均未測試。**

## 重現靜態審閱（不提交 Tripo 任務）

1. Blender 執行 `tools/tripo_head_review_prepare.py`，指定原始 GLB、全新的輸出目錄及 `--yaw -90`。
2. `tools/tripo_head_unity_review.ps1 -Action build -ArtVersion prepared-02`。
3. 同工具 `-Action capture`。保留每次獨立日誌與輸出，不覆蓋歷史。
4. `tools/tripo_head_review_page.py --capture <擷取目錄> --prepared prepared-02 --out <新審閱目錄>`。

舊審閱模式的預設保持原狀；新增 `-tripoReview` 僅啟用獨立審閱場景的灰模近景。
任何新一輪付費生成須先列出輸入、設定及費用，再由使用者核准。

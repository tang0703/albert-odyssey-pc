# Tripo 完整人物：Unity 靜態審閱

2026-11-01。起點 `74f01a5`。使用者同意單次 40 點生成後，明確指定
「直接由 tripo 生成整體」。本版採用同一次生成的頭、臉、身體與服裝，沒有拼接舊頭。

## 任務與產物

- 任務 `image_to_model`：`0dde299a-f45b-4076-9182-bbd84bf7c1d4`。
- 模型 `v3.1-20260211`、detailed PBR、面數上限 80000、種子 20261102。
- 原概念 `art/enhanced25d/v1/references/approved-character.png`；SHA256
  `a7a5771b31642a17e636ae10bd0caee8ea073ce93d0be512a278f7982f3da108`。
- 單次及本次合計 **40 點**，生成後餘額 **400**、凍結 **0**。改採完整人物無額外任務。
- 原始 GLB：`art/local/tripo-body-v1/tripo-out/player-body-01-0dde299a/model.glb`；SHA256
  `f37052fb7c617d684cd71a1b43155542c0aa874578fb53be934c8068432b49fe`。
- 模型：`art/local/tripo-body-v1/body-fit-03/player-body-preview.blend`、`player-static.fbx`、4K PBR PNG。
- 自包含頁：`art/local/tripo-body-v1/review-full-01/review.html`。
- 靜態建置：`build/unity-body-review-947ce995d18440bf97ff74f44701e27e/Body-Fit-Review.exe`。
  這是輸出圖片的審閱程式，不是可玩候選版。

## 處理與驗證

保留全部 47,498 頂點、79,434 三角面。僅統一朝向、腳底零位、等比縮放至
1.125 Unity 單位；沒有遮面、裁頭、拼接、雕塑、骨架或動畫。
GLB 貼圖本地提取，roughness 轉 Unity smoothness，normal 使用 GL 格式。

Blender 重新開檔比較原 GLB 與 .blend 座標、索引、UV、角點法線，摘要一致：
`e443697b6b56a6d0d1343e0af21ba44d18744a30bbb1318c7b1107858522f70a`。
核對面數、材質索引、零遮面、圖片打包、無骨架／動畫與高度通過。
全部舊頭核准檔案雜湊不變。既有三項來源防護測試通過。

Unity 6000.3.27f2／URP：中性／暖光各四向、斜側、45°、領口、腰帶、靴子，
另有四向灰模及舊房間 45° 靜態尺寸圖，共 23 張。沒有 RoomSession、動畫取樣或玩法更新。
房間未修改，其圖不能當成玩法整合或角色可讀性驗收。

瀏覽器實測 25 張內嵌圖片解碼、22 次視角／光線切換、放大／關閉、
1440px／390px 排版通過，無頁面錯誤或手機橫向溢出。
紀錄 `reports/unity/tripo-full-browser-check.log`，desktop/mobile 圖同目錄。

## 保留的失敗與限制

- D3D12 兩次擷取都寫完圖片，但退出失敗。日誌
  `body-capture-7a7372836cbe422485ec5f9c3b342a78.log`、
  `body-capture-04ac136021bd4aecbfd87d33380e41b9.log` 保留；後者確認 exit
  `-1073741819`（access violation）。根因未定位，不宣稱 D3D12 已修復。
- 靜態審閱改用 `-force-d3d11`，完整擷取並 exit 0：
  `reports/unity/body-capture-720ce9569345489282a69753c54f8ad1`。
  不改遊戲正式 renderer 設定，不以重試抹除失敗。
- Blender 縮圖／擴充快取權限警告保留。首次圖片驗證未觸發 packed image 延遲解碼，
  修正後 `reports/unity/tripo-full-validation-03b.log` 通過。
- 眼周表面起伏、髮束接縫、頭帶與指縫需人工精修；生成貼圖可能含明暗，
  不宣稱無光照 albedo 或最終材質。背面屬生成補全，未有原作造型驗證。
- 完整人物需重新審閱，不沿用舊頭核准。無動畫、蒙皮、完整玩法、負載、長循環或 FPS 測試。

## 重現

1. 使用已有原 GLB，不重送付費任務；`tools/tripo_body_textures.py` 提取 PBR。
2. Blender：`tools/tripo_body_full.py -- --version body-fit-<新序號>`。
3. Blender：`tools/tripo_full_validate.py -- --version <版本>`。
4. `tools/unity_body_review.ps1 -Action build -ArtVersion <版本> -TripoBody`；再 capture。
5. `tools/unity_body_review_page.py --version <版本> --capture <目錄> --out <新目錄> --tripo-full`。

工具、文件納入 Git；模型、參考、圖片、請求／回應、建置留本地。
狀態：**Tripo 完整人物 Unity 靜態審閱版；等待造型審閱，動畫與效能未驗收。**

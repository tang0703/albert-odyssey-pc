# 頭部眼部重建與基礎上色審閱版

2026-11-01，基準 `64ef7dd`／`refined-08`。本次只建立本地靜態頭部審閱；
Tripo 任務與新增點數均為 0。沒有動畫、蒙皮、身體／房間整合或負載測試。

## 審閱入口與資產

- 審閱頁：`art/local/tripo-head-v1/review-eye-color-02/review.html`。
- 本地素材：`art/local/tripo-head-v1/eye-color-18/`。
- `head-editable.blend`：原模型隱藏封存、保留表面、新左右眼、可編輯 `HeadPaint` 色彩層。
- `head-palette.fbx`：靜態模型；`head-basecolor.png`、`eye-basecolor.png` 均為 2048×2048。
- `palette.json`、`color-source.json`：具名區域、基礎色與粗糙度。
- `geometry-report.json`、`validation.json`、`unity-inputs.json`：來源、修改範圍與匯入雜湊。
- `review-eye-color-02/report.json`、`bundle-lock.json`：交付檔案、程式與檢查證據。

## 眼部與保護範圍

左右眼分別依來源開口建立曲面，未強制鏡像。使用受邊界約束的三角化及平滑深度，
邊界座標直接取自來源；虹膜及瞳孔改用專用 UV 貼圖，沒有烘入高光。

刪面後重建網格的早期方案造成 Blender 自訂法線重新量化，最大差約 0.0443°，已拒絕。
採用版複製原網格儲存資料，以 `source_eye_hidden` 面標記及 `SourceEyeHidden` 材質
將 **5,316 個舊眼球面排除顯示**；並非從可編輯網格中刪掉它們。
Unity URP 使用 alpha clip，灰模切換同樣保留此隱藏材質。舊模型另存隱藏集合。

此方案保留全部 993,520 個來源頂點及來源面資料，座標與 Blender 角點法線逐值完全相同。
新增兩個眼面共 4,906 個三角面，不宣稱新總模型與原模型具有相同拓樸。
它仍是高密度靜態研究資產，未做最終遊戲拓樸整理。

獨立重新開檔確認：原始 GLB、refined-08 及既有來源雜湊未變；
受保護眼瞼未被遮除；眼面沒有退化面、反面或重複面，邊界座標精確接合。
這些資料檢查不等同所有角度的美術驗收。

## 基礎材質與已知缺口

使用棕髮、棕色虹膜、綠頭帶、象牙色羽飾、紅圍巾及自然膚色。
頭部沿用來源 UV，以可編輯色彩層烘焙純色彩；沒有烘入光照、AO 或投影。
眼睛另有 UV 與貼圖，材質使用 URP Lit。

**尚未通過所有視覺條件。** 髮根、部分瀏海末端、羽飾外緣及圍巾交界仍有局部串色；
眼白外緣保留區域仍可見細小來源紋理。審閱頁明列這些差距，沒有標記人物／最終材質完成。
後續應先針對這些邊界精修並由使用者審閱，再決定是否進入身體、動畫或雲端材質流程。

## 實際驗證

- Unity 6000.3.27f2 建置及獨立短程擷取成功，最終 **60 張 900×900 實際渲染**。
- 舊灰模、新灰模、新上色，同高度、鏡頭與照明；中性／暖光、四向、斜側、臉部近景、45° 俯視。
- 自包含 HTML 嵌入 60 張 Unity 圖及 4 張概念圖，保留原始擷取，不後製修形。
- 使用隔離 Chrome 實際按鈕驗證 **72 組**方向／光線／近景／顯示模式；圖片均可解碼。
- 圖片放大、關閉、1680 像素桌面與 600 像素窄視窗檢查通過，沒有水平溢出。
- 既有 `tests.test_unity_source_baseline` **3 項通過**。
- 必要匯入檔必須列入雜湊清單；缺失貼圖、材料映射或無效 UV 會使 Unity 建置停止。

本次沒有重跑整個玩法回歸，也沒有用短程畫面宣稱動畫、效能或遊戲整合通過。

## 保留的失敗與警告

- eye-color-01～17 的局部眼面、材質分區及法線試驗留在本地；未作為最終審閱採用。
- eye-color-18 首次 Unity 灰模切換覆蓋了隱藏材質，重新露出舊眼刻線；
  該畫面及 `review-eye-color-01` 留存。修正後使用新的建置、擷取及 `review-eye-color-02`。
- Blender 縮圖快取寫入失敗與 `use_nodes` 棄用警告保留；模型、貼圖及實際圖另行驗證。
- Unity 擷取日誌有 `d3d12: failed to query info queue interface (0x80004002)`；
  最終擷取成功，沒有截圖逾時。
- Playwright 阻擋 `file:` 網址，改用只綁定 127.0.0.1 的本機靜態伺服器；
  頁面 favicon.ico 有一次 404，與嵌入圖片無關。該紀錄保留，沒有抹除成零警告。

## 重現

1. Blender 執行 `tools/tripo_head_eye_color.py -- --out eye-color-<新兩位版本>`。
2. Blender 執行 `tools/tripo_head_eye_validate.py -- --art <版本>`。
3. `tools/tripo_head_unity_review.ps1 -Action build -ArtVersion <版本>`，再執行 `-Action capture`。
4. `tools/tripo_head_eye_review_page.py --capture <擷取目錄> --art <版本> --out <新審閱目錄>`。
5. 實際開頁檢查並保留瀏覽器結果，不能只驗證圖片鍵值。

工具與文件納入 Git；模型、貼圖、參考圖、建置及審閱產物維持本地保存。

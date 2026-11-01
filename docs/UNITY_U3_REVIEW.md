# U3 房間與人物 3D 初稿審閱

狀態：**第一版依回饋修整後，使用者已核准第二版造型方向。U4 骨架、動畫與材質精修接續進行。**

目前審閱頁：`art/unity/startroom-v2/review.html`。第一版頁面與未核准紀錄保留。

## 第二版人物修整（造型方向已核准）

依使用者回饋修整髮束、五官、身形、手指、頭帶繫結、衣襬與皮靴。實際 Unity 四方向與房間預覽位於 `art/unity/startroom-v2/unity-review/`；身高仍為 1.125 Unity 單位，房間產生函式與第一版完全相同。

第二版 Blender 檔已獨立重新開啟（702 物件、462 網格、零骨架與動作）；Unity 預覽建置及五張畫面完成。全部預覽及模型以第二版 `review-lock.json` 保存雜湊，`approved=true`（僅造型方向）。使用者明確核准「採用第二版造型方向，繼續骨架與材質精修」。臉部／髮束／布料局部陰影、拓樸與最終材質仍非完稿，不宣稱已完全重現概念圖品質。

此輪只修整美術及預覽版本選擇，沒有改動核心。十一份舊包、254 檔及五份核心鎖定內容核對未變。沒有執行負載或效能測試。

## 第一版保留紀錄

- 可編輯來源：`startroom-draft.blend`，另有房間與人物獨立 FBX。
- 人物：棕髮束、綠頭帶、淺色羽飾、綠衣、紅圍巾與皮靴；初稿採簡化雕塑造型，五官、髮束與衣褶仍需精修。
- Unity URP 實際靜態渲染：`unity-review-v3/`，四方向與房間圖。人物匯入後統一高度 1.125 Unity 單位＝36 來源單位。
- 房間：固定 45° 正交鏡頭，來源原點 `(512,1536)`、14×8 Unity 單位參照；家具初稿依既有美術定位。尚不宣稱每件 3D 家具的輪廓、占地與玩家遮擋都已驗收。
- Blender 程序木紋／布料圖是另列的美術預覽，尚未烘焙成 Unity 最終貼圖。Unity 目前以 URP Lit 色彩及即時光影審閱形體。
- U3 預覽程式完全不驅動核心，只提供靜態造型與比例。U2 的可操作灰模仍獨立保留。

第一版 `review-lock.json` 保持未核准；第二版鎖定實際審閱的模型、畫面及頁面，另記錄使用者核准。審閱 HTML 保留送審時內容，不為修改狀態而改寫已核准檔。不得將使用者對舊 2D 圖片的核准當成本次 3D 造型核准。

## 修正與保留紀錄

首次 FBX 四方向旋轉覆蓋了匯入根節點的軸向修正，造成人物橫倒；已改以獨立父節點旋轉，原匯入姿態保留。房間 XZ 軸符號校準也明記於 `review.json`。

第一版材質偏亮，已調整暖光、色彩與柔和陰影。前兩次診斷圖保留在本地 `unity-review/`、`unity-review-v2/`，不列入待核准美術。Blender 嘗試寫入工作區外縮圖快取遭拒；可編輯 `.blend`、FBX 與正式渲染檔仍成功，相關日誌保留於 `reports/unity/`。

## 重建

```powershell
pwsh -NoProfile -File tools/unity_u3.ps1 -Action models -ArtVersion startroom-v2
pwsh -NoProfile -File tools/unity_u3.ps1 -Action build -ArtVersion startroom-v2
pwsh -NoProfile -File tools/unity_u3.ps1 -Action review -ArtVersion startroom-v2
```

models 只供尚未核准的初稿迭代；核准後必須另開素材版本，不覆蓋核准檔。review 每次寫入新的本地輸出目錄，不覆蓋既有失敗或成功畫面。

核准後才進 U4：角色拓樸與 UV 整理、骨架、待機／行走／來源必要取得動作、材質貼圖、家具遮擋與完整流程。U5 最終候選 ZIP 尚未製作。效能仍未驗收。

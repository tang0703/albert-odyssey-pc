# U3 房間與人物 3D 初稿審閱

狀態：**使用者要求先修整人物，更接近原概念圖。第一版未核准，沒有開始正式骨架或動畫製作。**

審閱頁：`art/unity/startroom-v1/review.html`。

- 可編輯來源：`startroom-draft.blend`，另有房間與人物獨立 FBX。
- 人物：棕髮束、綠頭帶、淺色羽飾、綠衣、紅圍巾與皮靴；初稿採簡化雕塑造型，五官、髮束與衣褶仍需精修。
- Unity URP 實際靜態渲染：`unity-review-v3/`，四方向與房間圖。人物匯入後統一高度 1.125 Unity 單位＝36 來源單位。
- 房間：固定 45° 正交鏡頭，來源原點 `(512,1536)`、14×8 Unity 單位參照；家具初稿依既有美術定位。尚不宣稱每件 3D 家具的輪廓、占地與玩家遮擋都已驗收。
- Blender 程序木紋／布料圖是另列的美術預覽，尚未烘焙成 Unity 最終貼圖。Unity 目前以 URP Lit 色彩及即時光影審閱形體。
- U3 預覽程式完全不驅動核心，只提供靜態造型與比例。U2 的可操作灰模仍獨立保留。

`review-lock.json` 鎖定這次待審閱的模型、畫面及頁面，`approved=false`。不得將使用者對舊 2D 圖片的核准當成本次 3D 造型核准。

## 修正與保留紀錄

首次 FBX 四方向旋轉覆蓋了匯入根節點的軸向修正，造成人物橫倒；已改以獨立父節點旋轉，原匯入姿態保留。房間 XZ 軸符號校準也明記於 `review.json`。

第一版材質偏亮，已調整暖光、色彩與柔和陰影。前兩次診斷圖保留在本地 `unity-review/`、`unity-review-v2/`，不列入待核准美術。Blender 嘗試寫入工作區外縮圖快取遭拒；可編輯 `.blend`、FBX 與正式渲染檔仍成功，相關日誌保留於 `reports/unity/`。

## 重建

```powershell
pwsh -NoProfile -File tools/unity_u3.ps1 -Action models
pwsh -NoProfile -File tools/unity_u3.ps1 -Action build
pwsh -NoProfile -File tools/unity_u3.ps1 -Action review
```

models 只供尚未核准的初稿迭代；核准後必須另開素材版本，不覆蓋核准檔。review 每次寫入新的本地輸出目錄，不覆蓋既有失敗或成功畫面。

核准後才進 U4：角色拓樸與 UV 整理、骨架、待機／行走／來源必要取得動作、材質貼圖、家具遮擋與完整流程。U5 最終候選 ZIP 尚未製作。效能仍未驗收。

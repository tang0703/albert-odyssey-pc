# Tripo 頭部上色審閱版

2026-11-01；從 `06108ca` 的本地眼部／上色研究接續。使用者改採 Tripo 上色，
並核准一次 20 點 HD／PBR 任務。保留原始造型及本地版本，未替換遊戲玩家。

## 費用與任務

| 項目 | 結果 |
|---|---|
| Tripo `texture_model` | `39e6ab01-c274-49e6-9043-d4dcd81144c1` |
| 貼圖版本 | `v3.0-20250812`；detailed、PBR、original_image；seed 20261101 |
| 輸入 | 可見頭部＋獨立眼球 GLB，四方向原概念頭部參考 |
| 實際扣點 | **20 點（US$0.20）** |
| 本輪總計 | **20 點**，沒有重試、幾何生成、綁定或動畫任務 |
| 完成後餘額 | **440 點**，凍結 0 |

核准、上傳、請求、成功任務及餘額紀錄留在
`art/local/tripo-head-v1/cloud-texture-01/`。付費提交已完成，不可為重建審閱頁再次提交。
原始結果：`cloud-texture-01/tripo-out/head-texture-01-39e6ab01/model.glb`，
SHA256 `0c638930c451a45b5becd00e6ac8de6b898031e83873b9d113c59af1d9195b6d`。

## 資產與審閱

- 自包含頁：`art/local/tripo-head-v1/review-cloud-texture-01/review.html`。
- 轉換素材：`art/local/tripo-head-v1/cloud-ready-01/`。
- `head-editable.blend` 包含三個網格、九張內嵌材質圖片；`head-palette.fbx` 為靜態匯出。
- 保留原始貼圖；PNG 解碼及 Unity metallic/smoothness 通道轉換不重畫色彩。
- 頭部主材質為 4096×4096，左右眼材質各 128×128；不是全部材質均為 4K。
- `palette.json`、`unity-inputs.json`、`preparation.json`、`blender-conversion.json`
  與 `validation.json` 保存映射、尺寸、雜湊及局部轉換證據。

Unity 使用 URP Lit、色彩／法線／金屬與平滑度貼圖。保留雲端雙面設定。
雲端沒有獨立 AO 圖，不宣稱具備另製的 AO。灰模檢查關閉貼圖，舊版眼面隱藏規則保留。

## 幾何結果與限制

可見模型共 **1,888,196 三角面**。Tripo 改變頂點／面排列並將 glTF Y 位移 −0.5。
逐網格排序及三角面方向比較後，扣除該位移的位置最大誤差 **1.49×10⁻⁸**，
有向三角面與 UV 相同。這是從資料推導並核對的位移，非 API 回傳的轉換 metadata。
Blender 將 Z 加回 0.5，沒有局部雕刻、縮放或新造型生成。

**部分頂點法線不同**：頭部最大分量差約 1.97；不可將這版描述成「座標及法線全部不變」。
原始 GLB、refined-08、本地 eye-color-18 均保持雜湊不變，雲端輸出作獨立分支保存。

實際畫面中，髮型／頭帶／羽飾及紅圍巾分區較本地前版清楚。
仍需審閱眼白偏灰、眼瞼外緣、鼻口細節與部分髮根接縫；眼睛貼圖包含風格化高光，
不能聲稱基礎色完全沒有光照表現。髮色較偏金棕，並非概念圖逐像素複製。
高密度靜態頭部尚未完成全身、遊戲拓樸、蒙皮或最終材質驗收。

## 實際驗證

- Unity 6000.3.27f2 建置及獨立短程啟動成功；80 張 900×900 實際畫面。
- 本地前版／雲端版，各有灰模及上色；中性／暖光、四向、斜側、臉部及 45° 俯視。
- 自包含頁嵌入 80 張 Unity 圖及 4 張概念圖；隔離 Chrome 48 組控制組合通過。
- 84 張圖片全部可解碼；放大／關閉、1680 與 600 像素視窗無水平溢出。
- Blender 重新開啟、圖片打包、UV、三個材質及來源／匯入雜湊檢查。
- 既有 `tests.test_unity_source_baseline` 三項通過。
- 本輪沒有遊戲、動畫、負載、長循環、效能基準或實際 GPU FPS 測試。

## 保留的警告

- Blender 系統縮圖寫入失敗；模型與 FBX 匯出成功，記錄保留於 `tripo-cloud-blender-01.log`。
- Unity build 有 LicensingClient validation／access token 更新訊息，之後已解析 Personal
  entitlement 並成功建置；未刪除前述日誌。
- 擷取日誌有 `d3d12: failed to query info queue interface (0x80004002)`；80 張擷取成功，無逾時。
- 本次瀏覽器檢查零頁面錯誤；舊版失敗／警告紀錄未覆寫。
- 第一次 Blender 重開驗證將延遲載入的 `has_data=false` 誤判為缺圖；
  確認九張均已打包，實際讀取像素後成功解碼。修正為解碼後檢查，首次失敗日誌保留。

## 重建本地產物

1. `tripo_head_texture_input.py` 只準備乾淨輸入；**不代表獲准再次呼叫付費 API**。
2. `tripo_head_cloud_assets.py` 讀取已完成的固定原始結果，核對幾何並轉換 PBR 貼圖。
3. Blender 執行 `tripo_head_cloud_prepare.py` 及 `tripo_head_cloud_validate.py`。
4. `tripo_head_unity_review.ps1 -Action build -ArtVersion cloud-ready-01`，再執行 capture。
5. `tripo_head_cloud_review_page.py --capture <新擷取目錄> --out <新審閱目錄>`。

素材工具拒絕覆寫已有版本；需新版本時先另命名，不刪除已核准輸入或既有結果。
工具／文件提交 Git，模型、參考圖、貼圖、任務私有紀錄及審閱產物留本地。

完成狀態：**Tripo 頭部上色 Unity 審閱版；等待美術審閱，不是人物定稿。**

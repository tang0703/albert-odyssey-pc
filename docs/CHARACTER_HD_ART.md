# MAP001 玩家高清動畫：機械整理與審閱契約

`tools/character_hd_art.py` 整理已經繪出的動作，不能生成姿勢。52 幀由四方向各 12 張行走、1 張待機構成。待機可以沿用該方向已核准打樣，另外 12 張必須實際繪製；複製、平移或鏡射同圖不算新姿勢。

## 輸入與來源

輸入 JSON 的 schema 為 `ao_character_hd_art_input_v1`，角色固定 `map001_player`。所有圖片須為真正 RGBA PNG，不接受把棋盤格畫入圖片當透明底。每個來源檔提供絕對 `path` 及 `sha256`；讀取及處理完成後再次核對，保留檔名與雜湊，不把原始參考圖搬入成品。

頂層必要欄位：

- `source_character_manifest_sha256`、`scene_manifest_sha256`：對應已驗證原版角色及場景資料包。
- `draft_approval`：`approved: true`、`evidence`、四方向 `references`，以及 `approval_record: {path, sha256}`。此欄固定已通過 A3 的四张造型，並不代表 52 幀已通過審閱。
- `normalization.maximum_alpha_height`：64–416，建議 400。
- `normalization.display_scale_by_direction`：四方向各自明寫的世界座標／高清像素比例。必須由原版比例與遊戲內預覽確認，工具不猜測。
- `normalization.actor_anchor_by_direction`：四方向在 512 畫布中的原作角色定位點。不能直接把鞋底視為原作座標原點。
- `directions`：`down`、`left`、`right`、`up`，各一份完整來源描述。

每方向可選以下一種來源：

```json
{
  "kind": "frames",
  "files": {
    "walk-00": {"path": "G:/.../walk-00.png", "sha256": "實際 SHA256"},
    "walk-01": {"path": "G:/.../walk-01.png", "sha256": "實際 SHA256"},
    "idle": {"path": "G:/.../approved-left.png", "sha256": "實際 SHA256"}
  },
  "anchors": [
    {"point": [625, 1110], "confirmed": true, "evidence": "逐幀目視確認的原圖鞋底地面點"}
  ]
}
```

上例省略 `walk-02..11` 及其餘 12 筆 anchors；實際使用必須完整提供。圖片可以不是 512×512，方向內 13 張共用相同比例縮放。明列 anchors 時，點座標以該張輸入圖片／該格局部座標為準，必須附 `confirmed: true` 與審閱說明。

另一種來源為 `{kind:"sheet", path, sha256, anchors?}`。圖集必須正好能以整數尺寸等分 4×4，cell 0..11 是 walk-00..11，cell 12 是 idle，cell 13..15 全透明。1254×1254 不能等分，會拒絕；不擅自推測不規則格線。

未提供 anchors 時，工具用主 alpha 連通分量最底支持點中心提出候選，標為 `mechanical_bottom_support_estimate`、`anchor_confirmed: false`。這只是幾何估算，不是已辨識出腳部；正式成品必須另有逐幀錨點審閱。

## 機械處理界線

工具以非零 alpha 的 8 連通分量分析完整角色。空格、格邊非透明內容、另一塊顯著獨立圖形均拒絕；不裁掉頭髮、鞋、衣角來使資料合格。預設保留所有小型分離細節，也不刪除雜點。

本輪透明邊緣修整可顯式加入 `normalization.alpha_cleanup={"min_alpha":16,"min_component_pixels":16}`。這只把低於 16 的非零 alpha、以及小於 16 像素的分离 alpha 分量設為零，其他有效 RGB／alpha 不變；原始 PNG 不改。閾值上限均為 16，不接受借此刪掉大片衣物、武器或另一個人物。每幀記錄清理前後 bbox、兩類去除像素數及參數，並額外輸出 `cleaned-sources/` 的 52 張原尺寸清理稿供人工核對。仍存在的大分量、跨格及裁切繼續拒絕。開啟清理不代表邊缘已經通過美術審閱。

每方向以最高姿勢計算同一縮放比例；其他幀不能逐張拉長或縮小。LANCZOS 僅執行機械縮放。畫布為 512×512，**美術地面點 `ground_anchor=[256,448]`**，最少保留 8 像素透明外邊距；裁切風險直接拒絕。

`actor_anchor` 是原作演出定位，`ground_anchor` 是美術地面點，兩者分開保存。`anchor` 僅為 `actor_anchor` 的同值相容欄位。兩者之差及 `display_scale` 必須由原版資料和實際畫面確認。

精確相同的圖片即使改了透明區 RGB、邊距、平移、鏡射或 90 度旋轉仍會判為重複。任意仿射變換、重上色或近似重複無法靠這個檢查完整辨識；不能把自動檢查通過寫成「52 幀美術完成」。

## 12 幀／40 更新週期

一個來源主姿勢維持 10 次更新，共四個主姿勢。每組三張：原主姿勢、新繪 1/3 過渡、新繪 2/3 過渡；最後一組過渡接回主姿勢 0。

實際演出索引：`primary*3 + floor((timer+render_phase)*3/10)`；`timer` 為 0..9，`render_phase` 在 `[0,1)`。因此小幀邊界在 3⅓、6⅔，並非等到整數第 4 或第 7 更新才切換。僅當 `render_phase=0` 的整數更新採樣，數量才是 `[4,3,3]`。

各 walk frame 保存 `phase_interval_numerators=[10*i,10*(i+1)]`，共同分母 3；全部覆蓋 `[0,40)`。`primary_source_index=i//3`，過渡記錄下一個主姿勢索引及 1/3 或 2/3。這些時間值只驅動演出，不改移動或事件更新頻率。

## 輸出、閉包與審閱

```powershell
..\tools\pc-remake\python\Scripts\python.exe tools/character_hd_art.py prepare `
  --spec reports/character/hd-production-v1/input.json `
  --out reports/character/hd-production-v1/prepared

..\tools\pc-remake\python\Scripts\python.exe tools/character_hd_art.py verify `
  reports/character/hd-production-v1/prepared
```

輸出 schema `ao_character_hd_art_v1`，狀態先為 `review_status:"pending"`：

- `frames/`：52 張 512×512 RGBA；每幀記錄穩定 ID、方向、primary/transition/idle、來源主姿勢、相位、腳底／角色原點、來源檔及分格座標、PNG 與 RGBA 雜湊。
- `atlases/`：四張 2048×2048 RGBA，walk 0..11、idle 12、最後三格透明。驗證逐像素與 52 張單圖相同。
- `previews/`：四向 contact PNG 與四個行走 GIF。GIF 有灰底、時間受格式限制而取整，僅供看動作，不作執行期或精確時間證據。
- `manifest.json`：64 個 payload 的完整閉包，啟用 alpha 清理時再加 52 張 `cleaned-sources/` 原尺寸審閱圖，以及來源及核准打樣雜湊。未列出的額外檔案、缺檔、來源變更、PNG 截斷、圖集重排會拒絕。A5 執行期包只選 normalized 52 幀及 4 張 atlas。

審閱記錄 schema `ao_character_hd_art_review_v1` 必须绑定 prepared `manifest.json` 的實際 SHA256，完整列出 52 個 frame ID，以及：

```json
{
  "schema": "ao_character_hd_art_review_v1",
  "manifest_sha256": "prepared manifest 的實際 SHA256",
  "approved": true,
  "reviewer": "實際審閱者",
  "notes": "逐幀、循環動畫及遊戲內比例的實際檢查結果",
  "frames": ["全部 52 個穩定 frame ID"],
  "checks": {
    "consistent_identity": true,
    "distinct_drawn_poses": true,
    "complete_silhouette": true,
    "feet_and_anchor": true,
    "limb_and_weapon_consistency": true,
    "loop_continuity": true
  }
}
```

未完成的檢查不能填 true。工具不代替審閱者判斷、也不自動產生批准記錄。

```powershell
..\tools\pc-remake\python\Scripts\python.exe tools/character_hd_art.py finalize `
  --prepared reports/character/hd-production-v1/prepared `
  --review reports/character/hd-production-v1/review.json `
  --out reports/character/hd-production-v1/approved

..\tools\pc-remake\python\Scripts\python.exe tools/character_hd_art.py verify `
  reports/character/hd-production-v1/approved --require-review
```

finalize 不改已封存的候選包，在新目錄建立批准版，保留 prepared manifest 雜湊及完整審閱記錄。A5 建置必須鎖批准 manifest 的雜湊，且要求 `review_status:"approved"`。原作參考圖仍留本地；經審閱的高清成品才可按既有 Git LFS 規則納入版本控制。

合成測試：`python -m unittest discover -s tests -p test_character_hd_art.py -v`。測試涵蓋透明分量、裁切／多圖拒絕、精確重複、週期邊界、52 幀及圖集閉包、來源改檔、未審閱拒絕與批准記錄綁定，不使用原作素材。

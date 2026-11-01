# 頭臉與髮型：本地多視角幾何小樣

日期：2026-11-01。接續 `dcc8eac`，使用者指示「依建議方式再精修」。範圍是先驗證頭部造型；C2 尚未核准，不進入最終蒙皮、動畫或整身製作。

## 已執行

- 建立隔離 Python 3.11.9／PyTorch 2.5.1+cu124 環境，鎖定 Hunyuan3D-2 原始碼 `f8db63096c8282cb27354314d896feba5ba6ff8a` 與 2mv 權重 `3a761b539b29fe4ff64714813aa9560fd66f5de0`。
- 從已核准 `art/enhanced25d/v1/approval.json` 的四張透明圖裁出頭部；原始參考不重畫、不上傳，裁切及縮放座標另存。插畫不是校準的多相機掃描。
- 本地生成四視角與官方三視角組合兩個頭部網格。三視角的另一側與羽飾不穩定，保留四視角結果作修整基底；兩個原始結果均保存。
- Blender 清除游離碎片、修補細孔及表面噪點，局部收整嘴部。主要審閱選用 `refined-02` 灰模；重複羽飾尚未解決。後續 `refined-04` 分件替換羽飾造成側面局部表面失真，**未採用**；其檔案與實際 Unity 畫面均保留，未覆寫較完整的前版。
- 新增獨立 Unity URP 靜態審閱程式，完全不建立遊戲 session。舊 v2 與新頭部使用同一鏡頭、灰模／基本材質、中性／暖光及五個角度。
- 基本材質只作常數色分區。自動分色及後續區域分色仍有明顯錯位，**未通過材質審閱，不採用於遊戲**；主審閱預設灰模，配色僅作失敗診斷紀錄。

## 本地審閱與可編輯來源

- `art/local/hunyuan-head-v1/review-02/review.html`：嵌入圖片，可離線查看；預設灰模，包含概念、舊 v2 與實際 Unity 畫面。
- `art/local/hunyuan-head-v1/refined-02/head-refined.blend`：選用的可編輯灰模、隱藏原始網格及舊版比較物件；材質仍是失敗試作。
- `art/local/hunyuan-head-v1/refined-02/head-palette.fbx`：靜態頭部幾何；不是遊戲用最終拓樸或材質。
- `art/local/hunyuan-head-v1/run-04`：四視角原始幾何；`run-05`：三視角對照。
- `reports/unity/hunyuan-head-run-*.log`、`hunyuan-head-refine-*.log`、`headpilot-*.log`：包含失敗與中間結果，未用成功重試覆蓋。

以上均留本地。Hunyuan3D-2 模型使用 Tencent 社群授權，含地域等條件，不視為無限制 MIT 素材；新網格及其衍生審閱圖未納入公開 GitHub。工具與授權副本另存於本地證據包。[官方模型與授權](https://huggingface.co/tencent/Hunyuan3D-2mv/tree/main)

## 載入問題與處理

首次官方整檔載入遇到 Windows `1455`（commit／分頁檔限制）。即使約有 11 GiB 實體記憶體可用，當時可用 commit 約 5.2 GiB，不代表可再配置完整模型與中間副本。沒有修改系統分頁檔、登錄檔或全域 PATH，也沒有關閉使用者程式。

改成逐張量讀取仍會在同時保留全部模型時耗盡可用 commit。最終使用分階段載入 conditioner → model → VAE，每階段釋放不再使用的權重；保留官方推論迴圈、排程器與幾何解碼。Safetensors 仍由官方解碼器解析，完整檔案先比對官方 LFS SHA256，每個必要鍵與形狀均檢查。只移除官方權重本來未提供、推論不會呼叫的 VAE 訓練用 encoder／pre_kl；沒有隨機補權重、量化或變更模型來源。

第一次串流驗證因未排除上述訓練用欄位而拒絕，後一次同時載入因記憶體不足失敗；這些紀錄仍保留。分階段生成四／三視角兩次成功。生成耗時與工具的進度列不是遊戲效能驗收。

## 審閱界線

主要判斷：臉頰／下巴體積、耳朵銜接、瀏海走向、髮束輪廓及羽飾側別是否更接近概念。

仍需修整：眉眼神情、嘴角、髮根及側後髮束銜接、羽飾根部、基本色區邊界。局部收整不能宣稱所有重建瑕疵已消失。頭部展示框等高，但包含的頸部／圍巾不同，不宣稱精確頭身比例已通過。近景採一致無投影燈光以觀察輪廓，不代表原房間 45° 暖光整身已驗收。

沒有製作最終拓樸、UV 材質、骨架、動畫或服裝精修；沒有替換遊戲人物或改動 1.125 Unity 身高、遊戲規則與來源資料。沒有執行負載、長循環、效能基準或 GPU FPS 測試。舊九項快照缺失、七項效能相依限制保持原狀，本輪不以靜態美術檢查代替它們。

## 重跑入口

1. `tools/hunyuan_headpilot_inputs.py`（只允許新輸出，核准來源必須一致）。
2. 隔離 Python 執行 `tools/hunyuan_headpilot_generate.py --stream-weights --output art/local/新的路徑`。
3. Blender 執行 `tools/hunyuan_headpilot_blender.py` 與 `tools/hunyuan_headpilot_refine.py`；各輸出目錄必須新建。
4. `tools/unity_headpilot_review.ps1 -Action build`，再 `-Action capture`。
5. `tools/hunyuan_headpilot_review_page.py --capture <實際截圖目錄> --out <新目錄>` 產生嵌圖審閱頁；已有審閱不覆寫。

目前狀態：**本地多視角建模流程與頭部小樣已實作；初始輪廓可作比較，但精修及材質未達定稿，C2 未通過。** 下一步需針對羽飾／髮根做具部位拓樸的修形，眼睛與分色需正式 UV／獨立材質，不能繼續以大範圍座標遮罩替代。整身人物、動畫及效能均未驗收。

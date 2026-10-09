# 第二輪角色造型打樣 v1

狀態：S2 造型已於 2026-10-09 經使用者審閱採用；這兩張仍是靜態概念圖，32 幀動畫另外製作。原始輸出保留透明背景。

| 角色 | 圖檔 | 原圖朝向 | 遊戲朝向 | 比例預覽 |
|---|---|---|---|---|
| 派克 | `pike-concept-v1.png` | 左 | 我方朝右，顯示時水平翻轉 | 圖片縮放 0.175，腳底約 y=0.902 |
| WEREDOG | `weredog-concept-v1.png` | 右 | 敵方朝左，顯示時水平翻轉 | 圖片縮放 0.155，腳底約 y=0.902 |

圖片由 imagegen 依本地原作截圖重繪，2026-10-09 產生。兩圖都是 1280 × 1280 RGBA 概念稿；S3 才製成統一 512 × 512 動畫畫布。這是外觀重繪，並非原作動畫影格解碼。遊戲技能、ID、數值不隨概念圖變更。

## 外觀核對

- 派克：淺褐色上揚頭髮、綠頭帶及兩個淡色側飾、紅圍巾／披風、深藍上衣、淺灰褲、橄欖金色手套與靴子、銀色直劍、金邊藍紫盾牌。
- WEREDOG：棕色犬人、尖耳、短吻、白眼、露齒、彎曲蓬鬆尾巴、深藍上衣與淺藍肩部、深青綠褲、裸露拳頭和腳；沒有手持武器。
- 原作低解析圖無法確認派克側飾的實際材質、衣服細縫及 WEREDOG 爪部細節。重繪中的線條、毛髮與高光屬視覺詮釋，不視為已確認的原作設定。
- 原作畫面中的白劍／紅色選取標記是 UI，未納入 WEREDOG 造型。

## 本地來源證據

參考圖不納入 Git 或 Windows 套件。以下路徑相對 `G:/codex/SS`，SHA256 用於追溯。

| 用途 | 路徑 | SHA256 |
|---|---|---|
| 派克完整姿勢及敵人配色 | `work/analysis/gameplay-balance/runtime/20260830_multi_random_04/enemy_weredog_2_pit_viper_1.png` | `68d48919767d96f6212e3cc94b6f4f2878c49f45b4363297886dd83904ef789c` |
| WEREDOG 單隻身份 | `work/analysis/gameplay-balance/runtime/20260830_weredog_01/enemy_weredog_1.png` | `9829e641f34af3fde38e5b01ca913068df06878f3c7093ca082db31f387bb045` |
| PIKE 姓名 | `work/analysis/gameplay-balance/runtime/20260830_reward_delta_02/status_before.png` | `25ba57e7dac2a7348e36db82487c2a8ac6affabdc694c7e9dcecaa734f5730af` |

## 比例預覽重跑

以 Godot 執行 `tools/preview_battle_concepts.gd`，載入正式戰鬥介面後只顯示靜態概念圖。預覽不提交戰鬥行動，也不改寫 `appearances.json`。輸出在 `reports/character-reference/concepts-in-game.png`。

S3 入口：先審閱這兩張造型，再製作每角待機 4、攻擊 6、受傷 2、倒下 4 幀；不得把這兩張靜態圖重複複製當作已完成的動畫。

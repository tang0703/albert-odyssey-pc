# 2.5D 美術來源與可編輯資料

採用使用者在 V2 核准的四方向造型及 36 世界單位人物高度。核准紀錄：`art/enhanced25d/v1/approval.json`，問題識別 `call_d89379a816f1404b85fe82731b038a43`。

新點陣素材由內建 imagegen 生成，沒有使用外部 API／CLI。每次選用的原始輸出與提示詞保存在 `drafts/` 及 `animation-sources/`；角色 52 張透明 PNG、四張 2048×2048 圖集、四份循環 GIF 與逐幀總覽保存在 `animation-candidate-03/`。

`tools/prepare_enhanced25d_animation.py` 只擷取完整輪廓、清理極低透明度雜點、等比縮放、對位及組圖，不生成肢體或用複製／鏡射補足幀數。生成圖的四格間距不完全固定，依分離輪廓擷取，避免裁掉鞋底。每幀保留原始檔雜湊、擷取範圍、比例與步序。

首輪候選的生成尺寸與步序未通過檢視，保留在本地 `art/local/enhanced25d-rejected/`。第二輪頭寬校準造成尺寸不一致，亦排除。第三輪以完整人物等比校準至相同高度，保留原稿、沒有扭曲個別肢體。這是逐幀重繪的視覺詮釋，不是原作動畫影格復原或 3D 骨架動畫；細部材質仍可能有輕微逐幀差異。

背景與家具皆為獨立 PNG，`layout.json` 保存世界座標、圖層與校準網格；`review-project/` 和 `exploration-demo/enhanced25d_renderer.gd` 是可編輯的 Godot 分層來源。沒有偽稱提供不存在的 3D 模型或 Krita 工程。

桌面瓶罐與 Cirrus 分開識別。Cirrus 的來源槽 6、常態影格 46 使用獨立新劍身圖；特殊姿勢及效果沿用來源包。新陰影不代表原作影子已還原。美術不能改動碰撞、物件持有狀態、裝備或劇情結果。

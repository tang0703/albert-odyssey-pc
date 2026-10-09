# A3：MAP001 玩家四方向高清造型核准

日期：2026-10-09。A1 為 `f00877c`，A2 為 `5133889`。

使用者已審閱四方向造型、原作對照及固定鏡頭遊戲內比例，明確回答：
「採用目前四方向造型，製作 52 幀」。此核准只針對本次 MAP001 玩家造型，
不是沿用舊戰鬥 demo 的派克／WEREDOG 核准。

## 核准素材與來源

四張核准稿位於 `art/characters/map001-player/design-v1/`，以 Git LFS 保存。
全部由內建 imagegen 生成，RGBA、1254×1254；這是造型基準，尚不是 A4 的
512×512 正式動畫影格。原始參照圖留在 `reports/character/reference-art/`。

|方向|檔案|SHA256|
|---|---|---|
|正面／下|down.png|69f0b62b922970de1ed6858d5bb02a97155ea2bc58d580da8b9b783151ab8c32|
|左|left.png|0a8b2a8ba87d308e0d7a6eaa7e01a8f7dce7e6294574badc0c6eca4642ace2d5|
|右|right.png|e50459c5657b069f85ca074c7da20efd3c274284f9c98243b49fb13031a46b3c|
|背面／上|up.png|0d9808ae52ad55b1c5dfa1a2c78f0433d2ecb3141a43898f7ddc34890fdd3373|

完整生成提示保存在本地 `reports/character/art-review-v1/prompts.json`。
審閱板為同目錄 `review-board.png`，SHA256
`e9baf2d1ee841cc7af644a784c1efbb0e08f45484722a7b90e678ab2e001ab2e`。
它含來源圖像，因此留在本地。`review-board.json` 記錄圖片雜湊、比例、透明範圍、
來源包與預覽程式身份。四方向預覽同處於來源起點 `(718,1626)`，沒有修改遊戲座標。

目前能確認的辨識特徵包含大幅掃向一側的棕金色頭髮、綠色頭帶、兩片淺色後飾、
紅色短上衣、淺色袖子及黃褐色褲靴。綠色眼睛、服裝接縫與飾片材質是高清詮釋，
已在核准問題中向使用者明列。角色姓名仍未取得來源證據。

## 比例與後續製作

預覽使用 alpha≥128 的主要輪廓，濾除極少數邊緣雜點；四張主要輪廓都沒有觸及畫布邊界。
原作與背景採最近鄰；高清草稿採線性取樣。預覽高度為 36／36／36／37 個原作世界像素，
以底部 8% 的像素估算腳底與 actor 錨點關係。這是審閱定位方式，正式逐幀錨點仍需 A4 人工核對。

A4 接著製作 16 個主要行走姿勢、32 個過渡姿勢及四個待機姿勢，輸出 52 張
512×512 透明 PNG 與四張 2048×2048 圖集。原作每姿勢 10 更新、整輪 40 更新不变；
高清每段以精確相位分成三份。未完成全部影格、循環檢查及資料包驗證前，不提供高清模式的替代素材。

重跑審閱板（實際 GPU，不能用 headless）：

```powershell
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe `
  --path exploration-demo --script res://character_art_review.gd -- `
  --art-dir=G:/codex/SS/pc-remake/art/characters/map001-player/design-v1 `
  --output=G:/codex/SS/pc-remake/reports/character/art-review-v1/review-board-rerun.png `
  --report=G:/codex/SS/pc-remake/reports/character/art-review-v1/review-board-rerun.json
```

缺圖或 headless 執行會拒絕。審閱工具不修改輸入圖像、不推進移動、不代表正式動畫、
4K 效能或 Windows ZIP 已驗收。原作影子及裝飾物 6／7 仍沿用 A2 的範圍限制。

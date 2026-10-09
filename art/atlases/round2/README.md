# 第二輪動畫來源圖集

兩張透明來源圖集由 imagegen 以使用者核准的概念圖為參考製作。首次圖集部分武器／尾巴太接近格線，另外使用 imagegen 修正留白後採用此版本。

- `pike-atlas.png`：派克，原生朝左。
- `weredog-atlas.png`：WEREDOG，原生朝右。
- 實際來源尺寸均為 1254×1254；每張 4 欄 × 4 列。
- 依逐列順序：待機 4、攻擊 6、受傷 2、倒下 4。

工程輸出使用 `tools/build_battle_art.gd`：整張按固定比例正規化至 1280×1280，切成 320×320 格，再以相同 1.6 倍倍率放入 512×512 RGBA 畫布。沒有逐幀變焦；僅垂直平移，使 alpha>0.5 的下緣落在 y448。腳底錨點為 `[0.5,0.875]`。

因此每幀 512×512 是交付画布尺寸，並非每幀都由模型原生輸出 512 像素細節。這不影響 4K 畫面輸出。動作是新繪詮釋，不還原原作逐幀姿勢。

原圖 alpha 1–2/255 的少量邊緣 RGB 雜點在某些透明圖檢視器會呈現鮮豔色；應以正常 alpha 合成的 Godot 畫面驗收。不得只看原始 RGB 就刪除角色線條。原始圖集與切片均保留完整可追溯來源。

在 `pc-remake` 下重跑：

```powershell
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tools/build_battle_art.gd -- --write-config
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tools/preview_battle_animations.gd
```

`reports/battle-art-assembly.json` 記錄每幀來源矩形、腳底平移、透明邊界與 SHA256；`battle-demo/data/asset-manifest.json` 記錄所有可進入套件的影格。原作參考截圖留在本地，不打包。

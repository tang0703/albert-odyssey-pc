# R2：碰撞擴域與鏡頭模型

2026-10-09；R1 基準提交 `6ba3578`。R2 核心比較通過，畫面與交付另由 R3–R5 驗收。

新增 `room_camera_core.gd` 與 `room_movement_core.gd`，不依賴節點、動畫時間或 FPS。
沿用既有整數移動核心；查表允許範圍由 R1 通過的 613 格實際聯集產生。
遇到來源階梯事件矩形，完整保留輸入狀態並回報 `test_boundary`，不當成原作牆壁。
鏡頭依原作的跟隨門檻、最大位移、夾限、顯示欄位複製與圖層順序計算。

`build_room_reference.py` 重新驗證五條基準來源捕捉，僅在結果與 R1 相同時輸出共用 fixture。
Godot 從各路線的唯一初始狀態及輸入連續推演，不回填後續角色或鏡頭狀態。

- 5,061 次角色更新、5,057 次完整鏡頭更新，兩層鏡頭的原始位置、顯示欄位及位移全部零差異。
- 30,383 項核心檢查通過，包含事件边界整次拒絕、鏡頭設定／來源變更拒絕、未知位移拒絕、
  設定失敗後使舊設定失效及重設起點。
- JSON 數字逐欄驗證為整數後轉換；沒有以放寬數值比較處理資料型別差異。
- Python 鏡頭／邊界 6 項及既有移動 8 項回歸通過。

本地來源 fixture：`reports/room/reference.json`，SHA256
`a2fade02e6f80c0acf60fdf331983faa85b05750d0c0d5f693b6f6c0d90b0d0a`。
Godot 報告：`reports/room/r2-godot.json`。R1 捕捉尾端四次未完成鏡頭仍明列，未補造完成樣本。

```powershell
& ../tools/pc-remake/python/Scripts/python.exe tools/build_room_reference.py reports/room/r1-survey.json --out reports/room/reference.json
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe --headless --path exploration-demo --script res://tests/test_room_core.gd -- --fixtures=G:/codex/SS/pc-remake/reports/room/reference.json --flags=G:/codex/SS/pc-remake/exploration-demo/generated/scene/flags.bin --report=G:/codex/SS/pc-remake/reports/room/r2-godot.json
```

下一步 R3：建立捲動背景／前景資源，驗證實際顯示延遲、非圖塊對齊投影、家具排序及省略物件影響。
既有三個資料包、52 幀高清素材及核准紀錄保持不變。

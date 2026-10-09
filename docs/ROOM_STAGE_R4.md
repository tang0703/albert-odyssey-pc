# R4：獨立室內入口與演出整合

2026-10-09。第四個本地資料包已建立，21 個核准檔案（19 張圖片、場景資料與清單）。
清單 SHA256：`4f5871775e4ff5de364cb78ed6aab695bcca5e60b57be4977d01270c7ed3e8d2`。
綁定既有三包雜湊，未修改原包、高清圖片或核准紀錄。

室內入口 `exploration-demo/room_main.tscn` 使用來源整數鏡頭、613 格移動範圍、
原作事件測試邊界、兩個新增裝飾物及同步 3 更新演出佇列。所有圖像開場預載。
完整動作先驗證，再一次提交移動／動畫／鏡頭／裝飾物及顯示狀態。

## 實測

- Godot 無畫面整合 61,061 項檢查通過；三外觀共 15,183 次來源更新零差異。
- 五條路線均經正式 UI 更新流程完成，包含原作鏡頭與動畫比較；未直接回填後續狀態。
- 獨立物件 CPU 捕捉逐次核對 Godot 裝飾物狀態。
- 暫停／恢復、多方向、單步、重設、失焦清鍵、出口整次保留及缺圖原子拒絕通過。
- 30／60／120 FPS 時間分割的核心、鏡頭、裝飾物和佇列結果一致。
- 真實 RTX 4070 Ti SUPER／Compatibility GPU，32 個代表視窗的非影子像素零差異。
  比較對象直接取自原作 video，不使用 PC 重繪畫面當期望值；含非圖塊對齊與家具遮擋。

GPU 測試呼叫實際室內入口、自然重播至指定更新，再讀取其 320×224 畫布。
三解析度畫面、Windows 封装、600 秒獨立長測及完整回歸仍由 R5 驗收。

```powershell
& ../tools/pc-remake/python/Scripts/python.exe tools/room_bundle.py build
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe --headless --path exploration-demo --script res://tests/test_room_ui.gd -- --report=G:/codex/SS/pc-remake/reports/room/r4-ui.json
& ../tools/pc-remake/godot-4.7.2/Godot_v4.7.2-stable_win64_console.exe --path exploration-demo --script res://tests/test_room_gpu.gd -- --fixtures=G:/codex/SS/pc-remake/reports/room/gpu-fixtures/fixtures.json --report=G:/codex/SS/pc-remake/reports/room/r4-gpu.json
```

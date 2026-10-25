# MAP001 互動核心與第六資料包

2026-10-25。P2 通過；可操作介面、實際演出、GPU 與交付仍待 P3–P5。

`interaction_core.gd` 是獨立 RefCounted 核心，沿用整數移動／鏡頭計算，
接收按鍵、新按下遮罩及文字／音訊裝置回應。85 條具名 PC 指令不執行任意 Saturn 位元組。
舊 `event_core.gd` 與五個資料包未修改。

- Python 與獨立 GDScript 均通過 13 條來源路線、7,970 次完整更新。
- Godot 核對 175,340 個完整狀態值，零差異，並驗證每條路線完整重設。
- 指令、初始狀態、互動矩形、額外動畫與來源證據整體綁定；改變指令、操作數、影格時長均拒絕。
- 新載入器預載 16 張新增來源圖片與舊事件的 6 張圖片，兩段音效均在互動前解碼。
- 第六包包含 32 個核准檔案，綁定五個父包。檔案缺失、雜湊變更、額外檔案及父包變更均拒絕。
- 新互動 Python 測試 10 項通過；既有事件 Python 測試 24 項通過。這些數字不代替後續完整回歸或 UI 驗收。

本地資料包為 `exploration-demo/generated/interaction`，manifest SHA256：
`365489c2f1c59410f26babb2e461c3dd2d25fb597d65306c4788aca01ff6a71e`。
資料包、參照輸入／預期狀態與來源圖像留在本地；Git 只保存程式、核准識別與文件。

## 重跑

1. `tools/build_interaction_reference.py`
2. `tools/verify_interaction_pc.py`
3. Godot headless：`res://tests/test_interaction_core.gd`
4. `tools/interaction_bundle.py verify`
5. Python unittest：`test_interaction*.py`

P3 使用獨立入口；拾取時呈現來源像素姿勢，完成後恢復原本選定的行走外觀。
確認鍵必須新按下，開啟事件的按鍵不能同時翻頁。實際 Windows 效能估算仍需以整合後的
完整「探索—互動—樓梯提醒—重設」循環量測；不沿用事件舊版長測。

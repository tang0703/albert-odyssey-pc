# Cirrus 事件核心與第五資料包

2026-10-15，D2 通過。

具名 PC 指令的 Python 參照與獨立 GDScript 核心均完成六條來源路線、6,679 次更新。GDScript 比較 113,543 個狀態區塊，逐區塊包含角色原始紀錄、鏡頭、裝飾物、表情、控制旗標、腳本位置及輸出請求，零差異。後續來源狀態只供比較，不回填核心。

第五個本地事件資料包綁定既有場景、角色、高清及室內包雜湊；包含已轉換指令、鎖定譯文、必要表情與 Cirrus 來源圖像、無損音訊及六條參照。原四包不變。載入前核對精確清單、內容雜湊、圖像尺寸及音訊規格，預載所有必要資源。未知指令、缺檔、變更與額外資源拒絕接受。

來源比較使用明列的原作文字／音訊裝置回應。這項結果驗證事件排程與世界規則，不表示 PC 整頁對話、實際音訊播放、演出時序或效能已通過。這些為 D3／D4 工作。

重跑：

- `tools/verify_event_pc.py`
- Godot `res://tests/test_event_core.gd`
- `tools/event_bundle.py verify`
- Python `unittest discover -s tests -p test_event*.py`：17 項通過。

本地報告：`reports/event/d2-python.json`、`reports/event/d2-godot.json`。本階段尚未產生事件版 Windows ZIP。

# 戰鬥 Demo 第二輪 — 角色重繪與演出

日期：2026-10-09。起始版本：`f850a0f5e7c3d045ba24870bee7610a97d89a860`。

## 範圍與里程碑

維持原有三對三新規則、角色 ID、數值與技能。派克外觀對應 guardian、WEREDOG 對應 scout，其餘四名保留簡易角色。原作 Stage B 沒有因此通過。

| 階段 | 狀態與證據 |
|---|---|
| S1 基準與演出 | 預載、動畫狀態／朝向／完成訊號、單一演出時鐘已實作；冷啟動、截圖與暖機後計量分開。原作來源回歸有下述缺口。 |
| S2 造型打樣 | 兩張透明概念稿與正式 UI 比例預覽完成；使用者已選擇「採用目前造型，繼續製作動畫」。 |
| S3 動畫 | 製作中；目標每角待機 4、攻擊 6、受傷 2、倒下 4 幀。 |
| S4 整合 | 演出與素材清單介面完成，待正式 32 幀整合驗證。 |
| S5 畫面／效能 | 尚待新素材三解析度與 600 秒 4K 實測，不沿用第一輪效能數據。 |
| S6 交付 | 尚待新版匯出、ZIP 驗證與最終 Git 同步。 |

## S1 驗證與回歸缺口

戰鬥核心原有 173 項斷言通過。新增動畫元件 39 項、計量器 20 項、封裝 7 項、QA 門檻 10 項檢查通過。演出 UI 初步 390 項通過，包含實際完成訊號、按住 Enter、命中後暫停、勝敗與再戰；整合素材後重跑。

2026-10-09 全 Python 回歸共 62 項：53 通過、9 個錯誤。錯誤均因既有原作來源存檔與鎖定 SHA256 不同；戰鬥 Demo 不讀取此檔。未改寫鎖定值或跳過檢查。原專案 Godot runtime 14 項與 workbench 9 項另行執行，全部通過。

- 預期來源：`work/ymir/dialogue-trace/savestates/D8562E1863DD5A2595CBE2D3A50EDFA4/0.savestate`（相對 SS）。
- 預期 SHA256：`615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab`。
- 目前 SHA256：`233be2069ce0005b42374e37a5e77c3470fbe10f0fa2bcb5848775cddbf7eb2c`。
- 本地另一份 `0-1.savestate` 也不符合；兩檔修改時間為 2026-09-12。需要原備份才可重現全部原作來源回歸。
- 記錄：`reports/round2-python-regression.log`、`round2-runtime.log`、`round2-workbench.log`。

最初另有暫存目錄存取問題；將 TEMP／TMP 以程序環境指向 `reports/tmp` 後已消除。APPDATA 也只在測試程序指向 `reports/appdata`，沒有修改全域 PATH、登錄檔或使用者設定。

## 動畫與演出契約

`fighter.configure()` 在開始前驗證並載入所有必要動作。每動作使用 `frames`、`durations`、`loop`，攻擊另有零起算 `hit_frame`。角色保存正規化 `anchor`、`scale`、`default_facing`。缺圖、空動作、錯誤時長與命中點會禁止開始，不改用簡易人物掩蓋。

核心只結算一次。UI 保存獨立顯示快照，在命中點顯示 HP／MP、飄字與音效，再等候受傷／倒下完成才解鎖。倒下保留末格，待機循環；防禦及藥水使用待機與特效。普通攻擊及重擊共享攻擊動作，命中特效大小與色彩不同。

## 重跑入口

```powershell
$env:APPDATA = "$PWD/reports/appdata"
$env:TEMP = "$PWD/reports/tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.\tools\battle.ps1 -Action test
.\tests\test_battle_qa.ps1
.\tools\battle.ps1 -Action export
.\tools\battle_qa.ps1 -SkipSoak
.\tools\battle_qa.ps1 -SoakSeconds 600
```

效能程序暖機 15 秒後開始計量；計量期間不存截圖、不讀回 GPU 圖片、不並行其他驗證。記錄平均／P95／最高影格時間與超過 50 ms 時點、每秒程序記憶體及每 10 秒 Godot 節點／靜態記憶體／渲染器顯存。Godot 顯存計數不是整張 GPU 的全部配置量。

ZIP 審核採核心資源與核准圖片 manifest 的 Godot import 閉包；來源 SHA256、匯入快取 MD5、封裝內容與實際解壓內容均需一致。BUILD-INFO 記錄來源 commit 及是否包含未提交修改。

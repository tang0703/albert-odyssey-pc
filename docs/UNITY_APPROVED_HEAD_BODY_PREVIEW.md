# 本地頭身拼接研究：已停止採用

使用者最初要求核准頭部的身體／服裝預覽，之後指定使用 Tripo，
最後明確要求「直接由 tripo 生成整體」。正式審閱改見
[完整 Tripo 人物](TRIPO_FULL_CHARACTER_REVIEW.md)。

本地 `art/local/tripo-head-v1/body-fit-01` 至 `03` 保留為未核准研究，
沒有交付 `review-body-fit-03/review.html`，也沒有替換遊戲人物。
`tools/unity_body_preview.py` 與 `tools/unity_body_validate.py` 保留其重現工具。

Tripo 身體接舊頭的 `art/local/tripo-body-v1/body-fit-01` 曾誤遮下巴與耳朵，
保留實際畫面及日誌。`body-fit-02` 縮小遮罩並調整位置，但因使用者改採完整人物，
未進一步建置或驗收。`tools/tripo_body_fit.py` 僅供重現此研究，不是正式交付路徑。

所有原核准頭部、概念與來源檔案保持原雜湊。研究沒有動畫或負載測試。

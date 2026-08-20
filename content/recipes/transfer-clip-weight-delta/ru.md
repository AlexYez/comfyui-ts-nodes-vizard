# Перенести разность весов CLIP на target

Фрагмент реализует `target + (tuned − base)` для common weights. Fine-tuned encoder подключается к `clip1` Subtract, его исходная база — к `clip2`; target входит в `clip1` Add и тем самым задаёт tokenizer и структуру результата.

`multiplier = 1` переносит полную разность. Для меньшего вклада меняйте multiplier в Subtract: он масштабирует всю дельту. Не ставьте ноль для bypass — common weights промежуточного delta-объекта будут обнулены.

В официальном пакете 0.1.42 такой топологии нет. Алгебра и порты проверены на exact-source probe, но полный fragment с реальными encoder не выполнялся.

# Поставить LTXV STG на блок 29 перед guider

Fragment применяет `LTXVSpatioTemporalGuidance` с default `scale = 1`, строкой блоков `29` и полным интервалом sampling. Изменённый `MODEL` передаётся в `LTXVDualCFGGuider`; positive и negative остаются внешними.

Схема собрана по исходнику. В workflow wheel 0.1.42 точных `LTXVSpatioTemporalGuidance` нет. Блок 29 — default runtime schema, а не доказанный лучший выбор для любой LTXV модели. Сверьте число transformer blocks у checkpoint.

При активном STG sampler делает дополнительный conditional pass. В выбранном блоке self-attention заменяется проходом value projection, а результат направляет основной prediction от perturbed prediction. `scale = 0` или строка без цифр отключают extra pass.

Model-free probe проверил разбор строки блоков, sigma-интервал, формулу callback и отсутствие extra pass в отключённых режимах. Настоящие веса и полный fragment не исполнялись; требуется человеческое утверждение.

## Источники

- [STG node callback](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L940-L991)
- [Value-passthrough attention branch](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/model.py#L464-L492)

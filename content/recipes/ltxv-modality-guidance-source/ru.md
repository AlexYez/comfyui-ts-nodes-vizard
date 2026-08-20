# Добавить cross-modal guidance перед LTXV Dual CFG

Fragment клонирует внешний LTXV-AV `MODEL`, добавляет к нему modality callback с `modality_scale = 3` на полном интервале sampling и передаёт изменённую модель в `LTXVDualCFGGuider` с раздельными шкалами `3` для video и `7` для audio.

Это source-derived схема. Полный wheel 0.1.42 не содержит `LTXVModalityGuidance`, поэтому fragment не заявлен как официальный workflow. Связка с dual CFG следует из описания и callback-контракта исходника; conditioning оставлено внешним.

После guider нужны совместимые noise, sampler, sigmas и nested AV latent в `SamplerCustomAdvanced`. Они не добавлены, чтобы fragment не подменял выбор модели, scheduler и формы данных.

Model-free probe выполнил callback внутри и вне заданного sigma-интервала, проверил оба отключённых cross-attention флага и отсутствие дополнительного прохода при `modality_scale = 1`. LTXV-AV веса и полный sampling не запускались; редактор ещё не утверждал рецепт вручную.

## Источники

- [Реализация modality guidance](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L994-L1050)
- [Реализация LTXV Dual CFG](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L1053-L1120)

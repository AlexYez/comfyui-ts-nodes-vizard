# Первый transformer-блок Qwen Image: 50/50

Подайте две совместимые Qwen Image-модели. Fragment выставит `transformer_blocks.0. = 0,5`; остальные группы останутся с default `1`, поэтому будут взяты из `model1`.

Сравнивайте с контрольным merge и исходной моделью на одинаковых prompt, reference inputs и seed. Это source-derived пример: exhaustive-поиск не нашёл прямого `ModelMergeQwenImage` в официальном пакете workflow 0.1.42. Полное исполнение с весами ещё не выполнялось.

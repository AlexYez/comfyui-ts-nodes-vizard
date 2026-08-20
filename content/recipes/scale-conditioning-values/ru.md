# Масштабирование CONDITIONING на 0,5

Подайте готовое conditioning на внешний вход. Нода умножит основной тензор и существующий `pooled_output` на 0,5, сохранив area, mask, strength и другие metadata.

Fragment не содержит sampler: его задача — изолировать числовое преобразование. Для оценки эффекта сравните исходную и масштабированную ветви при одинаковых model, seed и настройках sampling.

В 512 official workflow templates JSON 0.1.42 `ConditioningMultiply` не найден. Пример основан на runtime и исходнике, не исполнялся с реальным embedding и остаётся `in_review`.

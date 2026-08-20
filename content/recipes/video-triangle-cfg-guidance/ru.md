# Треугольный CFG перед KSampler

Подайте video `MODEL` в `VideoTriangleCFGGuidance` с `min_cfg = 1`, затем соедините patched MODEL с `KSampler`, где `cfg = 2,5`. На нечётном batch профиль идёт от 1 к 2,5 в центре и обратно к 1.

Это source-derived fragment: полный scan официальных workflow 0.1.42 не нашёл `VideoTriangleCFGGuidance`. Значения KSampler выбраны как контролируемый вариант формы SVD-примера для линейной соседней ноды, а не как найденный triangle preset.

Схема и exact-source формула проверены. Video model, conditioning и latent не включены; fragment не импортировался и не выполнялся.

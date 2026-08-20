# Epsilon Scaling: source-derived runtime default

Fragment добавляет exact runtime NodeId `Epsilon Scaling` со `scaling_factor = 1.005`. Сначала сравните его с тем же fragment при `1.0`: единица алгебраически сохраняет исходный denoised и помогает проверить неизменность остального графа.

Коэффициент выше единицы уменьшает `input − denoised`, коэффициент ниже единицы усиливает эту разность. Нода не делает дополнительный model call, но её место среди других post-CFG hooks влияет на результат.

Официальный wheel 0.1.42 не содержит Epsilon Scaling. Fragment восстановлен из exact source/runtime, не включает полный workflow и пока не проверен визуальным model run.

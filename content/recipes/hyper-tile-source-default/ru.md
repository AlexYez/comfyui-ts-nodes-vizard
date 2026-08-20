# HyperTile: source-derived runtime defaults

Fragment добавляет `HyperTile` с `tile_size = 256`, `swap_size = 2`, `max_depth = 0`, `scale_depth = false`. Сравните время, peak memory и изображение с полностью обойдённой нодой при одном seed.

`swap_size` выбирает tile count из делителей, но не сдвигает границы. При геометрии `64 × 64` и default tile size exact probe всегда выбрал `2 × 2`: два кандидата сводятся к первому из-за upper bound random index.

Official wheel 0.1.42 не содержит HyperTile. Fragment source-derived, не включает полный workflow и не подтверждён полноценным performance run.

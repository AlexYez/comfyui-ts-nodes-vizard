# FreeU_V2: source-derived runtime defaults

Fragment добавляет `FreeU_V2` с `b1 = 1.3`, `b2 = 1.4`, `s1 = 0.9`, `s2 = 0.2`. Сравнивайте его отдельно с обычным FreeU и baseline: последовательное подключение обоих patches зависит от порядка.

Spatial gain делит на разность максимума и минимума карты `h.mean(channel)`. На постоянной карте denominator равен нулю, и exact probe получил NaN. Нода также рассчитана на 4D features.

В official wheel 0.1.42 FreeU_V2 отсутствует. Fragment source-derived, не содержит полного workflow и не был исполнен с checkpoint.

# Perp-Neg перед SamplerCustomAdvanced

Подайте MODEL и три независимых CONDITIONING в `PerpNegGuider`: positive, negative и baseline от пустого prompt. При `cfg = 8` и `neg_scale = 1` GUIDER вычитает полную перпендикулярную часть negative-направления и передаётся в `SamplerCustomAdvanced`.

Это source-derived fragment. Официальный bundle 0.1.42 не содержит прямых `PerpNegGuider`, поэтому параметры — defaults закреплённого runtime, а не рекомендованный model preset. Empty conditioning нужно получить тем же encoder path, что и два других условия.

Fragment прошёл schema и source review, но не импортировался и не выполнялся. Перед реальным запуском проверьте finite output и сравните с обычным `CFGGuider` при одинаковых noise и sigmas.

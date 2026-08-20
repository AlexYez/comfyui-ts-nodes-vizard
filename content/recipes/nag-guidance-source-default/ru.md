# NAG: source-derived runtime defaults

Fragment вставляет `NAGuidance` с runtime defaults `nag_scale = 5.0`, `nag_alpha = 0.5`, `nag_tau = 1.5`. Подключите выход к guider, который передаёт и positive, и negative conditioning; при одной группе attention patch сразу возвращает исходный tensor.

Нода отключает CFG1 optimization. Учитывайте, что alpha=0 является тождественным только в обычной ветви без `img_slice`: exact-source probe подтвердил копирование positive image tokens в negative slice, когда `img_slice` присутствует.

В workflow wheel 0.1.42 NAG отсутствует. Fragment source-derived, не содержит модели и полного sampling path и не подтверждён запуском distilled/schnell-модели.

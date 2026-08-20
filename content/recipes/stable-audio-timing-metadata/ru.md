# Временные metadata для двух conditioning-ветвей

Подайте готовые positive и negative в одноимённые внешние входы. Нода запишет в каждую запись `seconds_start: 0.0` и `seconds_total: 47.0`, сохранив embedding и остальные metadata.

Fragment не содержит audio latent, model или sampler. Unit-level synthetic check подтвердил точные ключи, float-значения и копирование словарей; audio generation не выполнялась.

В official workflow templates JSON 0.1.42 runtime ID не найден. Пример основан на source/runtime-контракте и остаётся `in_review`.

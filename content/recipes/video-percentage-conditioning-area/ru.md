# Область video conditioning в долях latent

Fragment задаёт размер `(temporal, height, width) = (0.4, 0.6, 0.5)` и смещение `(z, y, x) = (0.1, 0.2, 0.25)`. В metadata попадёт tuple `("percentage", 0.4, 0.6, 0.5, 0.1, 0.2, 0.25)` и `strength: 0.9`.

Подайте conditioning от совместимой video-модели. Fragment не включает latent и sampler: фактические целые размеры зависят от temporal/spatial layout video latent и вычисляются перед sampling.

Runtime ID не найден в 512 official workflow templates JSON 0.1.42. Пример проверен структурно по runtime и исходнику, но не исполнялся и остаётся `in_review`.

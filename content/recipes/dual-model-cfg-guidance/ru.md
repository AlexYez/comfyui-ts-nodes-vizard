# Conditional и unconditional модели с CFG 7

Подключите основную MODEL к `model`, отдельную unconditional MODEL — к `model_negative`, затем positive и negative CONDITIONING. Fragment ставит cfg 7 и передаёт GUIDER в `SamplerCustomAdvanced`.

Структура повторяет subgraph `image_ideogram4_t2i`; конкретные Ideogram-файлы оставлены внешними, чтобы fragment нельзя было принять за универсальную пару моделей. Он не выполнялся.

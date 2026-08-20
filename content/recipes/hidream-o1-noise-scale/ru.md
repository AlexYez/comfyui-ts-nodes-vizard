# HiDream-O1 base: noise scale и scheduler

Fragment воспроизводит часть официального `image_hidream_o1.json`: `ModelNoiseScale(8.0)` передаёт patched MODEL в `BasicScheduler(normal, 40, 1.0)`.

## Подключение

Подайте HiDream‑O1 base MODEL во внешний вход. Выход `SIGMAS` scheduler подключите к custom sampler, а выход MODEL от `ModelNoiseScale` — к model/guider ветке того же sampler. Fragment фиксирует внутреннюю связь со scheduler, но patched MODEL допускает разветвление на несколько потребителей.

## Что именно проверено

Значения `8.0`, `normal`, `40`, `1.0` и связь MODEL сверены с официальным root workflow. Второй официальный dev case использует `7.6` и 28 шагов; это отдельная конфигурация, не скрытый default recipe.

Exact-source probe проверила clone, пересоздание sampling-объекта и перенос shift/multiplier. Настоящий HiDream‑O1 checkpoint не запускался.

## На что обратить внимание

Не применяйте `8.0` к произвольной MODEL. Downstream sampler и scheduler должны получать один patched MODEL. Если используется dev checkpoint, возьмите подтверждённую dev-конфигурацию, а не этот base fragment.

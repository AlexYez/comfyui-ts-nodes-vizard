# Основная и масочная conditioning-ветви

Подайте основное условие в `cond`, дополнительное — в `cond_NEW`, а маску — в optional-порт `mask`. Fragment задаёт новой ветви `mask_strength: 0.65` и `set_area_to_bounds: true`.

Нода не переносит эти поля в `cond`: выходной список имеет порядок `cond + processed cond_NEW`. Hooks и timestep range в примере не подключены.

Во всех 512 official workflow templates JSON 0.1.42 runtime ID отсутствует. Структура проверена по runtime и source, но sampler с перекрывающимися условиями не запускался; рецепт остаётся `in_review`.

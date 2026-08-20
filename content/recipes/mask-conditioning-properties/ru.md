# Маска и свойства conditioning

Подайте готовое `CONDITIONING` в `cond_NEW`, а совместимую маску — в optional-вход `mask`. Fragment задаёт `strength: 0.8` и `set_cond_area: mask bounds`.

По исходнику каждая запись получает mask tensor, `mask_strength: 0.8` и `set_area_to_bounds: true`. Входы `HOOKS` и `TIMESTEPS_RANGE` не подключены и ничего не добавляют.

Runtime ID отсутствует во всех 512 official workflow templates JSON 0.1.42. Fragment проверен по schema, `/object_info` и helper source, но не исполнялся с моделью и остаётся `in_review`.

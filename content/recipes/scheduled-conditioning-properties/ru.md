# Диапазон 0,2–0,75 для conditioning

`ConditioningTimestepsRange` создаёт основной tuple `(0.2, 0.75)`. Связь с optional-входом `timesteps` заставляет `ConditioningSetProperties` записать `start_percent: 0.2` и `end_percent: 0.75` во внешнее conditioning.

Маска не подключена, поэтому required-виджеты `strength: 1.0` и `set_cond_area: default` не добавляют mask metadata. Fragment показывает именно типизированную связь `TIMESTEPS_RANGE`, а не готовый sampler-граф.

Обе ноды отсутствуют в official workflow templates JSON 0.1.42. Схема и source-семантика проверены; model/scheduler run не выполнялся, статус — `in_review`.

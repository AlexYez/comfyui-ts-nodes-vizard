# Conditioning в первой половине нормализованного denoising

Fragment записывает `start: 0.0` и `end: 0.5` в metadata внешнего conditioning. Перед sampling активная модель переводит эти доли в sigma.

Диапазон не означает буквально половину числа UI-steps. Для сравнения двух настроек оставьте неизменными model, scheduler, steps и seed.

`ConditioningSetTimestepRange` отсутствует во всех 512 official workflow templates JSON 0.1.42. Пример основан на runtime и исходнике, не исполнялся в denoising-run и имеет статус `in_review`.

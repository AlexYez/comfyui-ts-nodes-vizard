# Основное и default conditioning без hooks

Подайте региональное или масочное conditioning в `cond`, а глобальный fallback — в `cond_DEFAULT`. Нода пометит только второй список ключом `default: true`; optional `HOOKS` в fragment не подключён.

Если обычный cond полностью покрывает latent с единичным множителем, остатка для default не останется. Пример поэтому требует cond с неполным spatial-покрытием, но не навязывает конкретную area или mask.

Runtime ID отсутствует во всех 512 official workflow templates JSON 0.1.42. Fragment проверяет experimental source/runtime-контракт, не исполнялся sampler и остаётся `in_review`.

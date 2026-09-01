# TS Remove Background

State-of-the-art удаление фона через BiRefNet. На выходе: вырезанная картинка, альфа-маска и "preview" маски. Опции: выбор модели (HR-matting / general / portrait / DIS), `process_resolution` (с override через `use_custom_resolution`), `precision` (auto/fp16/fp32), `mask_blur`, `mask_offset`, `invert_output`, `temporal_smooth` для видео (`none`/`median3`/`ema` с `ema_alpha`), фон (Alpha / цвет через COLOR-виджет). В v9.4 убран нестабильный `refine_foreground`.

**Когда использовать:** изоляция объектов, продуктовая съёмка, чистые альфа-маски для композа.

## Проверка и происхождение материала

Описание сверено с реализацией `comfyui-timesaver` и встроенной справкой пака на 2026-09-01. Статья имеет статус черновика до отдельной ручной редакционной проверки в Wizard. Если установлена другая версия пака, ориентируйтесь также на живые входы и выходы в панели.

- [Закреплённый исходник ноды](https://github.com/AlexYez/comfyui-timesaver/blob/29b0e730f19a1147cab29399652265f946663194/nodes/image/ts_bgrm_birefnet.py#L1082)

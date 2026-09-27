# TS Remove Background

State-of-the-art удаление фона через BiRefNet. На выходе: вырезанная картинка, альфа-маска и "preview" маски. Опции: выбор модели (HR-matting / general / portrait / DIS), `process_resolution` (с override через `use_custom_resolution`), `precision` (auto/fp16/fp32), `mask_blur`, `mask_offset`, `invert_output`, `temporal_smooth` для видео (`none`/`median3`/`ema` с `ema_alpha`), фон (Alpha / цвет через COLOR-виджет). В v9.4 убран нестабильный `refine_foreground`.

**Когда использовать:** изоляция объектов, продуктовая съёмка, чистые альфа-маски для композа.

## Проверка и происхождение материала

Материал импортирован из встроенной справки `comfyui-timesaver` на 2026-09-27; регистрация ноды проверена по исходнику. Статья имеет статус черновика до отдельной ручной редакционной проверки в Wizard. Если установлена другая версия пака, ориентируйтесь также на живые входы и выходы в панели.

- [Закреплённый исходник ноды](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/nodes/image/ts_bgrm_birefnet.py#L1100)

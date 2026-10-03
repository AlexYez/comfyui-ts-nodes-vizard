# TS Load LoRA, model only

Загружает защищённую модельную LoRA формата TimeSaver и применяет её к `MODEL`. По роли соответствует LoraLoaderModelOnly; CLIP не изменяет. При силе 0 возвращает модель без применения LoRA.

Используйте с совместимой моделью и разрешённым доступом к защищённому файлу. Формат `.tsmodel` не делает LoRA совместимой с другой архитектурой. Для обычных незашифрованных LoRA достаточно штатного загрузчика или TS LoRA Loader.

## Источники

[Реализация](https://github.com/AlexYez/comfyui-timesaver/blob/819d4e573a266fbc2aafb10554943f1e781c351a/nodes/loaders/ts_locked_lora_model_only.py#L72); [справка автора](https://github.com/AlexYez/comfyui-timesaver/blob/819d4e573a266fbc2aafb10554943f1e781c351a/js/docs/TS_LockedLoraModelOnly/ru.md). Проверено по исходнику и справке TimeSaver 12.12.3; выполнение с моделями и человеческое утверждение ещё нужны.

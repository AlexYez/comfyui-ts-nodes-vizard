# TS Load Diffusion Model

Загружает диффузионную модель из `.tsmodel` и возвращает `MODEL`. Текстовый кодировщик и VAE в этот выход не входят: их нужно загрузить отдельно.

## Пример применения

Положите файл в `models/diffusion_models`, выберите его и начните с `weight_dtype = default`. Подключите модель к совместимой цепочке sampling. CLIP и VAE должны соответствовать семейству модели.

## Параметры и ограничения

Кроме `default` доступны варианты FP8: `fp8_e4m3fn`, `fp8_e4m3fn_fast` и `fp8_e5m2`. Они меняют способ загрузки весов, но не делают модель совместимой с любой видеокартой и не гарантируют одинаковый результат. Locked здесь обозначает формат контейнера, а не DRM.

## Источники и границы проверки

Описание подготовлено по исходнику и справке TimeSaver 12.11.7. Полное выполнение с моделями и человеческое утверждение ещё не проведены.

- [Реализация ноды](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/nodes/loaders/ts_locked_diffusion_model.py#L97)
- [Справка автора пака](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/js/docs/TS_LockedDiffusionModel/ru.md)

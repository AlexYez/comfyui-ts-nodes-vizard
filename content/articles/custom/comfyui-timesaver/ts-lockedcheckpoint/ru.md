# TS Load Checkpoint

Загружает checkpoint в формате `.tsmodel` и возвращает `MODEL`, `CLIP` и `VAE`. Файлы выбираются из каталога checkpoints; обычный файл `.safetensors` эта нода не заменяет автоматически.

## Пример применения

Если автор модели распространяет checkpoint как `.tsmodel`, положите его в `models/checkpoints`, обновите список моделей и подключите выходы к sampler, текстовому кодировщику и VAE Decode. Для обычных checkpoint используйте штатный загрузчик.

## Ограничения

Locked — название контейнера, а не обещание шифрования или защиты от копирования. Успешное чтение контейнера не гарантирует, что checkpoint содержит подходящие CLIP и VAE: это зависит от самой модели.

## Источники и границы проверки

Описание подготовлено по исходнику и справке TimeSaver 12.11.7. Полное выполнение с моделями и человеческое утверждение ещё не проведены.

- [Реализация ноды](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/nodes/loaders/ts_locked_checkpoint.py#L59)
- [Справка автора пака](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/js/docs/TS_LockedCheckpoint/ru.md)

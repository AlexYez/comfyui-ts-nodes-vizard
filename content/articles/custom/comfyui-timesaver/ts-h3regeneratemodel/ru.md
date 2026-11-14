# TS H3 Regenerate Model: подготовка модели уточнения

<!-- nov14:start -->
**TimeSaver 12.13.12.** Текущий загрузчик Standard принимает чистую pruned H3 и один complete-файл open_h3_regenerate_2k_lora_complete.safetensors. Он уже содержит LoRA, 50 веток Sharp и проверенную таблицу AdaLN; отдельные sharp_name и reference_checkpoint больше не требуются в пользовательской ноде. При переносе старого графа заново выберите complete-файл. Обычный LoRA Loader не заменяет этот загрузчик, поскольку не применяет специальные Sharp-ветки. Веса не входят в пак; инструкция сборки из исходных файлов приведена в текущей справке автора.

[Реализация](https://github.com/AlexYez/comfyui-timesaver/blob/18c863d206a537c8d60c8db6d1c7dbdf4a29721a/nodes/video/latent_upscale/ts_h3_regenerate.py) · [Текущая справка автора](https://github.com/AlexYez/comfyui-timesaver/blob/18c863d206a537c8d60c8db6d1c7dbdf4a29721a/js/docs/TS_H3RegenerateModel/ru.md). Дополнение не означает полного повторного утверждения старого текста.
<!-- nov14:end -->

Готовит отдельную ветку чистой pruned H3 FL2VA для Open-H3-Regenerate-2K: применяет объединённую LoRA и ветки Sharp. Возвращает MODEL и текстовый отчёт; увеличение видео выполняет следующая TS H3 Regenerate.

## Подключение и файлы

Подключите базовый загрузчик H3 напрямую, до Turbo, Pika, DMAD и других LoRA или патчей. Нода проверяет существующие patches/object_patches и требует модель с AdaLN curves. Ветка первичной генерации может независимо получать свои адаптеры.

В папке LoRA нужны `open_h3_regenerate_2k_lora.safetensors` и `sharp_curve_branches.safetensors`. В `reference_checkpoint` выберите установленный pruned Ref2VA checkpoint: из него читается таблица AdaLN 1025×8 с проверкой SHA-256, а не вся модель на GPU. Файл должен содержать ожидаемую таблицу, одного похожего имени недостаточно.

## Пример

Разветвите выход чистого загрузчика: первая ветка готовит исходное видео, вторая проходит через TS H3 Regenerate Model в TS H3 Regenerate. Не подавайте сюда уже модифицированную модель первой стадии.

## Ограничения

Веса LoRA содержат ожидаемые 312 пар факторов; неподходящие формы и неполное применение вызывают ошибку. По данным реализации, факторы требуют примерно 6,2 ГБ ОЗУ в bf16 или 12,45 ГБ в fp32 — это не полный расход памяти всего workflow. Поддержка конкретного INT8 checkpoint требует правильных метаданных и совместимой архитектуры; произвольная H3-модель не подходит автоматически.

## Источники и границы проверки

[Реализация TimeSaver 12.13.5](https://github.com/AlexYez/comfyui-timesaver/blob/0e1aa5540cb95b8d5d932d4a082ec01d517cd03a/nodes/video/latent_upscale/ts_h3_regenerate.py#L261); [справка автора](https://github.com/AlexYez/comfyui-timesaver/blob/0e1aa5540cb95b8d5d932d4a082ec01d517cd03a/js/docs/TS_H3RegenerateModel/ru.md). Проверены исходники и документация, не живая установка всех зависимостей и не генерация с весами. Статья остаётся черновиком до человеческого утверждения.

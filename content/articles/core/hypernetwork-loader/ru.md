# HypernetworkLoader: патч attention через hypernetwork

## Назначение

`HypernetworkLoader` загружает hypernetwork и добавляет её вычисление в attention diffusion-модели. Нода клонирует `MODEL`, поэтому исходная ветвь остаётся доступной. В отличие от LoRA, здесь файл описывает небольшие последовательности слоёв, которые преобразуют key и value во время attention.

Hypernetwork должна быть создана для размеров каналов и формата, поддержанных выбранной моделью. Общий тип порта `MODEL` не доказывает совместимость.

## Место в графе

На вход подают базовую diffusion-модель. Выход идёт в sampler или следующие model patches. Нода устанавливает один и тот же patch object для `attn1` и `attn2`; фактическое применение происходит при последующем проходе модели.

`CLIP` и `VAE` через эту ноду не проходят. Если задача решается model-only LoRA, это другой формат файла и другой механизм; менять расширение или каталог недостаточно.

## Входы

`model` — обязательный `MODEL`. `hypernetwork_name` — combo из `models/hypernetworks` и дополнительных путей. `strength` — число от −10 до 10 с шагом 0,01 и default 1.

Combo в новом schema API представлен как `COMBO` с массивом `options`. В чистом snapshot массив пуст. Локальные имена не включаются в стабильный fingerprint статьи.

## Выходы

Единственный выход — клонированный `MODEL`. Если файл имеет неподдержанную activation function, parser пишет ошибку в лог и возвращает `None`; loader в таком случае всё равно возвращает клон, но не устанавливает attention patch. Отсутствие exception не означает, что эффект применён.

При совместимом формате output содержит patch для обоих attention slots. Исходный `MODEL` не меняется.

## Как работает

Файл безопасно читается как tensor state dict. Parser извлекает `activation_func`, layer norm, dropout, activation на выходе и last-layer dropout. Поддержаны linear, ReLU, LeakyReLU, ELU, Hardswish (`swish`), tanh, sigmoid, softsign и mish.

Для каждого числового ключа размерности строятся две последовательности Linear/activation/LayerNorm/Dropout: первая для key, вторая для value. Во время attention берётся последняя размерность `k`. Если такая размерность есть в hypernetwork, вычисляется `k + hn_key(k) * strength` и `v + hn_value(v) * strength`; query возвращается без изменения. Для отсутствующей размерности patch оставляет q/k/v как есть.

## Параметры и настройка

Используйте strength из документации файла. Отрицательное значение меняет знак добавки, но не является гарантированной смысловой противоположностью. Значение 0 всё ещё загружает и устанавливает patch, хотя его арифметический вклад равен нулю.

Следите за журналом. Сообщение `Unsupported Hypernetwork format` означает, что activation не поддержана и output фактически равен клону без hypernetwork. Отсутствие подходящей размерности не выдаёт отдельного предупреждения в callback, поэтому совместимость нужно проверять результатом и документацией.

## Проверенный пример

Рецепт «Hypernetwork поверх внешнего MODEL» принимает внешний `MODEL`, выбирает установленный файл и strength 1. Fragment основан на exact runtime-контракте: одно входное соединение, один loader и один выход для дальнейшего sampler.

Official workflow templates JSON 0.1.42 не содержит `HypernetworkLoader`, поэтому у рецепта нет заимствованных widgets или обещанного изображения. Файл hypernetwork не установлен, полный fragment не выполнялся; источник проверен построчно.

## Частые ошибки

**Нода выполнилась, но эффекта нет.** Проверьте лог на unsupported activation, соответствие размерностей и ненулевой strength.

**Файл лежит в `models/loras`.** Hypernetwork использует отдельный формат и каталог `models/hypernetworks`.

**Модель соединяется, но sampling падает на Linear shape.** Веса hypernetwork не соответствуют размерности или внутренней раскладке модели.

**Сила 0 используется как дешёвый bypass.** Код всё равно читает файл, строит модули и устанавливает patch; для настоящего bypass уберите ноду или обойдите её ветвью.

**Ожидают изменение CLIP.** Patch затрагивает attention diffusion-модели, а не текстовый энкодер.

## Ограничения и производительность

Hypernetwork добавляет Linear-проходы для каждого совпавшего attention-вызова. Стоимость зависит от размерностей, числа слоёв модели, устройства и структуры файла. Встроенный dropout, если он указан форматом, также входит в созданные последовательности.

Нода не кеширует разобранный файл на уровне своего класса, в отличие от `LoraLoader`. Повторное выполнение снова вызывает `load_torch_file` и строит модули. Универсальных цифр производительности без точного файла и модели нет.

## Совместимость и источники

Материал сверён с `/object_info` и `comfy_extras/nodes_hypernetwork.py` ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Полный census 512 official JSON не нашёл ни root-, ни subgraph-примеров.

Embedded docs 0.5.9 верно указывает каталог, MODEL и strength, но описывает эффект слишком общо. Exact source показывает конкретную операцию: query не меняется, к key/value добавляются dimension-specific преобразования, а неподдержанная activation возвращает неизменённый clone после сообщения в журнале.

- [Реализация `HypernetworkLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_hypernetwork.py#L9-L139)
- [Каталог `models/hypernetworks`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L49-L49)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

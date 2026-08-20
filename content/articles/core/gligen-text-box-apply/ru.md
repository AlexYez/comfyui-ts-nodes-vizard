# GLIGENTextBoxApply: привязать текст к области

## Что делает нода

`GLIGENTextBoxApply` кодирует отдельный текст через переданный `CLIP` и записывает пространственное условие в метаданные каждого элемента входного `CONDITIONING`. Основной тензор conditioning остаётся тем же объектом; словарь метаданных копируется и получает ключ `gligen`.

Внутри хранится кортеж `("position", gligen_model, position_params)`. Одна запись params имеет точный порядок: unprojected pooled CLIP embedding, `height // 8`, `width // 8`, `y // 8`, `x // 8`. Сэмплер позднее преобразует это в нормализованные координаты `(x1, y1, x2, y2)` относительно формы latent.

Это metadata-операция, а не рисование маски. Влияние возникает только при sampling совместимой моделью и загруженным GLIGEN patcher.

## Когда использовать и когда не использовать

Используйте ноду, чтобы связать короткое описание объекта с прямоугольником на будущей картинке: например, «красный куб» в области 256×256 с левым верхним углом `(128, 128)`.

Не ожидайте жёсткой геометрической маски или гарантии, что объект целиком останется внутри рамки. GLIGEN добавляет пространственное условие к denoise; результат зависит от основной модели, checkpoint GLIGEN, prompt и sampler.

Не смешивайте в последовательных apply разные `gligen_textbox_model`. Реализация сохраняет старый список params, но кортеж переписывает моделью последнего вызова; старые embeddings окажутся под новым patcher.

## Короткий рецепт подключения

1. Создайте базовый positive `CONDITIONING` обычным text encode.
2. Загрузите совместимую модель через `GLIGENLoader`.
3. Подключите тот же совместимый `CLIP` к входу `clip`.
4. Задайте `text`, `width`, `height`, `x`, `y` в пикселях целевого изображения.
5. Передайте выходное conditioning в positive-вход sampler.

Fragment «Добавить текстовую область 256×256» использует текст `красный куб`, размер 256×256 и координаты `(128, 128)`. Он прошёл проверку схемы, типов портов и закреплённого поведения метаданных. GLIGEN weights и полный сэмплер не выполнялись.

## Входы, выходы и параметры

Обязательные входы: `conditioning_to: CONDITIONING`, `clip: CLIP`, `gligen_textbox_model: GLIGEN`, многострочный `text: STRING`. У text descriptor включён `dynamicPrompts: true`.

`width` и `height` — `INT` с default 64, диапазоном 8–16384 и шагом интерфейса 8. `x` и `y` — `INT` с default 0, диапазоном 0–16384 и тем же шагом. `(x, y)` обозначает левый верхний угол, затем ширина и высота задают правую нижнюю точку.

Выход один: `CONDITIONING`, не list-output. Нода не обрезает прямоугольник по границам изображения. UI предлагает кратные восьми значения, но API-клиент может передать другое целое; `// 8` тогда округлит вниз.

## Типовые связки

`CLIPTextEncode → GLIGENTextBoxApply → KSampler` формирует positive-ветвь. Параллельно `GLIGENLoader` подаёт model patcher, а CLIP из совместимого checkpoint обслуживает и обычный prompt, и текст рамки.

Для нескольких объектов ставьте несколько `GLIGENTextBoxApply` последовательно. Каждый вызов добавляет один params к существующему списку. Внутренняя `Gligen` резервирует максимум 30 объектов; 31-я запись выйдет за размер masks при sampling.

Sampler helpers извлекают GLIGEN из positive/negative conditioning как additional model. В `get_area_and_mult` тип `position` вызывает `set_position` и устанавливает callback в `middle_patch`.

## Практический пример

Полный просмотр официального bundle 0.1.42 охватил 512 JSON, все root nodes и 272 subgraphs. `GLIGENTextBoxApply` и `GLIGENLoader` отсутствуют, поэтому официальных serialized widgets и рабочей topology для закреплённой версии нет.

В пробе закреплённого класса подменённый CLIP получил строку `красный куб`, а `encode_from_tokens` был вызван с `return_pooled="unprojected"`. Для `width=256`, `height=128`, `x=64`, `y=32` метаданные сохранили `(pooled, 16, 32, 4, 8)`: сначала высота и ширина, затем y и x, уже в latent-ячейках.

Проба также подтвердила неглубокое копирование metadata и append старого params. Tensor базового conditioning остался тем же объектом. Это исполнение класса без весов, не проверка качества GLIGEN sampling.

## Частые ошибки и способы проверки

**Меняют местами x/y и width/height.** В интерфейсе задаются пиксели, а metadata хранит порядок `height, width, y, x`. Проверяйте рамку на простом одиночном объекте.

**Передают значения не кратные восьми через API.** Целочисленное деление округляет вниз: 15 пикселей превращаются в одну latent-ячейку, а не в 1,875.

**Рамка выходит за холст.** У каждого числа есть общий max 16384, но проверки `x + width ≤ image_width` нет. Нормализованная правая граница может стать больше 1.

**Добавляют больше 30 областей.** `max_objs = 30`; разбивайте задачу или уменьшайте число объектов.

**Меняют GLIGEN-модель между apply.** Последний patcher обслужит и предыдущие params. Используйте один loader для цепочки.

## Производительность и внутреннее поведение

Каждый вызов заново токенизирует `text` и запускает CLIP encode, хотя обычный conditioning tensor не пересчитывает. Из пары возвращённых значений нода использует только `cond_pooled`; token-level `cond` отбрасывается.

Metadata хранит pooled embedding для каждой области и каждого conditioning entry. Во время sampling `set_position` дополняет список до 30 объектов, повторяет boxes, masks и embeddings по batch, а затем GLIGEN attention работает как middle patch.

Стоимость самой Python-операции мала по сравнению с CLIP encode и sampler patch. Большое число рамок повышает объём embedding и работу GLIGEN; оно также приближает жёсткий лимит 30.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `GLIGENTextBoxApply`, модуле `nodes`. Fingerprint: `sha256:ebd993b388d98a30147b048936e3978205a72061b4fb11a5896c1ea1818b06ca`.

Runtime не помечает ноду deprecated, experimental, dev-only или API-only; это не output node. Размеры и координаты имеют max 16384, step 8; text descriptor поддерживает multiline и dynamic prompts.

Embedded docs 0.5.9 правильно называют x/y левым верхним углом, но не описывают `// 8`, точный кортеж метаданных, append, лимит 30 и sampler middle patch. Эти детали закреплены исходником.

## Связанные ноды и источники

`GLIGENLoader` даёт model patcher. `CLIPTextEncode` создаёт базовое conditioning, а переданный CLIP отдельно кодирует текст области. `KSampler` — фактический consumer metadata. Conditioning-area utilities ограничивают стандартное conditioning иначе и GLIGEN не заменяют.

- [Реализация `GLIGENTextBoxApply`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1211-L1240)
- [Нормализация рамок и лимит 30 объектов](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/gligen.py#L198-L244)
- [Применение GLIGEN в sampler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L103-L113)
- [Embedded docs 0.5.9 для `GLIGENTextBoxApply`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/GligenTextBoxApply/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

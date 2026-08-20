# CLIPTextEncodeSDXLRefiner: текст и aesthetic score для Refiner

## 1. Что делает нода

`CLIPTextEncodeSDXLRefiner` кодирует одну строку через `CLIP` и добавляет в `CONDITIONING` три поля: `aesthetic_score`, `width` и `height`. Этот формат предназначен для размерного conditioning SDXL Refiner.

`ascore` — переданное пользователем число. Нода не анализирует изображение и не вычисляет его эстетическое качество.

## 2. Место в графе

На вход подают `CLIP` от совместимого SDXL Refiner checkpoint. Выход используют в positive или negative ветви той стадии sampling, где работает Refiner. Base- и Refiner-стадии могут иметь разные текстовые энкодеры, conditioning и диапазоны сигм; эта нода собирает только текстовую часть Refiner.

Она не переключает модель с Base на Refiner, не формирует расписание и не решает, на каком шаге начинается вторая стадия. Это задают соседние sampler/guider-ноды.

## 3. Входы

- `ascore` (`FLOAT`) — значение `aesthetic_score`; default `6.0`, диапазон `0.0…1000.0`, шаг `0.01`.
- `width`, `height` (`INT`) — размерная метка; default `1024`, runtime-диапазон `0…16384`.
- `text` (`STRING`) — многострочный prompt с frontend dynamic prompts.
- `clip` (`CLIP`) — текстовый энкодер Refiner.

Все пять входов обязательны в `/object_info`. Наличие default у виджета не делает поле optional на уровне backend-схемы.

## 4. Выходы

Нода возвращает один `CONDITIONING`. В нём совмещены результат scheduled text encoding и словарь с `aesthetic_score`, `width`, `height`.

Отдельного выхода с числом `ascore` нет. После кодирования значение можно увидеть только как metadata conditioning либо по логике модели, которая его потребляет.

## 5. Как работает внутри

Реализация короткая: `clip.tokenize(text)` создаёт токены, затем `clip.encode_from_tokens_scheduled` кодирует их с дополнительным словарём из трёх полей. Нода не меняет токены в зависимости от `ascore` и не сравнивает ширину с размером latent.

В закреплённой реализации SDXL Refiner модель читает `width`, `height` и `aesthetic_score` из conditioning. Если поле aesthetic отсутствует, код модели использует разные defaults для positive и negative prompt type. Эта нода, напротив, всегда записывает явно переданный `ascore`; если два её экземпляра настроены одинаково, обе ветви получат одно значение.

## 6. Настройки

Значения `1024 × 1024` и `ascore = 6.0` — defaults runtime и безопасная отправная точка для проверки схемы, но не универсальный художественный пресет. Подбирайте размеры вместе с latent и совместимой моделью.

Если positive и negative должны иметь разные aesthetic labels, используйте два экземпляра с разными `ascore`. Не рассчитывайте на внутренний default модели: явное поле, записанное этой нодой, его заменяет.

Runtime допускает ширину и высоту от нуля и не проверяет кратность восьми. Embedded docs `0.5.9` приводят более узкие рекомендации, но их не подтверждают ни `INPUT_TYPES`, ни метод выполнения закреплённой версии.

## 7. Пример подключения

Recipe `recipe.sdxl-refiner-text-conditioning` подаёт внешний Refiner `CLIP`, текст, `width = height = 1024` и `ascore = 6.0`. Выход следует подключить к соответствующей positive или negative ветви Refiner sampler/guider.

Архив official workflow templates `0.1.42` не содержит `CLIPTextEncodeSDXLRefiner` ни в корневых графах, ни в subgraphs. Fragment поэтому source-derived. Model-free probe с подставным CLIP подтвердил точный вызов токенизации и словарь metadata, но Base → Refiner workflow и реальные веса не запускались.

## 8. Частые ошибки

- Подать `CLIP` от Base или другого семейства и считать, что NodeId сам обеспечит совместимость.
- Принять `ascore` за результат автоматической оценки текущего изображения.
- Одной нодой кормить positive и negative, хотя ветвям нужны разные aesthetic labels.
- Считать `width` и `height` командой resize. Нода не обрабатывает пиксели и latent.
- Следовать неподтверждённым числам из вторичной документации как обязательным ограничениям runtime.

## 9. Ограничения и производительность

Основная стоимость — токенизация и один scheduled encode через подключённый CLIP. Добавление трёх скаляров почти ничего не стоит. Длинный prompt и выбранный text encoder влияют на время и память сильнее, чем числовые поля.

Нода не валидирует модель, стадию sampling, соответствие размера и ветвей. Она также не предоставляет `crop` и `target` fields базовой SDXL-ноды: контракт Refiner здесь намеренно уже.

## 10. Совместимость и источники

Материал закреплён на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`; fingerprint `/object_info` — `sha256:34882974614510e24dd0b085484a86f1d0876f7c4aecbfe3c2c5eb367829b881`. Реализация: [`comfy_extras/nodes_clip_sdxl.py`, строки 7–27](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_clip_sdxl.py#L7-L27). Потребление metadata Refiner: [`comfy/model_base.py`, строки 482–507](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L482-L507).

Embedded docs `0.5.9` помечены как AI-generated и содержат неподтверждённые рекомендации о минимальном размере, кратности, `ascore` и доле Refiner-стадии; они не использованы как факты реализации. Полный workflow wheel `0.1.42` не дал прямых случаев. Статья остаётся `draft/in_review`, пока нет исполнения с весами и ручного одобрения.

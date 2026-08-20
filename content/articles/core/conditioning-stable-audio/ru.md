# ConditioningStableAudio: временные числа для Stable Audio

## Назначение

`ConditioningStableAudio` добавляет к positive и negative conditioning два числа: `seconds_start` и `seconds_total`. Основные embedding-тензоры нода не меняет.

Эти поля предназначены для моделей семейства Stable Audio. Нода только готовит metadata; длину latent, waveform или файл она не создаёт.

## Место в графе

В оба входа подают готовые `CONDITIONING`, обычно после text encoder. Два выхода подключают к positive и negative портам sampler или guider, который работает с совместимой audio-моделью.

Длительность latent задаётся отдельно, например через `EmptyLatentAudio`. Значения времени в conditioning и размер latent могут расходиться: runtime не связывает их и не проверяет совместимость.

## Входы

`positive` и `negative` — обязательные значения `CONDITIONING`. Нода не требует одинакового числа записей или одинаковой формы тензоров в двух списках.

`seconds_start` принимает 0–1000 секунд с шагом 0,1; значение по умолчанию — 0. `seconds_total` имеет тот же диапазон и шаг, по умолчанию — 47. Оба числа проверяются отдельно, поэтому start может быть больше total, а total — равняться нулю.

## Выходы

Выходы называются `positive` и `negative`, оба имеют тип `CONDITIONING`. Число записей в каждом списке сохраняется.

Каждая запись получает float-значения `seconds_start` и `seconds_total`. Остальные metadata копируются, основной тензор переиспользуется. Если эти ключи уже существовали, новые числа их заменяют.

## Как работает

Метод дважды вызывает `conditioning_set_values`: один раз для positive, второй — для negative. Helper создаёт новый список и копию metadata-словаря каждой записи, затем записывает два ключа.

`StableAudio1` читает оба числа и превращает их в отдельные числовые embeddings. `StableAudio3` в закреплённом исходнике читает только `seconds_total`; `seconds_start` в его `extra_conds` не используется. Поэтому одинаковая metadata не означает одинаковое поведение разных поколений модели.

## Параметры и настройка

Для начала клипа с нулевой отметки используйте `seconds_start: 0`. `seconds_total` согласуйте с длительностью audio latent, если workflow не задаёт другое намеренное смещение.

UI разрешает значения до 1000. Внутренний `NumberConditioner` ограничивает числа собственным диапазоном: у `StableAudio1` максимум 512, у `StableAudio3` для total — 384. Значения выше этих границ дадут одинаковый числовой input модели после clamp, хотя metadata останется исходной.

## Проверенный пример

Fragment «Временные metadata для двух conditioning-ветвей» принимает внешние positive и negative, задаёт `seconds_start: 0.0` и `seconds_total: 47.0`, затем возвращает две обработанные ветви. Unit-level synthetic check подтвердил копирование списков, сохранение tensor-ссылок и запись обоих float-ключей без model weights.

Во всех 512 official workflow templates JSON 0.1.42, включая подграфы, `ConditioningStableAudio` отсутствует. Даже `audio_stable_audio_example` использует text conditioning напрямую. Fragment не выдаётся за официальный topology и не проходил полный sampling-run.

## Частые ошибки

**Seconds_total считают конечной отметкой.** Исходник передаёт это поле как total-duration conditioner. Нода не вычисляет `start + duration`.

**Время conditioning считают длиной latent.** `EmptyLatentAudio` создаёт размер независимо. Проверяйте оба значения.

**Ожидают одинаковый эффект на StableAudio1 и StableAudio3.** Вторая модель читает total, но не читает start в закреплённой реализации.

**Большие значения считают расширением диапазона модели.** UI принимает до 1000, однако внутренний number conditioner clamp ограничивает вход embeddings.

## Ограничения и производительность

Нода копирует только списки и metadata-словари; embedding-тензоры и модели не вычисляются. Стоимость мала по сравнению с text encoding и diffusion sampling.

Нет проверки порядка или согласованности секунд, нет привязки к sample rate и latent length. Поддержка ключей зависит от model implementation: несовместимая модель может их игнорировать. Реальный звук, смещение и длительность в этой партии не проверялись.

## Совместимость и источники

Материал закреплён на ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningStableAudio`, python module — `comfy_extras.nodes_audio`.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningStableAudio/en.md` верно описывают два поля, но не различают потребление metadata в `StableAudio1` и `StableAudio3`, не упоминают model-side clamp и отсутствие проверки согласованности времени.

- [Класс `ConditioningStableAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L39-L64)
- [Потребление полей в `StableAudio1`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L799-L825)
- [Потребление total в `StableAudio3`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L837-L900)
- [Clamp числового conditioner](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/audio/embedders.py#L97-L132)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

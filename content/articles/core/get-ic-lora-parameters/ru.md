# GetICLoRAParameters: извлечь параметры IC-LoRA из MODEL

## Что делает нода

`GetICLoRAParameters` читает attachment `lora_metadata` у входного `MODEL` и ищет первый ключ, имя которого оканчивается на `reference_downscale_factor`. Найденное значение переводится в `float`, округляется функцией Python `round`, ограничивается снизу единицей и возвращается в объекте `IC_LORA_PARAMETERS`.

Эти параметры нужны `LTXVAddGuide`: некоторые IC-LoRA обучены на уменьшенной сетке референса. Обычный `MODEL`-сокет не сообщает downstream-нode такой коэффициент, поэтому metadata передаются отдельной связью.

Нода не загружает LoRA и не меняет модель. Она лишь извлекает одно нормализованное значение из уже прикреплённых metadata.

## Когда использовать и когда не использовать

Используйте ноду между тем `LoraLoaderModelOnly`, который применяет конкретную IC-LoRA, и `LTXVAddGuide`. В официальных LTX 2.3 IC-LoRA subgraph именно такая цепочка передаёт коэффициент к guide-ноде.

Для обычной LoRA без `reference_downscale_factor` этот шаг не нужен: `LTXVAddGuide` и без optional-входа использует коэффициент `1`. Не подключайте сюда исходный checkpoint до LoRA Loader — у него, как правило, нет нужного attachment.

Не считайте выход полным набором safetensors metadata. В версии 0.32.0 объект содержит только `reference_downscale_factor`.

## Короткий рецепт подключения

1. Загрузите модель и примените IC-LoRA через `LoraLoaderModelOnly`.
2. Разветвите его `MODEL`: одна связь продолжает model pipeline, вторая идёт в `GetICLoRAParameters`.
3. Подключите `IC_LORA_PARAMETERS` к одноимённому optional-входу `LTXVAddGuide`.
4. К этой guide-ноде подключите референс, соответствующий той же IC-LoRA.
5. Проверьте, что spatial dimensions входного latent делятся на извлечённый коэффициент.

Рецепт Wizard повторяет точную связь официального IC-LoRA subgraph, но оставляет checkpoint, LoRA-файл, VAE и референс внешними зависимостями.

## Входы, выходы и параметры

Единственный вход `iclora_model` имеет тип `MODEL`. Нужен именно объект после LoRA Loader: `comfy.sd.load_lora_for_models` прикрепляет считанные metadata к новому model patcher под именем `lora_metadata`.

Выход `iclora_parameters` имеет специальный тип `IC_LORA_PARAMETERS`. Это словарь вида `{"reference_downscale_factor": N}`, где `N` — целое число не меньше `1`.

Widgets у ноды нет. Выбор ключа, округление и fallback зафиксированы в коде и не настраиваются через интерфейс.

## Типовые связки

Полный просмотр workflow wheel 0.1.42 нашёл два экземпляра ноды: в `template_ltx2_3_ic_lora_ingredients` и `video_ltx2_3_ic_lora`. Оба находятся внутри subgraph, работают в mode `Always` и не имеют widgets.

В обоих случаях `LoraLoaderModelOnly` передаёт `MODEL` в `GetICLoRAParameters`, а выход параметров подключён к `LTXVAddGuide`. Параллельно тот же LoRA-патченный model используется sampling-ветвью.

Если guides выстроены цепочкой, параметры подключаются к той guide-ноде, чей референс относится к конкретной IC-LoRA. Tooltip прямо указывает, что каждая `LTXVAddGuide` читает только собственный optional-вход.

## Практический пример

В официальном IC-LoRA subgraph `LoraLoaderModelOnly` №195 подключён к `GetICLoRAParameters` №196. Выход №196 идёт в optional socket №6 у `LTXVAddGuide` №115; guide получает `frame_idx = 0`, `strength = 1`.

Если metadata содержат строку `"2"`, результатом станет коэффициент `2`. Значение `0.7` округлится до `1`, а `2.6` — до `3`. Python применяет округление к ближайшему чётному при точной половине: `2.5` даёт `2`.

При отсутствующем attachment, пустом словаре, ключе без нужного суффикса или нечисловой строке результат равен `1`.

## Частые ошибки и проверка

**Всегда получается 1.** Проверьте, что вход пришёл после LoRA Loader и metadata действительно содержат ключ с суффиксом `reference_downscale_factor`. Имя может иметь префикс, но окончание должно совпасть дословно.

**В metadata несколько подходящих ключей.** Код берёт первый элемент в порядке обхода словаря. Такой файл неоднозначен; проверьте его metadata вне графа и оставьте один канонический ключ.

**При бесконечном значении возникает ошибка.** `float("inf")` проходит преобразование, но `round` выбрасывает `OverflowError`; эта ошибка не входит в обработанный список. Исправьте metadata LoRA.

**Guide сообщает о неделимом размере.** Это уже проверка `LTXVAddGuide`: latent width и height должны делиться на коэффициент.

## Производительность и внутреннее поведение

Операция не читает safetensors-файл заново. Она обращается к metadata, уже сохранённым в attachment model patcher, поэтому вычислительная стоимость мала и не зависит от размера весов.

Нода не клонирует и не загружает `MODEL`, не переносит тензоры между устройствами и не держит GPU intermediates. Создаётся только небольшой Python-словарь.

Поиск реализован через `next(...)`. После первого подходящего ключа остальные значения не рассматриваются. Ошибки `StopIteration`, `TypeError` и `ValueError` приводят к fallback `1`.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `GetICLoRAParameters` и модуля `comfy_extras.nodes_lt`. Fingerprint: `sha256:2842585e74ef274d9f867b5a7eea2bce4e052dab9ff97a4e729a82e3f25096b4`.

Нода активна, не experimental и не deprecated. Formal replacement и runtime aliases отсутствуют. Специальный socket `IC_LORA_PARAMETERS` требует совместимую версию `LTXVAddGuide`.

Embedded docs 0.5.9 правильно описывают назначение, но не раскрывают порядок выбора ключа, округление, fallback и необработанный `OverflowError`.

## Связанные ноды и источники

`LoraLoaderModelOnly` прикрепляет metadata, `GetICLoRAParameters` нормализует коэффициент, `LTXVAddGuide` применяет его к пространственной сетке guide. Обычный `LoraLoader` создаёт такое attachment и для model, если metadata доступны.

- [Реализация `GetICLoRAParameters`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L23-L60)
- [Прикрепление LoRA metadata к model patcher](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L98-L121)
- [Официальный LTX 2.3 IC-LoRA template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_ic_lora.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/GetICLoRAParameters/en.md)

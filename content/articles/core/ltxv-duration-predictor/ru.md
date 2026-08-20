# LTXVDurationPredictor: длительность prompt и число кадров

## Что делает нода

`LTXVDurationPredictor` запускает отдельный LTX 2.4 `DurationHead` на text connector outputs и возвращает два значения:

- `seconds` — сырое предсказание head в секундах;
- `num_frames` — число кадров, рассчитанное из `seconds`, `frame_rate` и заданных границ.

Нода не запускает diffusion sampling. Она берёт text context из первого элемента positive conditioning, пропускает его через caption connectors основной модели, делит результат на video и audio token dimensions и подаёт обе группы в duration head.

Выход `seconds` не ограничивается `min_seconds` и `max_seconds`. Ограничение применяется только при вычислении `num_frames`.

## Когда использовать и когда не использовать

Нода предназначена для совместимой LTX 2.4 цепочки с отдельным duration head, загруженным как `MODEL_PATCH`. Она подходит, когда число кадров нужно получить из prompt до создания video latent или настройки дальнейшего workflow.

Не подключайте произвольный `MODEL_PATCH`. Исполнение проверяет точный Python type `DurationHead` и сразу выдаёт `ValueError`, если patch содержит другую модель.

Обычный LTXV model также недостаточен сам по себе. Diffusion model должен предоставлять совместимый `preprocess_text_embeds`, video cross-attention dimension и LTXV-AV connector output. Socket type `MODEL` не доказывает эту архитектурную совместимость.

Для batch разных prompts нода не выдаёт batch длительностей: она использует только первую запись positive conditioning и, если context batch больше одного, оставляет только первый batch item.

## Короткий рецепт подключения

Приложенный source-derived fragment оставляет локальные assets внешними:

1. Загрузите совместимый LTX 2.4 `MODEL`.
2. Получите positive `CONDITIONING` от соответствующего text encoder и prompt.
3. Загрузите настоящий duration-head checkpoint через `ModelPatchLoader`; его выход должен иметь тип `MODEL_PATCH`.
4. Подключите три значения к `LTXVDurationPredictor`.
5. Начните с `frame_rate = 24`, `min_seconds = 1`, `max_seconds = 20`.
6. Используйте `num_frames` там, где downstream ожидает длину видео; `seconds` выводите отдельно, если нужна исходная оценка head.

Fragment не закрепляет filename: combo зависит от локальной папки моделей, а в workflow wheel 0.1.42 exact duration case отсутствует.

## Входы, выходы и параметры

- `model` (`MODEL`) — LTX 2.4 diffusion model с caption connector preprocessing.
- `positive` (`CONDITIONING`) — источник text context и metadata. Используется `positive[0]`, а не весь список conditioning entries.
- `duration_head` (`MODEL_PATCH`) — head, загруженный `ModelPatchLoader`; runtime проверяет `DurationHead`.
- `frame_rate` (`FLOAT`) — кадров в секунду, default `24`, диапазон `1…120`, шаг `0.01`.
- `min_seconds` (`FLOAT`) — нижняя граница только для `num_frames`, default `1`, диапазон `0.5…120`, шаг `0.1`.
- `max_seconds` (`FLOAT`) — верхняя граница только для `num_frames`, default `20`, тот же диапазон и шаг.
- `num_frames` (`INT`) — ограниченное и, когда границы позволяют, приведённое к causal VAE grid значение.
- `seconds` (`FLOAT`) — raw unclamped prediction.

UI schema ограничивает каждый параметр отдельно, но не требует `min_seconds ≤ max_seconds`. Такой порядок нужно контролировать в workflow.

## Типовые связки

`ModelPatchLoader` распознаёт duration-head state dict, нормализует префиксы ключей, создаёт `DurationHead` и сохраняет веса в `float32`. Его выход подключается только к `duration_head`, а не заменяет основной diffusion `MODEL`.

Positive conditioning должно принадлежать той же LTXV-AV text path, что и модель. Metadata flag `unprocessed_ltxav_embeds` передаётся в `preprocess_text_embeds`; от него зависит, нужно ли запускать connectors над context.

`num_frames` можно передать конструктору video latent или другим нодам, принимающим длину. Конкретная downstream-связка зависит от версии LTX 2.4 workflow и не была найдена в официальном wheel 0.1.42, поэтому статья не объявляет вымышленный exact topology.

## Практический пример

Пусть head предсказал `30` секунд, а параметры остались default: `24 fps`, минимум `1`, максимум `20`. Для расчёта кадров значение ограничивается двадцатью секундами: `480` raw frames. Затем формула привязывает число к causal grid и возвращает `473`, то есть `8 × 59 + 1`.

При этом второй выход останется `seconds = 30`. Такое расхождение нормально: один output сообщает предсказание head, второй — допустимую длину по настройкам.

Model-free probe выполнил точный node method с подклассом настоящего `DurationHead`. Он подтвердил выбор первого conditioning batch, split processed context на video/audio dimensions, перевод token tensors в `float32`, совместную загрузку model и patcher и результат `30 → 473`. Реальный checkpoint не использовался.

## Частые ошибки и способы проверки

**Подключён другой model patch.** Сообщение `The connected model_patch is not an LTX duration head` означает, что loader выдал не `DurationHead`. Проверьте файл и выход именно `ModelPatchLoader`.

**Ожидание clamped seconds.** `min_seconds` и `max_seconds` не меняют output `seconds`. Для downstream длины используйте `num_frames`.

**Batch prompts дают один результат.** Это зафиксированное поведение: берётся первый conditioning entry и первый batch item. Разделите prompts на отдельные исполнения, если каждой строке нужна своя длительность.

**Перепутаны min и max.** Schema допускает это. Формула продолжит считать и может вернуть число, которое не соответствует ожидаемому интервалу. Всегда держите `min_seconds ≤ max_seconds`.

**Число кадров не имеет форму `8k + 1`.** Обычно значение привязывается вниз к grid, а при уходе ниже минимума — вверх. Но если тесный `max_frames` не оставляет места для следующей grid point, реализация возвращает сам cap. Например, при `0.5…0.5` секунды и `24 fps` результат равен `12`, а не `8k + 1`.

## Производительность и внутреннее поведение

Перед вычислением `load_models_gpu` получает и основной model patcher, и duration-head patcher. Затем head переводится на device основной модели, context — в inference dtype модели, а processed video/audio tokens — в `float32` перед head.

`DurationHead` проецирует video tokens размерности `4096` и audio tokens размерности `2048` в общее пространство `256`, добавляет modality embeddings, объединяет tokens, выполняет cross-attention от обучаемого query, затем MLP. Последний scalar проходит через `exp`, поэтому корректный finite output head положителен.

Преобразование tensor в Python `float` синхронизирует получение scalar. Это заметно дешевле diffusion pipeline, но всё равно может загрузить крупную модель и выполнить её caption connectors. Пиковая VRAM и время на разных offload-конфигурациях не измерялись.

## Совместимость, изменения и устаревание

Контракт проверен для ComfyUI `0.32.0` и frontend `1.48.7`. Нода зарегистрирована в `comfy_extras.nodes_lt`, category `conditioning/video_models`; flags experimental, deprecated, API-only и dev-only выключены.

Schema fingerprint: `sha256:e0571d5bea7098876887d6eeb8287849f605000a0d0e80d98bad780917c58420`.

Node Replacement API не содержит замены. В embedded docs 0.5.9 нет отдельной страницы exact NodeId. Полный recursive census 512 JSON и 768 root/subgraph graphs workflow wheel 0.1.42 не нашёл `LTXVDurationPredictor` и не дал проверенного filename duration head.

## Связанные ноды и источники

- `ModelPatchLoader` — загружает и типизирует LTX 2.4 duration head как `MODEL_PATCH`.
- `LTXAVTextEncoderLoader` — относится к совместимой LTXV-AV text-conditioning цепочке.
- `ModelSamplingLTXV` и `LTXVScheduler` — соседние элементы последующего sampling, но не участвуют в предсказании head.
- Конструктор LTXV video latent — возможный потребитель `num_frames`; exact связь должна соответствовать выбранному workflow.

Источники: [реализация LTXVDurationPredictor](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L1123-L1174), [DurationHead и seconds_to_num_frames](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/duration_head.py#L25-L81), [ModelPatchLoader для duration head](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_patch.py#L229-L336), [LTXV-AV text preprocessing](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/av_model.py#L583-L600).

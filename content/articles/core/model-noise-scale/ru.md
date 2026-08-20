# ModelNoiseScale: задать training noise scale модели

`ModelNoiseScale` клонирует `MODEL` и заменяет внутри него объект `model_sampling`, задавая абсолютное значение `noise_scale`. Проверенные официальные применения относятся к HiDream‑O1: `8.0` для base и `7.6` для dev workflow.

## 1. Что делает нода

Нода получает текущий `model_sampling`, создаёт новый экземпляр того же Python-класса с `model_config`, переносит `shift` и `multiplier`, вызывает `set_noise_scale(noise_scale)` и добавляет новый объект как patch клонированной модели.

Исходный MODEL не меняется. Это не умножение прежнего значения на коэффициент: введённое число полностью заменяет абсолютный scale.

## 2. Место в графе

В официальных HiDream‑O1 workflow нода стоит сразу после `CheckpointLoaderSimple`. Её MODEL идёт в `BasicScheduler` и в sampler либо в следующий HiDream patch. Scheduler и sampling используют одну изменённую конфигурацию.

Патч не нужен только потому, что в графе присутствует шум. Он предназначен для модели, обучение которой требует конкретного абсолютного noise scale. Для обычной EPS-модели без совместимого `set_noise_scale` нода может быть неприменима.

## 3. Входы

- `model` — входной `MODEL`.
- `noise_scale` — `FLOAT` от `0.0` до `64.0`, шаг `0.01`, значение по умолчанию `1.0`.

Tooltip исходника приводит HiDream‑O1 base `8.0` и dev `7.5`. Однако закреплённый официальный dev workflow 0.1.42 фактически сохраняет `7.6`; статья показывает оба факта и не подменяет значение из реального графа текстом tooltip.

## 4. Выход

Выход имеет тип `MODEL` и является clone входного model patcher. В clone объект `model_sampling` заменён новым экземпляром; исходная модель и её scale остаются прежними.

Веса diffusion model не копируются целиком: patcher-клон обычно разделяет их и хранит изменения конфигурации. Но сам sampling-объект пересоздаётся и может потерять runtime-состояние, которое не восстанавливается конструктором и двумя перенесёнными полями.

## 5. Как работает

Код вызывает `type(original)(m.model.model_config)`. Затем `set_parameters(shift=original.shift, multiplier=original.multiplier)` пересчитывает sigmas для прежнего flow shift и multiplier. После этого задаётся новый `noise_scale` и patch регистрируется под именем `model_sampling`.

В `CONST.noise_scaling` scale участвует в формуле `sigma × noise_scale × noise + (1 - sigma) × latent`. Кроме того, многие k-diffusion samplers читают `model_sampling.noise_scale` и умножают на него внутренний `s_noise`. Поэтому патч способен влиять не на одну точку графа, а на несколько шумовых механизмов sampling.

Реализация предполагает, что класс original принимает `model_config`, имеет `shift`, `multiplier`, `set_parameters` и `set_noise_scale`. Общий тип `MODEL` этого не гарантирует.

## 6. Параметры и настройка

Для HiDream‑O1 base используйте проверенное `8.0`; официальный dev шаблон использует `7.6`. Не переносите эти числа на другую модель по сходству названия. Сначала найдите значение в официальной конфигурации или workflow конкретного checkpoint.

Значение `0.0` разрешено схемой, но означает полное обнуление scale в местах, где он множит noise; это не универсальный режим «без шума» и может нарушить предпосылки модели. `1.0` — нейтральный default поля, но не обязательно правильная training scale.

## 7. Проверенный пример

Recipe `HiDream‑O1 base: noise scale и scheduler` воспроизводит подтверждённый участок `image_hidream_o1.json`: внешний MODEL входит в `ModelNoiseScale(8.0)`, затем patched MODEL подключается к `BasicScheduler(scheduler = normal, steps = 40, denoise = 1.0)`.

В dev workflow та же нода имеет `7.6`, scheduler — `normal, 28, 1`. Полный census нашёл ровно два root-экземпляра и ни одного subgraph. Exact-source probe с совместимым fake sampling class подтвердила clone, перенос `shift/multiplier`, замену scale и неизменность исходной модели. Настоящие веса HiDream‑O1 не загружались.

## 8. Частые ошибки

- Воспринимают `noise_scale` как множитель прежнего значения. Это абсолютная замена.
- Ставят ноду на любую MODEL, не проверив API её `model_sampling`.
- Патчат модель после создания SIGMAS другой веткой и получают рассогласованную sampling-конфигурацию.
- Берут `7.5` из tooltip и называют его значением официального dev workflow; в версии 0.1.42 сохранено `7.6`.
- Считают, что патч затрагивает только начальный noise scaling; scale читают и некоторые samplers.
- Ожидают, что все нестандартные поля original sampling автоматически перенесутся. Явно копируются только `shift` и `multiplier` после конструктора.

## 9. Ограничения и производительность

Сама нода дешева: она клонирует patcher и пересоздаёт небольшой sampling-объект, а не прогоняет модель. Основной риск — семантический, а не вычислительный: неверный scale меняет всю траекторию sampling.

Порядок model patches важен. Если другая нода уже заменила `model_sampling` подклассом с дополнительным состоянием или нестандартным конструктором, `ModelNoiseScale` может потерять его либо завершиться ошибкой. После неё другой patch также способен снова заменить scale.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не помечена experimental или deprecated и не имеет formal replacement.

Embedded docs передаёт общую задачу и tooltip, но не описывает реконструкцию sampling-класса, перенос только двух полей, влияние на sampler `s_noise` и расхождение dev tooltip `7.5` с официальным widget `7.6`.

- [ModelNoiseScale в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L310-L330)
- [ModelSamplingDiscreteFlow и CONST](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L86-L103)
- [HiDream‑O1 default noise scale](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/supported_models.py#L1653-L1664)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

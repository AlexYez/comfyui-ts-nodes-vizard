# SamplerCustom: custom sampling с обычным CFG

`SamplerCustom` собирает в одной исполняющей ноде модель, positive и negative conditioning, CFG, начальный шум, алгоритм `SAMPLER`, расписание `SIGMAS` и исходный `LATENT`. В отличие от `SamplerCustomAdvanced`, генератор шума и guider здесь встроены в контракт.

## 1. Что делает нода

Нода запускает custom sampling через стандартный CFG-путь ComfyUI. При `add_noise = true` она создаёт воспроизводимый случайный шум из `noise_seed`; при `false` создаёт нулевой тензор той же формы. Затем вызывает выбранный sampler на переданном расписании.

На выходе доступны итоговый latent и последнее предсказание чистого latent `x0`, если sampler передал его через callback. Это два представления одного запуска, а не два последовательных прохода модели.

## 2. Место в графе

До ноды обычно находятся checkpoint/model patch, conditioning, `KSamplerSelect` и scheduler. После неё ставят VAE Decode, сохранение результата или следующую latent-стадию.

`SamplerCustom` удобен, когда нужен раздельный выбор sampler и scheduler, но не требуется собирать NOISE и GUIDER вручную. Для нестандартного guider, отключаемого объекта шума или сложной композиции компонентов лучше использовать `SamplerCustomAdvanced`.

## 3. Входы

- `model` — модель, которой выполняется denoising.
- `add_noise` — случайный шум при `true`, нули при `false`.
- `noise_seed` — seed генератора; frontend может менять число между очередями.
- `cfg` — сила обычного positive/negative classifier-free guidance.
- `positive`, `negative` — две ветви `CONDITIONING`.
- `sampler` — алгоритм типа `SAMPLER`.
- `sigmas` — последовательность уровней шума.
- `latent_image` — начальный latent; может содержать `noise_mask`, `batch_index` и служебные metadata.

Параметры sampler и scheduler не дублируются внутри ноды: их нужно собрать отдельными узлами.

## 4. Выходы

- `output` — итоговый `LATENT` после sampling.
- `denoised_output` — последний доступный `x0`, обработанный `process_latent_out`; если callback не получил `x0`, возвращается тот же объект, что и `output`.

`denoised_output` не означает дополнительный прогон шумоподавления и не гарантирует визуально более «чистую» картинку. Это оценка clean sample из последнего callback конкретного sampler. Оба выхода наследуют metadata исходного словаря, но служебные ключи `downscale_ratio_spacial` и `downscale_ratio_temporal` удаляются из результатов.

## 5. Как работает

Сначала код при необходимости исправляет пустой latent под ожидаемое число каналов модели и её пространственный/временной коэффициент downscale. Затем выбирает `Noise_RandomNoise(noise_seed)` либо `Noise_EmptyNoise`, извлекает `noise_mask` и создаёт callback на `len(sigmas) - 1` шагов.

`comfy.sample.sample_custom` строит стандартный CFG guider из model, positive, negative и `cfg`. Сам sampler получает шум, latent, SIGMAS, mask, callback и seed. Seed передаётся в sampling-путь даже при `add_noise = false`: некоторые model options, wrappers или callback-механизмы могут использовать его независимо от начального тензора.

Если список `SIGMAS` пуст, низкоуровневый guider возвращает исходный latent без sampling. Это аварийно допустимый путь, а не полезное расписание для генерации.

## 6. Параметры и настройка

Для text-to-image обычно оставляют `add_noise = true`. Значение `false` нужно для продолжения уже подготовленного latent или стадий, где повторно добавлять стартовый шум нельзя. Оно не отключает вызов sampler: нулевой NOISE всё равно проходит через тот же pipeline.

CFG следует брать из проверенного workflow конкретной модели. Низкое значение не универсально лучше или хуже: Turbo/flow-модели могут ожидать около 1, а классические SD-пайплайны часто используют более высокие значения. Число шагов задаётся длиной `SIGMAS`; поле `noise_seed` не заменяет расписание.

## 7. Проверенный пример

Recipe `SDXL Turbo: custom sampling в один шаг` повторяет официальный участок `sdxlturbo_example`: `KSamplerSelect(euler_ancestral)`, `SDTurboScheduler(steps = 1, denoise = 1)`, `SamplerCustom(add_noise = true, noise_seed = 0, cfg = 1)`. Positive, negative, latent и одна и та же модель подаются извне.

В workflow templates 0.1.42 найден 21 экземпляр `SamplerCustom`: 5 в root и 16 в subgraph, все активны в mode 0. Exact-source проба отдельно проверяет ветви random/zero noise, передачу mask/seed/CFG, metadata, удаление downscale-ключей и `x0`; полный запуск SDXL Turbo с весами не выполнялся.

## 8. Частые ошибки

- Считают `add_noise = false` командой пропустить sampler. Она лишь заменяет стартовый шум нулями.
- Подключают обычный tensor или LATENT в порт `sampler`; требуется объект `SAMPLER`.
- Передают несовместимые `SIGMAS` от scheduler другого модельного семейства.
- Принимают `denoised_output` за второй, улучшенный результат отдельного прохода.
- Забывают, что `noise_mask` из LATENT ограничивает область воздействия.
- Подают модель в scheduler, но не в сам `SamplerCustom`, либо наоборот.
- Меняют seed при `add_noise = false` и считают любое отличие доказательством скрытого случайного шума; seed может использоваться другими частями sampling-пути.

## 9. Ограничения и производительность

Основная стоимость — модельные вызовы на каждом переходе SIGMAS. Память зависит от формы latent, batch, модели, CFG и промежуточного `x0`. Callback сохраняет последнюю оценку clean sample на CPU перед сборкой второго выхода, поэтому крупные video latent могут добавить заметную передачу и память.

Нода бережно копирует словарь metadata, но не является общим валидатором его согласованности. Устаревшие `noise_mask`, `batch_index` или размерные metadata после пользовательских latent-операций способны изменить поведение. Empty-latent repair рассчитан на поддерживаемые ComfyUI model contracts, а не на произвольные словари.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не experimental и не deprecated; formal replacement отсутствует.

Embedded docs перечисляет порты, но расплывчато называет `cfg` «конфигурацией» и описывает `denoised_output` как результат отдельного шумоподавления. В runtime это обычная сила CFG и последнее callback-предсказание `x0`. Поведение noise, mask, metadata и пустого SIGMAS проверено по коду.

- [SamplerCustom в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L741-L805)
- [sample_custom](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sample.py#L78-L83)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

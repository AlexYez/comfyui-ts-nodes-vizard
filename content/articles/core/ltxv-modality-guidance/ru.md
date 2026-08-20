# LTXVModalityGuidance: усилить связь между видео и аудио

## Что делает нода

`LTXVModalityGuidance` клонирует `MODEL` и добавляет post-CFG callback для LTXV-AV sampling. На активных шагах callback выполняет ещё один conditional pass с двумя выключенными флагами transformer:

- `a2v_cross_attn = false` отключает передачу audio → video;
- `v2a_cross_attn = false` отключает передачу video → audio.

Основной conditional prediction сохраняет обе связи. Дополнительный `mod_pred` показывает, что модель предсказывает без межмодального обмена. Итог рассчитывается так:

```text
cfg_result + (cond_pred - mod_pred) × (modality_scale - 1)
```

При default `modality_scale = 3` разность добавляется с коэффициентом `2`. Нода не меняет conditioning и не создаёт `GUIDER`: на выходе остаётся cloned `MODEL` с дополнительной логикой sampling.

Флаги читаются внутри LTXV-AV transformer block. Если audio stream пуст, ветвь audio → video и без того не запускается. На модели без этих переключателей extra pass может оказаться бесполезным, хотя тип сокета `MODEL` соединение разрешит.

## Когда использовать и когда не использовать

Нода предназначена для совместной генерации видео и аудио LTXV-AV, когда результат должен сильнее опираться на связь двух потоков — например, при синхронизации видимой речи и звука. Это направление следует из runtime description; конкретное улучшение нужно проверять на выбранной модели, prompt и seed.

Не применяйте её к video-only LTXV как универсальный «улучшатель качества». Там нет полноценной пары audio/video streams, ради которой отключаются `a2v` и `v2a`. Тип `MODEL` не отличает LTXV-AV от других архитектур.

Значение `1` отключает guidance и не выполняет extra pass. Меньше единицы schema не разрешает, поэтому нода не умеет направлять prediction в обратную сторону. Очень большой scale допустим до `100`, но исходник не ограничивает амплитуду результата и не проверяет конечность tensor.

`start_percent` и `end_percent` полезны, если дополнительный проход нужен только на части sampling. При перепутанном порядке интервал обычно становится пустым: percent преобразуется в sigma, а callback требует одновременно `sigma ≤ sigma_start` и `sigma ≥ sigma_end`.

## Короткий рецепт подключения

Приложенный fragment собран по source-контракту:

1. Подайте LTXV-AV `MODEL` в `LTXVModalityGuidance`.
2. Начните с `modality_scale = 3`, полного интервала `0…1`.
3. Передайте выходной `MODEL` в `LTXVDualCFGGuider`.
4. Подключите positive и negative conditioning той же LTXV-AV цепочки.
5. Используйте полученный `GUIDER` с nested audio-video latent в `SamplerCustomAdvanced`.

Связка с Dual CFG прямо разрешена runtime description и механизмом callback stacking, но точного `LTXVModalityGuidance` в официальном wheel 0.1.42 нет. Поэтому fragment не копирует неизвестные weights, scheduler или latent-конструктор и не называется официальным workflow.

Для сравнения сначала выполните тот же seed с `modality_scale = 1`, затем верните `3`. Так меняется только эта guidance-добавка; остальные параметры остаются сопоставимыми.

## Входы, выходы и параметры

- `model` — обязательный `MODEL`. Нода вызывает `clone()` и не должна менять входную ветвь.
- `modality_scale` — `FLOAT` от `1` до `100`, default `3`, шаг `0.1`, округление UI до `0.01`.
- `start_percent` — advanced `FLOAT` от `0` до `1`, default `0`, шаг `0.001`.
- `end_percent` — advanced `FLOAT` от `0` до `1`, default `1`, шаг `0.001`.
- `MODEL` — cloned model patcher с добавленным post-CFG callback.

Percent не сравнивается с номером шага напрямую. При создании ноды текущий `model_sampling` переводит обе границы в sigma через `percent_to_sigma`. На каждом callback берётся только первое значение `sigma`: `args["sigma"][0].item()`.

Границы включены. Callback пропускает работу только при `sigma > sigma_start` или `sigma < sigma_end`; равенство остаётся активным. Параметры не меняются динамически после создания patched model.

## Типовые связки

Ожидаемая AV-цепочка выглядит как `LTXV-AV MODEL → LTXVModalityGuidance → LTXVDualCFGGuider → SamplerCustomAdvanced`. Positive и negative идут в guider отдельно, а nested latent содержит video и audio streams.

Ноду можно поставить рядом с `LTXVSpatioTemporalGuidance`. Обе используют `set_model_sampler_post_cfg_function`, который добавляет callback в существующий список, а не заменяет его. На шаге, где активны обе, sampler выполняет два дополнительных conditional pass: один без межмодального cross-attention, другой с perturbed self-attention выбранных блоков.

`ModelSamplingLTXV` меняет sigma-математику модели и решает другую задачу. Если оба patch применяются, scheduler и guider должны получать финальную ветвь `MODEL`, иначе части графа будут опираться на разные model options.

Полный рекурсивный просмотр wheel 0.1.42 охватил 512 JSON, 496 root и 768 root/subgraph графов. Точный NodeId `LTXVModalityGuidance` не встретился ни разу; serialized widgets и реальная official topology для него отсутствуют.

## Практический пример

Model-free exact-source probe использовал условные значения:

```text
cfg_result = 2
cond_pred = 4
mod_pred = 1
modality_scale = 3
```

Callback вернул `2 + (4 − 1) × 2 = 8`. В переданную копию `model_options` были записаны оба флага `false`, а существующее поле transformer options сохранилось. Исходный словарь options не изменился.

Та же проба настроила percent `0.2…0.8`; тестовый sampler переводил их в sigma `8…2`. При sigma `5` extra pass выполнился, при sigma `9` callback вернул исходный `denoised` и не вызвал модель. Scale `1` также вернул исходный tensor без дополнительного вызова.

Отдельная проверка последовательно поставила modality guidance и STG на один model patcher. В финальной модели оказалось два callback. Это подтверждает stacking механически, но не оценивает качество видео или синхронизацию: веса LTXV-AV не загружались.

## Частые ошибки и способы проверки

**Результат не меняется.** Проверьте, что `modality_scale` больше `1`, sigma попадает в интервал и модель действительно поддерживает `a2v_cross_attn`/`v2a_cross_attn`. На video-only либо несовместимой модели разность может быть близка к нулю.

**Sampling стал заметно медленнее.** На каждом активном шаге появляется полный дополнительный conditional pass. Сузьте percent-интервал или установите scale `1` для контрольного запуска.

**Интервал не срабатывает.** Убедитесь, что `start_percent ≤ end_percent`. Нода не исправляет перепутанные границы и не сообщает о пустом диапазоне.

**Вторая patch-нода будто потерялась.** Соедините patch последовательно и передайте в guider выход последней ноды. Параллельные ветви `MODEL` не объединяются сами.

**Ожидался отдельный GUIDER.** Эта нода возвращает `MODEL`. Guider создаётся следующей нодой, например `LTXVDualCFGGuider`.

**Большой scale даёт нестабильный результат.** Формула не содержит rescale или clamp. Снижайте scale и сравнивайте при одинаковом seed; проверка интерфейсного диапазона не гарантирует устойчивость модели.

## Производительность и внутреннее поведение

Создание ноды дешёвое: клонируется model patcher и регистрируется Python callback. Веса модели при этом не дублируются как независимый checkpoint, но model options расходятся между ветвями.

Основная цена появляется в sampler. Обычный CFG уже вычисляет conditional и при необходимости unconditional prediction. Modality guidance добавляет ещё один conditional вызов `calc_cond_batch` на каждом активном шаге. Полный интервал приблизительно добавляет один model forward на шаг; точное относительное замедление зависит от CFG optimization и других patches.

Callback копирует только верхний `model_options` и вложенный `transformer_options`, затем меняет два boolean. Conditioning и входной tensor передаются в extra pass без клонирования на уровне этого кода.

Post-CFG callbacks выполняются по порядку списка. Каждый следующий получает `denoised`, возвращённый предыдущим, но те же `cond_denoised`, sigma и input. При stacking стоимость складывается даже тогда, когда итоговые поправки малы.

## Совместимость, изменения и устаревание

Контракт сверён с ComfyUI 0.32.0 и frontend 1.48.7. Нода активна, не experimental, не deprecated, не `api_node` и не `dev_only`. Node Replacement API не содержит alias или замены.

Runtime fingerprint: `sha256:c5f9451a382e5e1ac47bb08bfce0c55102153926e2a3098deb0efca3b891e747`. Он фиксирует параметры и флаги, но не внутренние названия `a2v_cross_attn` и `v2a_cross_attn`; их нужно повторно читать в исходнике после обновления.

В embedded docs 0.5.9 папки `LTXVModalityGuidance` нет ни для `en`, ни для `ru`. Поэтому статья не приписывает этой версии документации отсутствующие объяснения и опирается на pinned source, `/object_info` и model-free probe.

Изменение реализации LTXV-AV transformer switches, `percent_to_sigma` или post-CFG API может поменять смысл без заметного изменения интерфейса. Эти три участка входят в проверку совместимости материала.

## Связанные ноды и источники

- `LTXVSpatioTemporalGuidance` создаёт другой perturbed pass — с изменённым self-attention выбранных блоков.
- `LTXVDualCFGGuider` применяет разные CFG к video и audio частям packed latent.
- `SamplerCustomAdvanced` принимает готовый `GUIDER`, noise, sampler, sigmas и nested latent.
- `ModelSamplingLTXV` меняет sampling schedule объекта `MODEL`, а не межмодальную поправку.

Формула и отключённые режимы сверены по `nodes_lt.py`; фактическое чтение a2v/v2a flags — по `av_model.py`; stacking — по `model_patcher.py`. В официальном workflow wheel точных cases нет, поэтому приложенный fragment остаётся source-derived и имеет `exampleExecuted=false`.

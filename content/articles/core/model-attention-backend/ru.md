# ModelAttentionBackend: закрепить attention-функцию для MODEL

`ModelAttentionBackend` клонирует модель и записывает в её transformer options конкретную attention-функцию. В ComfyUI 0.32.0 нода предлагает PyTorch attention и, когда локальная сборка поддерживает её, Comfy Kitchen int8 attention.

## Что делает нода

Выбор переводится во внутреннее имя: `pytorch` или `comfy_kitchen_int8`. Функция ищется в реестре attention backend, затем модель получает `optimized_attention_override`.

Нода не меняет глобальный CLI backend всего ComfyUI. Override относится к cloned `MODEL` и тем transformer-блокам, которые читают соответствующую опцию. CLIP, VAE и другие отдельные модели не обязаны использовать его.

## Место в графе

Ставьте patch после загрузки diffusion-модели и до guider/sampler. Последующие model patches должны идти от его выхода. Если позже другая нода снова вызывает `set_model_optimized_attention`, последнее значение заменяет предыдущее в `transformer_options`.

Для сравнения backend держите остальные настройки одинаковыми: checkpoint, seed, latent, sampler, scheduler и dtype. Иначе нельзя отделить эффект attention от других изменений.

## Входы

- `model` — исходный `MODEL`.
- `attention` — `pytorch attention` и, при доступности, `comfy kitchen attention`.

Список строится при запросе `INPUT_TYPES`. Comfy Kitchen появляется только если `comfy_kitchen.int8_attention_is_available()` вернул true. Поэтому набор вариантов зависит от установленной сборки и может отличаться между машинами.

## Выход

Выход — cloned `MODEL` с override attention. Исходная ветвь сохраняет выбранный глобально backend. В реальном `ModelPatcher` функция оборачивается так, чтобы transformer-код мог передать служебный первый аргумент, а при наличии переносится `container_function`.

Нода не возвращает метрики и не сообщает, действительно ли каждый блок вызвал override. Проверка результата требует запуска модели и профилирования на целевом устройстве.

## Как выбирается backend

`pytorch attention` соответствует зарегистрированной функции `attention_pytorch`. `comfy kitchen attention` соответствует `attention_comfy_kitchen_int8`; функция регистрируется только при доступной int8-реализации Comfy Kitchen.

`VALIDATE_INPUTS` всегда возвращает true. Поэтому программный вызов может передать неизвестную строку или kitchen-вариант на несовместимой установке. Lookup вернёт `None`, нода напишет warning и поставит PyTorch attention. Это безопасный fallback, но не строгая ошибка конфигурации.

## Параметры и настройка

PyTorch — предсказуемый диагностический выбор, когда нужно исключить влияние автоматически выбранного backend. Comfy Kitchen int8 имеет смысл тестировать только при явной доступности и на реальном workflow; название int8 само по себе не доказывает ускорение, меньшую VRAM или одинаковую численную точность.

Сравнивайте прогрев и несколько повторов, peak memory и output на фиксированном seed. Первый запуск может включать компиляцию, аллокации или загрузку, поэтому единичное время вводит в заблуждение.

## Проверенный пример

Fragment Wizard ставит `pytorch attention` и ведёт patched модель в `CFGGuider`. Positive и negative conditioning остаются внешними. Это воспроизводимый baseline, а не рекомендация использовать PyTorch на любом устройстве.

В 512 JSON official wheel 0.1.42 нода не встречается. Probe зарегистрировал две подставные attention-функции, подтвердил правильный выбор, динамическое отсутствие kitchen-варианта и fallback неизвестной строки в PyTorch. Реальные CUDA kernels и diffusion-модель не запускались. Редактор пока не проверил материал вручную.

## Частые ошибки

- Ожидается глобальная смена backend для CLIP, VAE и всех моделей.
- Kitchen-вариант переносится на машину, где он не зарегистрирован; фактически срабатывает PyTorch fallback.
- Warning пропускается, и пользователь думает, что тестирует int8.
- Две attention patch-ноды ставятся подряд; последняя перезаписывает override.
- Скорость сравнивается по одному холодному запуску.
- Разница output автоматически считается ошибкой без оценки допустимой численной погрешности.

## Ограничения и производительность

Сам patch почти бесплатен. Производительность определяется выбранной attention-функцией, формой тензоров, dtype, устройством и моделью. Ни source, ни UI не дают универсального рейтинга двух вариантов.

Override действует только там, где модель передаёт `transformer_options` и использует optimized attention contract. Специализированный блок может вызывать другую функцию напрямую. Нода не выполняет capability-test на конкретной форме до inference.

## Совместимость и источники проверки

Проверено на ComfyUI 0.32.0 и frontend 1.48.7. В чистом снимке `/object_info` были доступны оба варианта, но это свойство проверочной среды, а не обязательный общий контракт. Source не помечает ноду deprecated или experimental; формальной замены нет.

Embedded docs 0.5.9 не содержат директории `ModelAttentionBackend`. Статья основана на node source, реестре attention и точной реализации override в `ModelPatcher`.

### Источники

- [ModelAttentionBackend в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L352-L383)
- [Реестр attention-функций](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/modules/attention.py#L54-L75)
- [Регистрация core attention backends](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/modules/attention.py#L855-L899)
- [ModelPatcher attention override](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L688-L695)

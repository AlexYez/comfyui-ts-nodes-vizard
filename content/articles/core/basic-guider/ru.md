# BasicGuider: один условный проход без CFG

## Что делает нода

`BasicGuider` собирает объект `GUIDER` из `MODEL` и одного `CONDITIONING`. Внутренний класс наследует обычный `CFGGuider`, но записывает только ключ `positive`; коэффициент остаётся равным базовому значению `1.0`.

При стандартном sampling это означает один условный прогноз модели. Отрицательной ветви нет, смешивать два прогноза по CFG-формуле не с чем. Conditioning при этом не исчезает: именно оно направляет единственный проход.

Нода ничего не сэмплирует сама. Она настраивает стратегию предсказания шума, которую затем принимает `SamplerCustomAdvanced`.

## Когда использовать и когда не использовать

Используйте `BasicGuider`, когда модели или графу нужен только один conditional-проход: например, guidance уже записан в conditioning отдельной нодой, либо архитектура рассчитана на sampling без классической positive/negative пары.

Не выбирайте её лишь ради ускорения обычного CFG-графа, если negative prompt нужен модели по смыслу. Он здесь не принимается вообще. Для классической пары используйте `CFGGuider`; при `cfg = 1` тот тоже обычно пропускает negative-проход, но сохраняет привычный интерфейс и может иначе взаимодействовать с CFG hooks.

`BasicGuider` не равен «безусловной генерации». Единственный вход `conditioning` остаётся условием модели.

## Короткий рецепт подключения

1. Подайте совместимый `MODEL` во вход `model`.
2. Подключите подготовленное `CONDITIONING` во вход `conditioning`.
3. Соедините выход `GUIDER` со входом `guider` ноды `SamplerCustomAdvanced`.
4. Отдельно передайте sampler, sigmas, noise и latent.
5. Проверьте, что выбранная модель действительно рассчитана на один conditional-проход.

Fragment «BasicGuider перед SamplerCustomAdvanced» повторяет официальную форму связи. Он содержит внешние MODEL, CONDITIONING, NOISE, SAMPLER, SIGMAS и LATENT, поэтому не привязан к одному семейству моделей. Схема и типы портов проверены; fragment не выполнялся.

## Входы, выходы и параметры

`model: MODEL` и `conditioning: CONDITIONING` обязательны. Настраиваемого `cfg` и negative-входа нет. Дескрипторы обоих входов не добавляют числовых ограничений или widgets.

Выход один: `GUIDER`, не list-output. Это Python-объект с model patcher и подготовленным условием; он не является LATENT или MODEL и подключается только к нодам custom sampling, которые принимают `GUIDER`.

Runtime ID — `BasicGuider`, а не имя внутреннего класса `Guider_Basic`. Исторических execution aliases не зафиксировано.

## Типовые связки

Базовая цепочка: `MODEL + CONDITIONING → BasicGuider → SamplerCustomAdvanced`. В официальном Flux Redux `MODEL` приходит из `ModelSamplingFlux`, а conditioning — из второй `StyleModelApply`.

В других закреплённых шаблонах источниками conditioning служат `FluxGuidance`, `LotusConditioning`, `ReferenceLatent` и ноды семейства MiniMax. Это подтверждает, что `BasicGuider` не кодирует текст и не задаёт guidance сам: он принимает уже подготовленное условие.

Один `GUIDER` можно использовать в одном custom-sampling узле. Для сравнения стратегий соберите отдельные ветви с одинаковыми noise, sigmas и latent.

## Практический пример

Полный census `comfyui-workflow-templates-json 0.1.42` охватил 512 JSON, все root nodes и 272 subgraphs. Найдены 14 `BasicGuider` в 14 файлах и 10 разных top-level UUID: 3 ноды в root и 11 в subgraphs. Все имеют mode 0 и пустой `widgets_values`.

Во всех 14 случаях выход `GUIDER` напрямую подключён к `SamplerCustomAdvanced.guider`. Вход model чаще всего приходит от `UNETLoader` — 9 связей; conditioning чаще всего от `LotusConditioning` — 5 связей.

Показательный `flux_redux_model_example`, UUID `06010f12-03bc-41ce-86bd-14f321d5a152`: `ModelSamplingFlux #30 → BasicGuider #22.model`, `StyleModelApply #45 → #22.conditioning`, затем `#22.GUIDER → SamplerCustomAdvanced #13`. Проверена сериализованная структура, модели не запускались.

## Частые ошибки и способы проверки

**Ищут negative-вход.** Его нет в runtime schema. Если отрицательная ветвь обязательна, замените ноду на `CFGGuider`.

**Считают, что conditioning игнорируется при cfg 1.** Стандартная оптимизация убирает только unconditional-проход; conditional-прогноз остаётся результатом.

**Подключают GUIDER к KSampler.** Обычный `KSampler` принимает MODEL и conditioning напрямую. `GUIDER` предназначен для custom sampling.

**Дублируют guidance.** Если upstream-нода уже внедрила свою шкалу, добавление классического CFG в другой ветви может изменить результат. Сверьте рекомендованный граф модели.

**Сравнивают разные noise или sigmas.** Для честного сравнения Basic и CFG фиксируйте остальные входы sampler.

## Производительность и внутреннее поведение

При обычной конфигурации выполняется один прогноз модели на шаг. Это дешевле классического CFG с conditional и unconditional ветвями, хотя фактическая экономия зависит от batching, hooks и дополнительных моделей внутри conditioning.

Базовый `CFGGuider` хранит `cfg = 1.0`. Sampling function при этом передаёт `None` вместо unconditional condition, если `disable_cfg1_optimization` не установлен. У `BasicGuider` negative condition отсутствует изначально, поэтому отдельного отрицательного прогноза всё равно нет.

Подготовка conditions, загрузка модели, sigmas и denoise остаются обязанностью custom sampler. Сама нода создаёт небольшой объект и не запускает tensor-вычисления.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `BasicGuider`, модуле `comfy_extras.nodes_custom_sampler`. Fingerprint: `sha256:0683f804654dbd15bdb740dc4f39c976b85b4fbe388d6e21310926d1855525be`.

Runtime flags `deprecated`, `experimental`, `dev_only` и `api_node` равны false; нода не является output node. В `node-replacements` 0.32.0 её ID отсутствует.

Embedded docs 0.5.9 перечисляют два входа и GUIDER, но не объясняют наследуемый cfg=1, отсутствие unconditional condition и реальную экономию прохода. Эти детали сверены с исходником.

## Связанные ноды и источники

`CFGGuider` добавляет negative condition и числовой cfg. `DualCFGGuider` смешивает три прогноза. `CLIPTextEncode` — один из способов получить CONDITIONING. Фактическим consumer выхода служит `SamplerCustomAdvanced`, статья о котором ещё не подготовлена.

- [Реализация `BasicGuider`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L805-L829)
- [CFG-формула и оптимизация cfg=1](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Embedded docs 0.5.9 для `BasicGuider`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/BasicGuider/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

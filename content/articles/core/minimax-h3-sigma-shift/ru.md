# MiniMaxH3SigmaShift: согласованные sigma-сдвиги видео и аудио

## Что делает нода

`MiniMaxH3SigmaShift` создаёт копию `MODEL` MiniMax H3 и заменяет в ней объект sampling на сочетание `ModelSamplingAV` и `CONST`. Параметр `shift_video` задаёт flow-преобразование общей sigma-сетки sampler. `shift_audio` задаёт отдельное расписание аудиопотока, согласованное с этой сеткой.

Для базовой доли времени `t` video sigma вычисляется так:

```text
sigma_video = shift_video × t / (1 + (shift_video − 1) × t)
```

Модель получает video sigma, обращает это преобразование до общей базовой сетки и применяет к ней `shift_audio`. Одновременно `ModelSamplingAV.audio_scale` становится `shift_video / shift_audio`; при исходных `12 / 3` это `4`. Так audio latent переносится на video schedule и возвращается к собственному расписанию внутри MiniMax H3 DiT.

## Когда использовать и когда не использовать

Нода предназначена для MiniMax H3 joint audio-video model. Она нужна, когда вы осознанно меняете flow-shift или хотите явно закрепить исходную пару `12` для видео и `3` для аудио. Эти значения также записаны в pinned model config ComfyUI.

Не применяйте её к обычной image diffusion model. Порт `MODEL` не подтверждает наличие MiniMax H3 audio stream; patch создаст `ModelSamplingAV` независимо от семейства. Также не переносите пару `12 / 3` на LTX, Flux или SD3: у них другой sampling-контракт.

Если workflow уже загружает MiniMax H3 с исходными sampling settings и не требует изменения, нода может быть избыточна. В официальном wheel 0.1.42 exact `MiniMaxH3SigmaShift` не найден ни в одном из 512 JSON и вложенных subgraph, поэтому здесь нет подтверждённого workflow preset сверх значений в source.

## Короткий рецепт подключения

1. Загрузите MiniMax H3 `MODEL` совместимым loader.
2. Подайте его в `MiniMaxH3SigmaShift`.
3. Для контрольной точки оставьте `shift_video = 12` и `shift_audio = 3`.
4. Используйте выходной `MODEL` одновременно в guider и scheduler той же sampling-ветви.
5. Меняйте только один shift за опыт и сохраняйте seed, prompt, длительность и остальные параметры.

Fragment «MiniMax H3: исходные sigma-shift» содержит patch-ноду с точными defaults и внешний вход `MODEL`. Полного workflow нет: pinned official wheel ещё не даёт реального случая exact NodeId, а MiniMax H3 веса не исполнялись.

## Входы, выходы и параметры

`model` — обязательный `MODEL`. Метод вызывает `clone()`, поэтому исходный model patcher не должен измениться.

`shift_video` — `FLOAT` от `0.01` до `100`, шаг `0.01`, default `12`. Он формирует зарегистрированный tensor из 1000 sigma и определяет расписание sampler. Чем больше shift при одной базовой точке `t`, тем выше sigma, кроме крайних `t = 0` и `t = 1`.

`shift_audio` — `FLOAT` с тем же диапазоном и шагом, default `3`. Он не строит вторую независимую sigma-последовательность на уровне sampler. MiniMax H3 выводит audio sigma из текущей video sigma аналитически.

Выход — новый `MODEL`. Если исходный sampling имел `noise_scale`, значение переносится. В `transformer_options` записываются оба shift, чтобы DiT использовал те же числа, что sampling patch.

## Типовые связки

После patch один и тот же выходной `MODEL` должен питать части custom sampling-графа, которые зависят от модели: `CFGGuider` и `BasicScheduler`. Затем guider, sigmas, выбранный sampler, noise и joint latent сходятся в `SamplerCustomAdvanced`.

Если scheduler подключён к исходному model, а guider — к patched model, graph формально проходит type-check, но sigma schedule и модельный контракт расходятся. Держите один выход patch-ноды источником обеих ветвей.

Для MiniMax H3 важно не отделять аудио и видео перед sampling, если модель ожидает packed AV latent. Нода патчит именно согласование joint stream; она не создаёт audio latent, conditioning или noise.

## Практический пример

Exact-source probe создал `ModelSamplingAV + CONST` без весов и применил пару `12 / 3`. Получился `audio_scale = 4`, унаследованный `noise_scale = 2.5`, 1000 зарегистрированных sigma и отдельная копия `transformer_options`; исходный словарь options остался без новых ключей.

Для базовых точек `[0.1, 0.5, 0.9]` probe получил:

```text
video sigma: [0.5714286, 0.9230769, 0.9908257]
audio sigma: [0.25,      0.75,      0.9642857]
```

Обращение video shift и повторное применение audio shift совпали с прямым расчётом от базовой сетки. При равных shift преобразование video → audio стало тождественным, а `audio_scale` было бы равно `1`.

## Частые ошибки и способы проверки

**Звук и видео расходятся по времени или дают нестабильный результат.** Проверьте, что оба shift пришли из одной patch-ноды и тот же patched `MODEL` используется scheduler и guider.

**Результат изменился уже при defaults.** Loader мог исходно содержать другие sampling settings. Нода явно заменяет sampling на `12 / 3`, хотя defaults совпадают с pinned MiniMax H3 config ComfyUI 0.32.0. Сверьте config конкретных весов.

**Параметры поставлены равными в надежде «усилить аудио».** При `shift_video = shift_audio` `audio_scale = 1`, а audio sigma совпадает с video sigma. Это отключает различие расписаний, а не отдельно усиливает звук.

**Применена другая архитектура MODEL.** Runtime не проверяет class family. Ищите MiniMax H3 loader и совместимый joint AV latent; ошибка может появиться только глубже в sampling.

**Не видно отличий от смены одного числа.** Shift меняет всю кривую, но качество зависит от модели, schedule, steps и conditioning. Сравнивайте с фиксированным seed и меняйте один параметр.

## Производительность и внутреннее поведение

Сама нода не запускает DiT. Она создаёт model clone, tensor из 1000 sigma и несколько небольших словарей; эти затраты малы рядом с одним sampling-шагом.

Главное последствие проявляется в runtime модели. Аудиопоток переносится как масштабированный latent на video schedule. Перед DiT MiniMax H3 вычисляет audio sigma из video sigma, снимает carry scaling, а после forward переводит audio velocity обратно. Оба shift также задают разные внутренние timesteps `t_v = 1 − sigma_v` и `t_a = 1 − sigma_a`.

Нода копирует `transformer_options` перед добавлением ключей. Это защищает исходную модель от прямого изменения этого вложенного словаря. Однако patched model остаётся model patcher со всеми обычными расходами загрузки весов при последующем sampling.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7` и модуля `comfy_extras.nodes_minimax_h3`. Runtime fingerprint: `sha256:25fc0535f0b075c09d0bedfc70856ffd7ac46f9c71f5dcd7bfbb04868983cec0`.

Нода не experimental, deprecated, dev-only и не API node. Display name — `ModelSamplingMiniMaxH3`; runtime search aliases — `sigma shift` и `minimax shift`. Это поисковые имена, не aliases идентификации статьи. Node Replacement API не содержит записи.

Embedded docs 0.5.9 для exact NodeId отсутствуют. Факты взяты из node source, `ModelSamplingAV`, MiniMax H3 forward и pinned runtime. После обновления нужно отдельно сверять model defaults, transformer-option keys и formula: схема двух float может остаться прежней при изменении внутренней математики.

## Связанные ноды и источники

`BasicScheduler` строит `SIGMAS` по patched sampling object, `CFGGuider` использует тот же `MODEL`, а `SamplerCustomAdvanced` объединяет sampling-компоненты. Эти связи уже имеют статьи. Специализированные MiniMax H3 loader/conditioning nodes ещё не описаны и потому не добавлены как manifest targets.

- [Реализация `MiniMaxH3SigmaShift`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_minimax_h3.py#L283-L324)
- [`ModelSamplingAV` и flow-shift](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L279-L347)
- [Преобразование audio sigma внутри MiniMax H3](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/minimax/model.py#L1-L39)
- [Официальные workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

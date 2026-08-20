# TrimVideoLatent: убрать начальные temporal-срезы LATENT

## Что делает нода

`TrimVideoLatent` копирует словарь LATENT и заменяет только `samples` выражением `samples[:, :, trim_amount:]`. Для обычной пятиосевой формы video latent `[B, C, T, H, W]` нода убирает первые `trim_amount` элементов latent-времени `T`.

Это не обязательно то же число, что у декодированных кадров. В Wan VACE temporal-ось формируется с учётом VAE compression, а `WanVaceToVideo` сам вычисляет служебное значение `trim_latent`. Его и следует подключать к `trim_amount`.

Срез возвращается как view общего storage, а не как clone. `noise_mask`, `batch_index` и другие поля остаются без изменений, даже если у них есть собственная временная ось.

## Когда использовать и когда не использовать

Официальная позиция ноды в Wan VACE — после `KSampler` и перед `VAEDecode`. В двух Animate2 subgraph вместо `KSampler` используется `SamplerCustom`, но место Trim перед decode остаётся тем же. Нода удаляет latent-префикс conditioning-ветки либо ничего не меняет, когда связанный `trim_latent` равен нулю.

Не задавайте число по длительности ролика на глаз. Возьмите выход `trim_latent` той же conditioning-ноды — `WanVaceToVideo` или `WanAnimate2ToVideo`, — которая подготовила начальный latent.

Не подавайте обычный четырёхосевой image LATENT. Тип порта формально совпадёт, но третья ось там является высотой: код обрежет верхние latent-строки вместо времени.

## Короткий рецепт подключения

1. Подайте результат `KSampler` либо `SamplerCustom` в `samples`.
2. Соедините выход `trim_latent` исходного `WanVaceToVideo` с `trim_amount`.
3. Направьте выход `TrimVideoLatent` в `VAEDecode` с тем же VAE, который использовался при VACE conditioning.
4. При reference image убедитесь, что INT-связь не потеряна; локальное widget-значение `0` подключённый вход не заменяет.
5. Проверьте длину декодированного видео и согласованность временных metadata.

Fragment «Убрать служебный VACE-префикс перед VAEDecode» повторяет официальную часть топологии: внешние sampled LATENT, `trim_latent` и VAE идут в `TrimVideoLatent` → `VAEDecode` → `PreviewImage`. Полного workflow нет.

## Входы, выходы и параметры

`samples` — обязательный `LATENT`. `trim_amount` — `INT` с default `0`, минимумом `0` и максимумом `99999`; шага и display-режима runtime не задаёт. Выход — один `LATENT`.

Код не проверяет число осей и не ищет временную dimension по metadata. Он всегда режет индекс 2. Для `[B, C, T, H, W]` это `T`, для `[B, C, H, W]` — `H`.

Значение больше или равное длине оси не вызывает clamp: tensor получает нулевой размер по третьей dimension. `trim_amount = 0` создаёт полный slice-view того же storage.

Выходной словарь — неглубокая копия входа. Если `noise_mask` тоже имеет temporal-длину, нода её не подрезает; downstream может получить рассогласованные формы.

## Типовые связки

Во всех восьми найденных экземплярах результат идёт прямо в `VAEDecode`. Шесть VACE-экземпляров получают samples из `KSampler` и INT с output slot 3 `WanVaceToVideo`. Два Animate2-экземпляра получают samples из `SamplerCustom` и тот же по позиции INT-выход `WanAnimate2ToVideo`.

`WanVaceToVideo` добавляет encoded reference image перед control-video latent и увеличивает temporal length. Одновременно он возвращает длину этого префикса; после sampling TrimVideoLatent удаляет соответствующие начальные latent-срезы.

В VACE без reference image conditioning-нода возвращает `trim_latent = 0`. Топология остаётся той же и не требует ручного bypass. Animate2 всегда кодирует reference frame для своей conditioning-ветки и также сообщает точную длину префикса.

## Практический пример

Exhaustive census 496 workflow-графов 0.1.42 нашёл восемь `TrimVideoLatent` в семи файлах. Четыре root-экземпляра находятся в `video_wan_vace_14B_ref2v`, `video_wan_vace_14B_t2v`, `video_wan_vace_14B_v2v` и `video_wan_vace_outpainting`. Ещё четыре лежат в subgraphs: два в `video_wan_animate2`, по одному в `video_wan_vace_flf2v` и `video_wan_vace_inpainting`. Все имеют mode `0` и `widgets_values: [0]`.

Во всех восьми случаях INT-порт связан с output slot 3 conditioning-ноды, поэтому widget `0` не задаёт фактическое значение. Шесть настроек length равны 81, две — 45 исходным кадрам, но Trim получает вычисленную latent-длину, а не эти числа напрямую.

Exact-source tensor-проба обрезала `[2, 3, 6, 2, 2]` на 2 temporal-среза и получила `[2, 3, 4, 2, 2]` с общим storage. При `trim_amount = 99` temporal-размер стал нулевым. Четырёхосевой `[1, 4, 8, 8]` превратился в `[1, 4, 6, 8]`, подтвердив отсутствие rank-проверки. Это не полный запуск VACE fragment.

## Частые ошибки и способы проверки

**В `trim_amount` введено число decoded frames.** Параметр режет latent temporal slices. Подключите `trim_latent` от conditioning-ноды вместо ручного пересчёта.

**Reference-префикс остался в видео.** Проверьте INT-link: сохранённое widget-значение `0` в официальных графах является запасным, а фактический trim приходит по связи.

**Результат имеет нулевую длину.** `trim_amount` не ограничивается текущим `T`. Сверьте форму samples и значение conditioning-output.

**Обычное изображение потеряло верхнюю часть.** Четырёхосевой LATENT был принят формально, и код обрезал высоту. Используйте ноду только для известной video-формы.

**После trim не совпала `noise_mask`.** Нода меняет только samples. Подрежьте или пересоберите temporal metadata отдельно, если downstream её читает.

**Изменение выхода затронуло общий storage.** Slice является view. Большинство нод создают новые tensors, но in-place операция downstream способна изменить данные, общие с исходной веткой.

## Производительность и внутреннее поведение

Операция не копирует tensor samples: она создаёт slice-view и неглубокий словарь. Поэтому собственная вычислительная стоимость мала и не зависит от числа удаляемых значений линейно.

View удерживает исходный storage целиком. Обрезка большого префикса сама по себе не освобождает соответствующую GPU или CPU память, пока жив результат. Если downstream позже вызывает contiguous или clone, появится отдельная копия оставшейся части.

Метаданные также разделяются с исходным словарём по ссылке. Нода не синхронизирует temporal masks, timestamps или пользовательские поля и не проверяет устройство, dtype либо значение `trim_amount` относительно формы.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, модуль `comfy_extras.nodes_wan`. Runtime fingerprint: `sha256:cfc5865170d2ef40ef70d67398f2f471cee79deb67cf782c49ce079cf89a8e78`.

Нода не помечена как experimental, deprecated или API node. В Node Replacement API 0.32.0 замены нет. Контракт тесно связан с формой Wan latent и выходом `trim_latent`; изменения conditioning-ноды требуют совместной проверки.

Embedded docs 0.5.9 называют `trim_amount` количеством кадров. Код точнее: он удаляет элементы третьей оси tensor. В статье используется термин «latent temporal slice», чтобы не обещать соответствие один к одному с decoded frames.

## Связанные ноды и источники

`KSampler` создаёт sampled LATENT в официальных VACE-графах, а `SamplerCustom` — в Animate2 subgraphs. `VAEDecode` получает уже удалённый служебный префикс. Значение trim приходит от `WanVaceToVideo` или `WanAnimate2ToVideo`; отдельные статьи для них в этой партии не создаются.

- [Реализация `TrimVideoLatent`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_wan.py#L375-L397)
- [Расчёт `trim_latent` в `WanVaceToVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_wan.py#L287-L373)
- [Расчёт `trim_latent` в `WanAnimate2ToVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_wan.py#L1253-L1379)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/TrimVideoLatent/en.md)
- [Официальные workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

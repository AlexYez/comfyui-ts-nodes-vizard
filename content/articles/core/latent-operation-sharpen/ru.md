# LatentOperationSharpen

## Что делает нода

`LatentOperationSharpen` создаёт `LATENT_OPERATION` для пространственного повышения резкости latent tensor. Она отделяет magnitude channel-вектора, фильтрует только его normalized direction grouped convolution и затем возвращает исходную magnitude.

Результат остаётся в latent-пространстве. Нода не знает VAE и не гарантирует, что визуальный эффект совпадёт с обычным unsharp mask по RGB.

## Когда она нужна и когда не нужна

Операция подходит для контролируемого эксперимента с 4D image latent `B×C×H×W`: её можно применить один раз через `LatentApplyOperation` либо на каждом шаге через CFG-wrapper.

Не используйте её без проверки для 5D video latent: реализация вызывает `conv2d`. Она также не заменяет image sharpening после decode, где результат проще интерпретировать.

## Короткий рецепт подключения

1. Создайте `LatentOperationSharpen` с radius `9`, sigma `1`, alpha `0,1`.
2. Подключите её к `LatentApplyOperation.operation`.
3. Подайте 4D LATENT на `samples`.
4. Декодируйте исходную и обработанную ветви одним VAE.

В official templates 0.1.42 прямых случаев ни Sharpen, ни direct apply нет. Рецепт source-derived и предназначен для проверяемого A/B, а не как обещание улучшения.

## Входы и выход

`sharpen_radius` принимает `1…31` и образует kernel size `2·radius+1`, то есть default 9 даёт `19×19`. `sigma` — `0,1…10`, default `1`; `alpha` — `0…5`, default `0,1`.

Выход — callable `LATENT_OPERATION`. Для фактического tensor нужен один из двух apply-wrapper. Alpha `0` превращает kernel в единичный и служит контрольным режимом.

## Нормализация latent

Код вычисляет `luminance = vector_norm(latent, dim=1) + 1e-6` и делит latent на неё. Здесь luminance — техническое название величины channel-вектора, а не фотометрическая яркость.

После convolution отфильтрованное направление умножается на исходную magnitude. Это отличает операцию от прямого свёрточного sharpen каждого latent-channel.

## Как строится фильтр

`gaussian_kernel(2r+1, sigma)` умножается на `-10·alpha`. Центральный элемент затем меняется так, чтобы сумма kernel стала `1`. При alpha больше нуля соседи получают отрицательные веса, центр — компенсирующий положительный.

Tensor сначала reflect-pad на radius, затем проходит `conv2d` с отдельной одинаковой kernel для каждого канала (`groups=channels`). После дополнительного padding convolution края crop обратно до исходных H×W.

## Практический пример

Сначала проверьте alpha `0`: decode должен совпасть с контрольной ветвью в пределах численной точности. Затем попробуйте default `0,1`, не меняя seed и VAE. Смотрите одновременно на детали и артефакты по краям.

Если нужен меньший footprint, уменьшайте radius; sigma регулирует распределение соседних весов. Не поднимайте сразу radius и alpha: невозможно понять, какой параметр вызвал ringing.

## Частые ошибки и проверка

- Default radius принимают за размер kernel. Фактический размер `19×19`.
- На маленьком latent reflect-pad падает. Каждая spatial dimension должна быть больше radius.
- Передан 5D tensor. `conv2d` поддерживает 4D input.
- Alpha `0` используют и ждут резкость. Это identity-контроль.
- Sharpen подключён напрямую к VAE. Сначала нужен `LatentApplyOperation`.

## Ограничения и производительность

Стоимость растёт примерно с площадью kernel и числом spatial-элементов. Radius 31 создаёт `63×63` kernel; в pre-CFG hook convolution повторится на каждом шаге. Временные normalized, padded и convolved tensors увеличивают память.

Reflect padding требует достаточного H/W. Нода не делает fallback на меньший radius и не проверяет rank заранее. Реальный полный workflow с моделями в редакционной проверке не запускался.

## Совместимость, изменения и источники

Сверено с ComfyUI `0.32.0`, frontend `1.48.7`, `/object_info`, embedded docs `0.5.9` и полным workflow census. Прямых случаев — ноль; нода experimental, не deprecated, без replacement.

Редактор пока не проверил материал вручную. Статья `draft/in_review`; exact-source kernel и edge branches проверены на synthetic tensors.

### Источники

- [LatentOperationSharpen](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_latent.py#L409-L447)

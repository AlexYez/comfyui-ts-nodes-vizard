# SkipLayerGuidanceDiT: дополнительный проход с пропуском блоков DiT

## Что делает нода

`SkipLayerGuidanceDiT` клонирует `MODEL` и добавляет post-CFG hook. В заданной части семплирования hook запускает ещё один conditional-проход модели, но заменяет выбранные `double_block` и `single_block` тождественным обходом: вход блока сразу становится его выходом. Затем к уже рассчитанному CFG-результату прибавляется разность между обычным conditional prediction и prediction с пропущенными блоками.

Нода экспериментальная. Она не меняет веса и не создаёт новый checkpoint. Формулировка embedded docs об «ещё одном наборе CFG negative» не совпадает с закреплённым кодом: дополнительный вызов получает `cond`, а не `uncond`.

## Место в графе

Подайте `MODEL` после loader. Если граф меняет объект `model_sampling`, проще проверять границы окна, когда такой patch стоит **до** `SkipLayerGuidanceDiT`: нода переводит `start_percent` и `end_percent` в sigma один раз, во время своего выполнения, через объект sampling входной модели. В официальных `wan2.1_fun_control` и `wan2.1_fun_inp` порядок обратный — `UNETLoader → SkipLayerGuidanceDiT → ModelSamplingSD3`; это точная сериализованная схема, а не универсальная рекомендация.

Выход можно передать дальше через другие MODEL-patches и затем в sampler или guider. Post-CFG hooks хранятся списком и выполняются в порядке добавления. В дополнительном проходе SLG сохраняет чужие replacement-ключи, но для совпавшего ключа `("double_block", index)` или `("single_block", index)` записывает свой обход поверх прежнего replacement.

## Входы

`model: MODEL` — модель, которую нода клонирует при наличии хотя бы одного разобранного индекса.

`double_layers: STRING` и `single_layers: STRING` — списки индексов, defaults у обоих `"7, 8, 9"`. Парсер извлекает все последовательности цифр регулярным выражением. Поэтому подходят запятые и пробелы, но строка `-1` превращается в индекс `1`, а `7.5` — в два индекса `7` и `5`. Проверки диапазона нет: ключ для несуществующего блока просто не встретится в цикле модели.

`scale: FLOAT` — коэффициент добавки, default 3, диапазон 0–10, шаг 0,1. `start_percent` и `end_percent` имеют defaults 0,01 и 0,15, диапазон 0–1, шаг 0,001. `rescaling_scale` имеет default 0, диапазон 0–10 и шаг 0,01.

## Выходы

Единственный выход `MODEL` содержит clone с post-CFG hook. Если обе строки не дают ни одного числа, исходник возвращает сам входной `MODEL`, не clone.

Пустая строка только в одном поле не отключает ноду: можно пропускать лишь double- либо лишь single-блоки. Выход остаётся обычным типом `MODEL`, поэтому наличие hook по одному разъёму не видно.

## Как работает внутри

Проценты переводятся в `sigma_start` и `sigma_end`. На шаге с sigma `σ` дополнительный проход выполняется при `scale > 0` и `sigma_end ≤ σ ≤ sigma_start`; обе границы включены. Для выбранных блоков `patches_replace["dit"]` получает функции, возвращающие входной словарь без вызова исходного блока.

Пусть `C` — обычный conditional prediction, `S` — prediction того же conditioning с пропущенными блоками, а `R` — результат CFG и предыдущих post-hooks. Нода возвращает `R + scale × (C − S)`. При ненулевом `rescaling_scale = r` она затем умножает весь результат на `(1 − r) + r × std(C) / std(R)`. Здесь `R` означает уже обновлённый tensor. В формуле нет epsilon: нулевая стандартная девиация может дать бесконечность или `NaN`.

## Настройки

Начинайте со списка блоков и окна из конкретного проверенного workflow той же архитектуры. Номера — индексы массивов блоков, а не номера слоёв из имени параметра checkpoint. У разных DiT различаются количество и устройство double/single blocks; defaults не доказывают совместимость.

`scale = 0` отключает дополнительный model forward, хотя hook остаётся в clone. `rescaling_scale = 0` оставляет поправку без нормализации; 1 стремится привести общую стандартную девиацию к `std(C)`. Значения выше 1 разрешены схемой, но экстраполируют множитель за эту точку. Если `start_percent > end_percent`, монотонное преобразование процентов даёт пустое sigma-окно. При равных процентах сработает только шаг, sigma которого точно попала на общую границу.

## Пример подключения

В bundle 0.1.42 есть два прямых случая, оба mode 0 и с одинаковым root UUID `e7533930-2792-43a9-b4b5-ded4617d8a43`: `wan2.1_fun_control` («Wan 2.1 ControlNet») и `wan2.1_fun_inp` («Wan 2.1 Inpainting»). В обоих `UNETLoader #37 → SkipLayerGuidanceDiT #65 → ModelSamplingSD3 #67`. Widgets SLG: `double_layers = "9,10"`, `single_layers = "9,10"`, `scale = 3`, окно 0,01–0,8000000000000002, rescaling 0; у `ModelSamplingSD3` shift равен 5.

Fragment `recipe.skip-layer-guidance-dit-wan` сохраняет этот локальный участок и округляет отображаемый `end_percent` до 0,8. Он не включает Wan weights, temporal-attention patch, CFGZeroStar и sampler, поэтому не является полным workflow и не исполнялся.

## Частые ошибки

**Считают индексы проверенными.** Код принимает любое число. Несуществующий индекс не вызывает ошибку и может создать ложное впечатление, что настройка сработала.

**Пишут отрицательные индексы.** Минус отбрасывается: `-1` становится `1`.

**Ожидают модификацию negative pass.** Реализация считает дополнительный `cond` и добавляет `C − S` после CFG.

**Ставят patch sampling после SLG и считают окно новым.** Границы уже вычислены по sampling-объекту, который был на входе SLG.

**Складывают replacements одного блока.** На дополнительном проходе SLG перезапишет существующую функцию с тем же ключом блока; replacements для других ключей сохранятся.

## Ограничения и производительность

На каждом активном шаге выполняется дополнительный conditional model forward. Это основная цена ноды по времени и памяти; обработка списка индексов и rescaling заметно дешевле. Чем шире окно, тем больше дополнительных проходов.

Описание schema называет реализацию пригодной для любой DiT, но исходник требует от архитектуры поддержки `patches_replace["dit"]` и ключей `double_block`/`single_block`. Модель с другой схемой блоков может проигнорировать часть индексов или все их. На pinned версии не проверялись реальные Wan/SD3 weights, качество изображения, multi-GPU и сочетания с каждым сторонним patch.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `SkipLayerGuidanceDiT`, модуле `comfy_extras.nodes_slg`. Fingerprint: `sha256:517c17fc845775855aafce528a4483011f11e6a13fa057e6177a358ec808354e`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacements и execution aliases отсутствуют.

Embedded docs 0.5.9 правильно перечисляют диапазоны и no-op при двух пустых списках, но русская страница переводит runtime-имена портов, а обе страницы называют дополнительный проход negative CFG. В этой статье механизм сверялся с исходником, а документация использовалась только как вторичный источник.

- [Реализация `SkipLayerGuidanceDiT`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_slg.py#L8-L88)
- [Запись block replacements и post-CFG hooks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L93-L118)
- [Выполнение post-CFG hooks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L605)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SkipLayerGuidanceDiT/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

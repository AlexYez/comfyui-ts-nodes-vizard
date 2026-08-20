# SkipLayerGuidanceDiTSimple: пропуск блоков только в unconditional-проходе

## Что делает нода

`SkipLayerGuidanceDiTSimple` клонирует `MODEL` и заменяет функцию, которая считает conditional и unconditional predictions для sampler. В активном sigma-окне conditional ветвь проходит модель без изменений, а unconditional ветвь — с обходом выбранных double- и single-блоков DiT.

В отличие от `SkipLayerGuidanceDiT`, здесь нет отдельного `scale`, нет post-CFG добавки `C − S` и нет rescaling. Изменённый unconditional prediction входит в обычную формулу CFG с тем коэффициентом, который задаёт sampler или guider.

## Место в графе

Подайте MODEL после loader и после patches, меняющих `model_sampling`, затем направьте выход к scheduler, guider или обычному sampler. Проценты переводятся в sigma при выполнении ноды, поэтому upstream sampling patch определяет границы окна.

Нода записывает один `sampler_calc_cond_batch_function`, а не добавляет обработчик в список. Следующая downstream-нода, которая установит функцию в тот же slot, полностью её заменит. С generic `SkipLayerGuidanceDiT` она может сосуществовать: Simple меняет расчёт cond/uncond, а generic-вариант позднее работает как post-CFG hook. Результат такого сочетания с весами здесь не проверялся.

## Входы

`model: MODEL` — входная модель. `double_layers` и `single_layers` — строки с defaults `"7, 8, 9"`. `start_percent` и `end_percent` имеют defaults 0 и 1, диапазон 0–1, шаг 0,001.

Все пять входов находятся в секции `required` закреплённого `/object_info`. Embedded docs 0.5.9 ошибочно помечают четыре настройки как необязательные. Парсер извлекает последовательности цифр: `9, 10` даёт `[9, 10]`, `-1` — `[1]`, `7.5` — `[7, 5]`. Диапазон индексов не валидируется.

## Выходы

Выход `MODEL` — clone с custom batch function. Если обе строки не содержат цифр, нода возвращает исходный объект MODEL без clone.

Достаточно непустого списка только одного вида. Утверждение embedded docs, будто допустимые индексы должны находиться сразу в обоих полях, противоречит guard в исходнике.

## Как работает внутри

В активном окне `sigma_end ≤ σ ≤ sigma_start`, если unconditional conditioning существует, функция вызывает `calc_cond_batch` дважды. Первый вызов получает `[cond, None]` с обычными model options и оставляет `cond_out`. Второй получает `[None, uncond]` с replacement-функциями выбранных блоков и оставляет `uncond_out`. Эта пара возвращается стандартному CFG dispatch.

Вне окна или при `uncond is None` выполняется один обычный `calc_cond_batch(model, conds, ...)`. Replacement `skip` возвращает входной словарь блока. Совпавший ключ в `patches_replace["dit"]` на unconditional-проходе перезаписывается; другие replacement-ключи остаются.

## Настройки

У Simple нет силы эффекта. Его величина зависит от выбранных блоков, окна и внешнего CFG. Для сравнения меняйте по одному параметру при одинаковых seed, sigmas, sampler и conditioning.

`start_percent = 0`, `end_percent = 1` покрывают всё sigma-окно, включая граничные значения. Обратный порядок создаёт пустое окно. Пустые оба списка дают настоящий no-op с возвратом исходной модели. Пустой только `single_layers`, как в официальном Wan Dancer, оставляет обход double-блоков.

## Пример подключения

Единственный прямой случай в bundle 0.1.42 находится в `video_wan_dancer`, root UUID `a92ccb88-3a14-4114-9b6b-fa8952839d39`, subgraph `f7467834-35a6-42fe-b525-7f17383beb4f` «Image to Video (Wan Dancer)». Нода #645 имеет widgets `double_layers = "9"`, `single_layers = ""`, окно 0–1. Слева стоит `ModelSamplingSD3 #643` с shift 5; выход SLG расходится в `BasicScheduler #653` (`simple`, 48 steps, denoise 1) и `CFGGuider #657`.

У CFGGuider сериализован widget 1, но его вход `cfg` подключён к `ComfySwitchNode`, поэтому фактическое значение определяется связью. Fragment `recipe.skip-layer-guidance-dit-simple-wan` фиксирует локальную развилку и задаёт `cfg = 3` как явное source-derived тестовое значение: при точном CFG 1 стандартная оптимизация передаёт `uncond = None`, и Simple-ветвь с пропуском блоков не включается. Fragment не исполнялся.

## Частые ошибки

**Ищут `scale`.** У Simple его нет; поправка проявляется через изменённый unconditional prediction и внешний CFG.

**Ставят CFG ровно 1 и ждут эффект.** Нода не отключает cfg=1 optimization. В стандартном dispatch unconditional тогда убирается, а код Simple переходит в обычный расчёт.

**Считают оба списка обязательными для эффекта.** Исходник требует только один непустой список.

**Цепляют две ноды с custom batch function.** Downstream-запись в `sampler_calc_cond_batch_function` заменяет upstream-функцию, а не складывается с ней.

**Принимают номер из строки как проверенный слой.** Невалидный индекс не диагностируется и обычно не встречает соответствующего блока.

## Ограничения и производительность

В активном окне conditional и unconditional считаются двумя отдельными вызовами `calc_cond_batch`. Обычный путь может объединять совместимые conditions в batch; разделение способно увеличить время и пиковые накладные расходы, хотя точный эффект зависит от модели, conditioning и памяти. Дополнительного третьего conditional forward, как у generic-варианта, здесь нет.

Поддерживаются лишь DiT-реализации, читающие replacement-ключи `double_block` и/или `single_block`. Архитектура может иметь только один вид блока или другое число слоёв. Реальный Wan Dancer graph, weights, качество видео, multi-GPU и комбинации с другими custom batch functions не исполнялись.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `SkipLayerGuidanceDiTSimple`, модуле `comfy_extras.nodes_slg`. Fingerprint: `sha256:d67fd781f6a8b675040a3f81ae1f53e3b0c3f53c827feacfe2c571c850765148`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacements и execution aliases отсутствуют.

Embedded docs верно отделяют unconditional-проход, но ошибаются в required-статусе входов и в условии «оба списка содержат индексы». Русская страница также переводит имена runtime-портов. Эти места исправлены по source и `/object_info`.

- [Реализация `SkipLayerGuidanceDiTSimple`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_slg.py#L91-L163)
- [Custom batch dispatch и cfg=1 optimization](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L607-L627)
- [Replacement-ключи блоков](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L93-L112)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SkipLayerGuidanceDiTSimple/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

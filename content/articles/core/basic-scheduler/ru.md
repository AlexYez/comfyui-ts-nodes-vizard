# BasicScheduler: получить SIGMAS из модели

`BasicScheduler` строит последовательность уровней шума для custom sampling. Он читает внутренний объект `model_sampling` из входного `MODEL`, выбирает один из встроенных алгоритмов и возвращает `SIGMAS`. Нода ничего не семплирует сама и не меняет латент.

## SIGMAS — это расписание, а не готовый результат

Выход `SIGMAS` содержит уровни шума, по которым sampler проходит от более шумного состояния к менее шумному. Его подключают к одноимённому входу `SamplerCustom` или `SamplerCustomAdvanced`. Без sampler, noise, guider и latent эта последовательность не создаёт изображение.

Финальный ноль обычно завершает денойзинг. Однако `BasicScheduler` не дописывает его самостоятельно: он получает готовое расписание от выбранного алгоритма и берёт нужный хвост.

## MODEL задаёт шкалу шума

Нода вызывает `model.get_model_object("model_sampling")`. В этом объекте находятся шкала и границы sigma, рассчитанные для конкретной архитектуры и её sampling-настроек. Поэтому вход `MODEL` здесь нужен не для предсказания шума, а для построения совместимого расписания.

Если перед `BasicScheduler` стоит нода вроде `ModelSamplingFlux` или `ModelNoiseScale`, расписание строится уже по изменённому `MODEL`. Подавать в guider другую версию модели рискованно: sampler получит SIGMAS от одной sampling-конфигурации, а предсказание — от другой.

## scheduler выбирает один из девяти алгоритмов

В ComfyUI 0.32.0 список фиксирован и идёт в таком порядке: `simple`, `sgm_uniform`, `karras`, `exponential`, `ddim_uniform`, `beta`, `normal`, `linear_quadratic`, `kl_optimal`. Неизвестное имя приводит к `ValueError` внутри `calculate_sigmas`.

Алгоритмы используют `model_sampling` по-разному. Например, `simple`, `normal`, `ddim_uniform` и `beta` читают модельную сетку sigma; `karras`, `exponential` и `kl_optimal` получают её границы. Поэтому одинаковые `steps` и имя scheduler не гарантируют одинаковые числа для разных моделей.

## steps задаёт запрошенное число переходов

`steps` имеет значение по умолчанию 20 и runtime-диапазон 1–10000. Большинство встроенных алгоритмов возвращают ненулевые уровни для переходов и завершающий ноль. Но `BasicScheduler` не проверяет длину результата: например, `beta` может убрать повторяющиеся индексы модельной сетки.

Отдельный крайний случай возникает у `kl_optimal`, когда внутренний `total_steps` равен 1: формула делит индекс на `n - 1`, получает `0 / 0` и возвращает `[NaN, 0]`. Так будет, в частности, при `steps = 1` и `denoise = 1`. Для `kl_optimal` добивайтесь хотя бы двух внутренних шагов. В остальных случаях увеличение `steps` лишь делает сетку плотнее: оно не доказывает повышение качества и не заменяет подбор sampler, CFG, модели и остальных частей графа.

## denoise строит длинную сетку и берёт её хвост

При `denoise = 1` нода просит ровно `steps` шагов. Если `0 < denoise < 1`, она сначала вычисляет `total_steps = int(steps / denoise)`, строит более длинное расписание, а затем оставляет последние `steps + 1` значений.

Например, при `steps = 20` и `denoise = 0,7` внутреннее число равно 28. В sampler уйдёт хвост этой сетки, то есть работа начнётся с более низкого уровня шума. Это механика расписания; сама нода не смешивает исходное и новое изображение в пропорции 70/30.

## denoise = 0 возвращает пустую последовательность

Runtime разрешает диапазон 0–1. Для нуля реализация сразу возвращает пустой `torch.FloatTensor` и даже не обращается к `MODEL`. Такой выход не описывает ни одного sampling-перехода.

Это не режим «ничего не менять» внутри `BasicScheduler`: дальнейшее поведение зависит от подключённого sampler и графа. Если нужен рабочий custom sampling, используйте положительное значение `denoise`.

## MODEL для scheduler и guider должен совпадать по sampling-настройкам

В custom pipeline модель участвует в двух местах. `BasicScheduler` читает из неё шкалу sigma, а guider использует модель для предсказания на каждом шаге. Ведите к ним один и тот же выход после всех `ModelSampling…`-патчей.

Сам `BasicScheduler` не сравнивает эти ветви и не выдаёт предупреждение при расхождении. Ошибка проявится уже как странная траектория sampling или несовместимые уровни шума.

## Официальные шаблоны показывают реальную топологию

Полный просмотр wheel 0.1.42 охватил 512 JSON: 496 root workflow и 272 `definitions.subgraphs`. Найдено 46 `BasicScheduler`: 13 в root и 33 в subgraph, всего в 38 файлах. Из них 44 включены, а две ноды с `simple`, 8 шагами и `denoise = 1` находятся в режиме bypass.

Во всех 46 случаях `MODEL` подключён, выход `SIGMAS` тоже подключён, а сериализованный `denoise` равен 1. Используются `simple` 35 раз, `normal` 10 раз и `beta` один раз. В 11 случаях `steps` приходит по связи; в остальных 35 берётся значение widget.

## Fragment повторяет безопасную часть официальной схемы

В `flux_redux_model_example` выход `ModelSamplingFlux` идёт одновременно в `BasicGuider` и `BasicScheduler`; у scheduler стоят `simple`, 20 и 1, а `SIGMAS` подключены к `SamplerCustomAdvanced`. Учебный fragment сохраняет ту же пару `BasicScheduler → SamplerCustomAdvanced`, оставляя MODEL, GUIDER, NOISE, SAMPLER и LATENT внешними входами.

Fragment прошёл проверку схемы, а ветви `denoise = 1`, `0,5` и `0` исполнены методом, извлечённым из pinned source, на подставном `model_sampling`. Полный граф с весами не запускался. Редактор пока не проверил материал вручную.

## Типичные ошибки видны до запуска sampler

- `MODEL` не подключён: расписание нельзя рассчитать.
- Guider построен из другой sampling-версии модели: SIGMAS и предсказание расходятся.
- `denoise = 0`: выход пуст.
- `kl_optimal` при внутреннем `total_steps = 1`: первая sigma равна `NaN`.
- Ожидание точной длины `steps + 1`: отдельные алгоритмы могут вернуть меньше уникальных точек.
- Выбор scheduler по обещанию «лучшего качества»: исходник задаёт математику, но не универсальный рейтинг.

Сначала проверьте модельную ветвь, длину и конечность SIGMAS, затем меняйте sampler или число шагов.

## Источники

- [BasicScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L17-L44)
- [Модельные scheduler в `comfy.samplers`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L645-L736)
- [Реестр и dispatch scheduler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L1358-L1386)
- [Официальный workflow `flux_redux_model_example`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/flux_redux_model_example.json)
- [Embedded docs 0.5.9 для BasicScheduler](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/BasicScheduler/en.md)

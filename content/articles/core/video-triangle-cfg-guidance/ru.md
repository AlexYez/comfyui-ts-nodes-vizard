# VideoTriangleCFGGuidance: CFG с пиком в середине

## Что делает нода

`VideoTriangleCFGGuidance` клонирует `MODEL` и задаёт пользовательское смешение CFG для video batch. Коэффициент равен `min_cfg` на первом кадре, поднимается к downstream `cond_scale` в середине и возвращается к `min_cfg` на последнем.

Это один треугольник на всю нулевую ось tensor, а не повторяющаяся волна по denoise steps. Нода не выполняет sampling и не создаёт `GUIDER`; она возвращает patched `MODEL`.

## Место в графе

Ставьте ноду между video model loader или другим совместимым model patch и sampler: `MODEL → VideoTriangleCFGGuidance → KSampler`. В custom sampling её MODEL можно передать в обычный `CFGGuider`, после чего GUIDER направить в `SamplerCustomAdvanced`.

Не ставьте рядом с `VideoLinearCFGGuidance` в надежде сложить профили. Обе ноды вызывают `set_model_sampler_cfg_function`; более поздняя patch заменяет функцию предыдущей.

## Входы

`model: MODEL` — обязательный model patcher. Schema не проверяет расположение temporal dimension, поэтому video-совместимость нужно подтверждать по графу конкретной модели.

`min_cfg: FLOAT` — коэффициент на обоих краях batch. Default 1, диапазон 0–100, шаг widget 0,5, округление 0,01; поле advanced. Центральный уровень берётся из `cond_scale` downstream sampler или guider.

## Выходы

Единственный выход — `MODEL`, клонированный перед установкой CFG-функции. Исходная модель остаётся без этой patch-функции.

Выход не содержит готовых кадров, conditioning или sigmas. Все они остаются входами sampler и должны быть согласованы с video architecture.

## Как работает внутри

Для `N = cond.shape[0]` код строит значения `t` от 0 до 1. Затем вычисляет `v = 2 × |t − floor(t + 0,5)|` и `scale = min_cfg + v × (cond_scale − min_cfg)`. Результат имеет форму `(N, 1, 1, 1)` и входит в `uncond + scale × (cond − uncond)`.

При нечётном `N` один элемент лежит точно в `t = 0,5` и достигает downstream cfg. При чётном `N` два центральных элемента симметричны, но максимум немного ниже `cond_scale`. При `N = 1` и `N = 2` все элементы получают `min_cfg`.

## Настройки

При `min_cfg = 1` и downstream `cfg = 2,5` профиль начинается с 1, поднимается к 2,5 и снова падает к 1. Для нечётного batch из пяти кадров коэффициенты равны `[1; 1,75; 2,5; 1,75; 1]`.

Если `min_cfg` выше downstream cfg, геометрия сохраняется, но середина становится впадиной, а не пиком. Имя параметра не навязывает математический порядок. Подбирайте оба значения как пару и фиксируйте длину batch при сравнении.

## Пример подключения

В 512 JSON официального bundle 0.1.42, включая 272 `definitions.subgraphs`, прямых `VideoTriangleCFGGuidance` нет. Поиск точного типа и строкового имени также дал ноль. Поэтому fragment не выдаётся за извлечённый официальный case.

Source-derived fragment использует `min_cfg = 1` и `KSampler` с cfg 2,5, 20 steps, Euler, Karras и denoise 1. Такая форма повторяет интерфейс реально найденного линейного SVD-примера, но заменяет patch-алгоритм на треугольный. Schema и типы проверены; граф не импортировался и не выполнялся.

## Частые ошибки

**Ждут повторных колебаний.** В интервале 0–1 формула проходит один подъём и один спуск. Период в source фиксирован и не является параметром.

**Считают, что центральный кадр всегда получает точный cfg.** Для чётного batch точки `t = 0,5` нет; максимум будет ниже.

**Применяют к image batch.** Тогда разные изображения batch получают разные коэффициенты, хотя temporal смысла у оси нет.

**Ищут расписание по steps.** Коэффициенты меняются по `cond.shape[0]` внутри каждого prediction, не по sigma.

**Соединяют с PerpNegGuider.** Тот вызывает собственную формулу и не использует `sampler_cfg_function`, поэтому треугольная patch не применяется как ожидается.

## Ограничения и производительность

Вычисление одномерной шкалы и смешение predictions малы по стоимости относительно diffusion model. Память в основном определяется video latent и conditional/unconditional проходами.

Broadcast shape рассчитан на четырёхмерные predictions `[frames, channels, height, width]`. Для других tensor layouts результат нужно проверять отдельно. Нода не различает кадры и независимые batch items по metadata.

Как и линейная версия, она не запрещает cfg=1 optimization. Если downstream `cond_scale` равен 1, стандартный sampling может не вычислить настоящий unconditional prediction, даже если `min_cfg` отличается от 1. Это ограничение особенно важно при нестандартной паре параметров.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `VideoTriangleCFGGuidance`, модуле `comfy_extras.nodes_video_model`. Fingerprint: `sha256:7daaf0739719dc43d47e3efe41c531ad24ddacd1ad438dfd55b29d05ec062028`. Legacy descriptor не сериализует deprecated, experimental, dev_only и api_node; класс не задаёт эти flags. Replacement и aliases не обнаружены.

Embedded docs 0.5.9 называют профиль «волной, которая колеблется», и без доказательств обещают улучшение consistency и quality. Закреплённый source показывает только один triangle по axis 0 и не содержит оценки качества, поэтому статья таких обещаний не повторяет.

- [Реализация `VideoTriangleCFGGuidance`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video_model.py#L83-L108)
- [Контракт custom CFG function](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/VideoTriangleCFGGuidance/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

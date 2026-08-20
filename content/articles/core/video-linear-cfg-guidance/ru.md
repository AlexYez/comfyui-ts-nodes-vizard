# VideoLinearCFGGuidance: линейный CFG по кадрам

## Что делает нода

`VideoLinearCFGGuidance` клонирует `MODEL` и заменяет его `sampler_cfg_function`. Вместо одного коэффициента для всего video batch функция строит линейную шкалу: первый элемент получает `min_cfg`, последний — `cond_scale`, который пришёл от downstream sampler или guider.

Нода не создаёт кадры и не задаёт конечный CFG сама. Она меняет способ смешения conditional и unconditional predictions внутри sampling. Такой приём рассчитан на video-модели, у которых кадры лежат по нулевой оси тензора.

## Место в графе

Подключайте `MODEL` от video checkpoint или совместимого model patch во вход ноды, а её выход — в `KSampler` либо guider custom-sampling цепочки. В официальном SVD-примере путь ровно такой: `ImageOnlyCheckpointLoader → VideoLinearCFGGuidance → KSampler`.

Ставить ноду после sampler бессмысленно: выход снова имеет тип `MODEL`. Если далее другая нода вызывает `set_model_sampler_cfg_function`, она заменит эту функцию, а не сложит два расписания.

## Входы

`model: MODEL` обязателен. Runtime не проверяет, действительно ли модель хранит видеокадры по batch-оси; совместимость определяется фактической формой predictions.

`min_cfg: FLOAT` — значение для первого элемента. Default 1, диапазон 0–100, шаг widget 0,5, округление до 0,01; параметр помечен advanced. Значение на последнем кадре берётся не отсюда, а из downstream `cond_scale`.

## Выходы

Выход один: клонированный `MODEL` с пользовательской CFG-функцией. Это не list-output и не готовый `GUIDER`.

Подключённые conditioning и latent нода не видит. Их принимает downstream sampler, который вычисляет conditional и unconditional tensors и передаёт их функции вместе с `cond_scale`.

## Как работает внутри

Исходник строит `torch.linspace(min_cfg, cond_scale, cond.shape[0])`, меняет форму на `(N, 1, 1, 1)` и вычисляет `uncond + scale × (cond − uncond)`. Для обычного четырёхмерного video batch коэффициент широковещательно применяется к каждому кадру.

При одном элементе `linspace` возвращает только `min_cfg`; downstream cfg не достигается. При нескольких элементах шаг постоянен. Если `min_cfg` больше downstream cfg, шкала убывает, несмотря на слово `min` в имени.

## Настройки

В закреплённом SVD workflow стоит `min_cfg = 1`, а downstream `KSampler` использует `cfg = 2,5`. Поэтому первый кадр получает 1, последний 2,5, промежуточные — равномерные значения между ними.

Выбирайте `min_cfg` вместе с CFG sampler. Сам по себе диапазон UI 0–100 не означает, что крайние значения полезны для конкретной модели. Для контрольного сравнения фиксируйте seed, sigmas, sampler и входной кадр.

## Пример подключения

Полный census bundle 0.1.42 нашёл одну прямую ноду: root workflow `txt_to_image_to_video`, UUID `858d315b-00e0-4802-b61b-fadbacbedaaf`, node 14, mode 0, widgets `[1]`.

`ImageOnlyCheckpointLoader #15` с `svd_xt.safetensors` подаёт MODEL в node 14; её MODEL идёт в `KSampler #3`. KSampler хранит 20 steps, cfg 2,5, `euler`, `karras`, denoise 1; positive, negative и latent создаёт `SVD_img2vid_Conditioning #12`. Fragment воспроизводит эти связи и параметры, но не включает checkpoint или изображение и не выполнялся.

## Частые ошибки

**Принимают `min_cfg` за общий CFG.** Это только первый конец линейки; второй задаёт sampler или guider.

**Применяют к обычному image batch.** Код различает элементы по оси 0 и примет изображения за «кадры». Получится разный CFG по batch, что обычно не является целью.

**Ставят после другого CFG patch.** Последний вызов `set_model_sampler_cfg_function` перезаписывает предыдущую функцию. Проверяйте порядок model chain.

**Ждут линейку по denoise steps.** Шкала строится по `cond.shape[0]`, а не по sigma или номеру шага.

**Используют downstream cfg=1 с иным min_cfg.** Стандартный sampling может пропустить настоящий unconditional-проход при cfg=1; тогда формула получает нулевую заглушку вместо полноценного unconditional prediction.

## Ограничения и производительность

Создание линейки и покадровое смешение дёшевы по сравнению с прогоном diffusion model. Главная стоимость определяется числом кадров, размером latent и тем, вычисляются ли обе conditioning-ветви.

Код reshapes scale в четыре измерения. Он напрямую соответствует тензору вида `[frames, channels, height, width]`; для иной упаковки, например с отдельной temporal-осью в пяти измерениях, корректность нельзя предполагать без проверки модели.

Нода не включает `disable_cfg1_optimization`. При downstream cfg=1 стандартный путь может исключить unconditional condition до вызова пользовательской функции. Кроме того, `PerpNegGuider` применяет собственную формулу напрямую и не вызывает `sampler_cfg_function`, поэтому эта patch-функция с ним не образует линейный Perp-Neg schedule.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `VideoLinearCFGGuidance`, модуле `comfy_extras.nodes_video_model`. Fingerprint: `sha256:d44e927ba77b0ab10d76ab2f9cbf642bf174d9e830158f5165d272155c7377c7`. Legacy descriptor не сериализует поля deprecated, experimental, dev_only и api_node; исходный класс также не задаёт эти flags. Replacement и execution aliases не обнаружены.

В embedded-docs 0.5.9 нет каталога `VideoLinearCFGGuidance` ни для EN, ни для RU. Поэтому описание параметров и tensor semantics опирается на закреплённый source, runtime inventory и единственный официальный workflow case.

- [Реализация `VideoLinearCFGGuidance`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video_model.py#L59-L81)
- [Контракт custom CFG function](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

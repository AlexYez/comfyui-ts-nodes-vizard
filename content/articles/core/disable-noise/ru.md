# DisableNoise: нулевой шум для custom sampler

`DisableNoise` возвращает объект `NOISE`, который при запросе создаёт нулевой тензор формы входного `LATENT`. Несмотря на название, нода не отключает sampler и не пропускает его шаги: она заменяет случайный начальный шум нулями.

## 1. Что делает нода

Нода создаёт `Noise_EmptyNoise` с `seed = 0`. Его метод `generate_noise(input_latent)` читает форму, dtype и layout поля `samples`, затем выделяет нули на CPU.

До вызова этого метода выход — небольшой объект без tensor. Фактическое выделение происходит внутри `SamplerCustomAdvanced` или другой принимающей ноды, когда известен начальный LATENT.

## 2. Место в графе

Основной путь: `DisableNoise → SamplerCustomAdvanced.noise`. Остальные входы sampler остаются обычными. Такая схема полезна для refinement, продолжения уже существующего latent или специальных pipeline, где расписание и модель должны отработать без новой случайной составляющей.

Это не эквивалент bypass sampler. Даже с нулевым noise результат может измениться из-за сигм, guider, denoising mask и модели. Для обычной генерации с нуля чаще нужен `RandomNoise`.

## 3. Входы

У ноды нет входов и виджетов. Она не принимает seed, форму, устройство или dtype заранее.

Форма появляется только при вызове `generate_noise` с конкретным LATENT. Поэтому один и тот же объект можно использовать для разных форм: каждый вызов создаст подходящий нулевой tensor.

## 4. Выход

Выход имеет тип `NOISE`. Для обычного latent он создаёт CPU-тензор нулей с теми же shape, dtype и layout, что у `samples`. Устройство исходного tensor намеренно не наследуется: в коде явно задан `device="cpu"`.

Для nested latent каждый вложенный tensor получает отдельный массив нулей и результат собирается обратно в `NestedTensor`. Метаданные LATENT не копируются в NOISE; только сам sampler использует их отдельно.

## 5. Как работает

`Noise_EmptyNoise.generate_noise` проверяет `latent_image.is_nested`. В обычной ветке вызывается `torch.zeros(latent_image.shape, dtype=..., layout=..., device="cpu")`. В nested-ветке тензоры распаковываются, каждый обнуляется на CPU и снова объединяется.

`SamplerCustomAdvanced` всё равно вызывает `noise.generate_noise(latent)`, передаёт нули в `guider.sample` и выполняет заданные сигмы. Поэтому фраза embedded docs о возможности «пропустить noise-related operations» неточна: генерация массива и sampling остаются, просто случайные значения заменены нулями.

Поле `seed = 0` передаётся sampler как seed для связанных внутренних механизмов. Пользовательского виджета seed у `DisableNoise` нет.

## 6. Параметры и настройка

Настраивать саму ноду нечего. Поведение определяется входным LATENT и downstream sampler. Для проверки результата сравнивайте одинаковый граф с `RandomNoise` и `DisableNoise`, не меняя sigmas, guider и latent.

Если требуется лишь уменьшить шум, а не убрать его, `DisableNoise` не предоставляет коэффициент. Используйте подходящую SIGMAS-схему, model-specific операцию или отдельно подготовленный NOISE; смешивание нуля и random noise эта нода не выполняет.

## 7. Проверенный пример

Recipe `Нулевой шум для SamplerCustomAdvanced` соединяет выход `DisableNoise` с портом `noise` sampler. `GUIDER`, `SAMPLER`, `SIGMAS` и `LATENT` приходят извне. Такая точная связь найдена в Lotus Depth, SD 3.5 Depth, Qwen control, LTX depth и Hunyuan Video 1.5 templates.

Полный census нашёл семь экземпляров: два root и пять subgraph в семи файлах. Пять активны, два Hunyuan-варианта сохранены в режиме bypass. Exact-source probe подтвердил CPU, dtype, shape и нулевые значения. Полный sampling fragment не исполнялся.

## 8. Частые ошибки

- Считают, что sampler не запустится. Он получает нули и выполняет все шаги.
- Ожидают неизменный LATENT. Модель и расписание могут изменить его без случайного старта.
- Ищут настройку силы или seed. Входов у ноды нет.
- Путают нулевой `NOISE` с нулевым `LATENT`: это разные объекты и разные порты.
- Ожидают tensor на GPU. Реализация выделяет нули на CPU.
- Делают вывод по bypassed ноде официального workflow. Два Hunyuan-примера отключены режимом canvas; активные случаи найдены в других шаблонах.

## 9. Ограничения и производительность

Нулевой tensor всё равно занимает память, пропорциональную форме LATENT, и затем участвует в sampler pipeline. Для большого видео это не «бесплатное отключение». Временное CPU-выделение и перенос остаются.

Нода не проверяет, подходит ли zero-noise выбранной модели или расписанию. Смысл зависит от конкретного pipeline: для одних это refinement существующего latent, для других — некорректная начальная точка.

## 10. Совместимость и источники

Материал проверен для ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не deprecated и не experimental; Node Replacement API её не заменяет.

Embedded docs правильно описывает отсутствие входов и назначение нулевого шума, но создаёт впечатление, будто связанные операции пропускаются. Исходник показывает явное создание нулевого массива и обычный вызов sampler.

- [Noise_EmptyNoise и DisableNoise](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L716-L729)
- [SamplerCustomAdvanced](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L1027-L1082)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

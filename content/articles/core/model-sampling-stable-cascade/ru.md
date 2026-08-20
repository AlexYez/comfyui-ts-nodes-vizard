# ModelSamplingStableCascade: cosine sampling с настраиваемым shift

`ModelSamplingStableCascade` клонирует модель и заменяет её sampling-объект реализацией `StableCascadeSampling`. Нода перестраивает cosine-зависимость между timestep и sigma, а параметр `shift` сдвигает log-SNR. Она предназначена для Stage C или Stage B Stable Cascade, а не для обычной Stable Diffusion.

## Что делает нода

Patch соединяет sampling-базу Stable Cascade с epsilon-параметризацией. Внутри создаётся совместимая сетка из 10 000 sigma. Затем `shift` применяется повторно к новому объекту, и он записывается в cloned `MODEL`.

Нода не создаёт двухступенчатый Cascade workflow и не передаёт prior между Stage C и Stage B. Она меняет только sampling-математику одной подключённой модели. Обе стадии в ComfyUI используют класс Stable Cascade по умолчанию, но каждая остаётся отдельным model instance.

## Место в графе

Ставьте patch после загрузчика соответствующей Stage C или Stage B модели и до guider, scheduler и sampler этой стадии. Один и тот же patched выход ведите в model-aware scheduler и guider.

Если вы настраиваете обе стадии, применяйте отдельный patch к каждой ветви и не смешивайте их модели. Conditioning и latent/prior между Stage C и Stage B имеют разные роли; одинаковый тип `MODEL` не делает ветви взаимозаменяемыми.

## Входы

- `model` — Stable Cascade `MODEL`, который будет клонирован.
- `shift` — число от 0 до 100 с шагом 0,01, по умолчанию 2.

Runtime не проверяет семейство модели. Любой `MODEL` формально подключается, поскольку порт общий. Также схема разрешает `shift = 0`, хотя этот крайний случай схлопывает построенную сетку почти в одно значение и непригоден как обычное расписание.

## Выход

Выход — cloned `MODEL` с новым `model_sampling`. Объект содержит 10 000 sigma и conversion-функции Stable Cascade. Исходная модель остаётся без этого patch.

Сам `SIGMAS` здесь не выходит. Их строит downstream scheduler по patched model sampling. Если guider получает другой model output, типы портов останутся корректными, но sampling-семантика разойдётся.

## Как работает shift

Базовый cumulative alpha вычисляется по cosine-кривой с `cosine_s = 0,008`. Для каждого из 10 000 timestep нода получает alpha, переводит его в log-SNR и при `shift != 1` добавляет `2 * log(1 / shift)`. Затем значение проходит sigmoid, ограничивается диапазоном 0,0001–0,9999 и переводится в sigma.

При `shift = 1` дополнительного сдвига нет. Значение больше единицы уменьшает log-SNR перед clamp и меняет весь ряд в сторону иных sigma; это механическое описание, а не универсальное обещание качества. В probe `shift = 0` дал бесконечный положительный сдвиг, clamp 0,9999 и 10 000 одинаковых sigma около 0,01.

## Параметры и настройка

Default ноды равен 2, тогда как базовый `StableCascadeSampling` модели читает `shift` из model config и при отсутствии значения использует 1. Следовательно, вставка ноды с default уже меняет поведение; это не нейтральный passthrough.

Не используйте ноль как способ отключить shift. Для исходной cosine-кривой задайте 1, а для полного сохранения автоматически загруженной конфигурации лучше вообще не добавлять ручной patch. Другие значения сравнивайте отдельно для Stage C и Stage B на фиксированном seed.

## Проверенный пример

Fragment Wizard применяет `shift = 2` и ведёт patched модель в `BasicScheduler` с `simple`, 20 и `denoise = 1`. Это демонстрирует порядок patch → scheduler. Пользователь должен подключить правильную Cascade stage и продолжить своей sampling-ветвью.

Полный scan official workflow wheel 0.1.42 не нашёл `ModelSamplingStableCascade`: 512 JSON, 496 root и 272 subgraph просмотрены полностью. Системный реальный контекст подтверждён исходником `StableCascade_C` и `StableCascade_B`, которые обе создаются с типом `STABLE_CASCADE`. Exact patch исполнен для shift 2 и 0; проверены класс, EPS mixin, длина и монотонность сетки. Модели Stage C/B не запускались. Редактор пока не проверил материал вручную.

## Частые ошибки

- Нода применяется к SDXL или другой не-Cascade модели из-за общего типа `MODEL`.
- Default 2 считается нейтральным, хотя базовый fallback модели равен 1.
- `shift = 0` используется как выключатель и даёт почти плоский ряд.
- Один patched model подключается в обе Cascade-stage ветви.
- Scheduler получает patched модель, guider — исходную.
- Ожидается автоматическая сборка prior/conditioning между Stage C и Stage B.

## Ограничения и производительность

В отличие от коротких patch-нод, `StableCascadeSampling.set_parameters` заполняет 10 000 sigma Python-циклом. Это всё ещё дешевле полного inference, но заметнее обычного создания тысячаточечной векторной сетки и может повторяться при каждом исполнении ноды.

Sampling-класс вычисляет ряд для совместимости scheduler, а не оценивает оптимальный shift. Нода не проверяет stage, checkpoint, conditioning или порядок двухступенчатого графа. Слишком крайние значения могут упереться в clamp и потерять различимость точек.

## Совместимость и источники проверки

Проверено на ComfyUI 0.32.0 и frontend 1.48.7. Нода относится к `model/patch/stable cascade`, не помечена experimental, deprecated или API-only и не имеет формальной замены.

Embedded docs 0.5.9 описывают входы и общий custom shift, но не сообщают о базовом fallback 1, цикле на 10 000 точек, формуле log-SNR, clamp и вырожденном нуле. Эти детали взяты из закреплённой реализации и подтверждены probe.

## Источники

- [ModelSamplingStableCascade в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L91-L118)
- [StableCascadeSampling mathematics](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L349-L398)
- [Stable Cascade Stage C и Stage B](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L724-L770)
- [Embedded docs 0.5.9 для ModelSamplingStableCascade](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelSamplingStableCascade/en.md)

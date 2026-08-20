# CFGZeroStar: optimized scale после CFG

## Что делает нода

`CFGZeroStar` клонирует `MODEL` и добавляет post-CFG hook. На каждом sampling step он вычисляет коэффициент проекции между conditional и unconditional направлениями, затем корректирует уже готовый CFG-результат.

Закреплённая реализация содержит только optimized-scale часть метода CFG-Zero*. В ней нет параметра числа начальных шагов и нет zero-init, который обнуляет prediction в начале sampling. Название ноды не означает, что обе части reference method включены автоматически.

## Место в графе

Ставьте ноду в MODEL-цепочку перед sampler: `MODEL patch → CFGZeroStar → KSampler`. В двух официальных WAN-графах перед ней стоит `UNetTemporalAttentionMultiply`, а выход напрямую подключён к `KSampler.model`.

Нода добавляет post-hook в существующий список. Если в MODEL уже есть `CFGNorm` post-mode, `Mahiro` или другая post-CFG функция, они выполняются последовательно; результат зависит от порядка model patches.

## Входы

Вход один: `model: MODEL`. Widgets и числовых параметров нет. Guidance scale, positive и negative conditioning по-прежнему задаёт downstream sampler или guider.

Schema не ограничивает модель конкретным семейством. Однако два прямых официальных case относятся к WAN 2.1, а reference repository описывает метод для flow-matching models. Перенос на другую архитектуру требует отдельного сравнения.

## Выходы

Единственный выход `patched_model: MODEL` содержит clone с добавленным post-CFG hook. Исходный MODEL не меняется.

Это не `GUIDER` и не denoised LATENT. Correction выполняется внутри стандартного sampling path после CFG combine и до следующих post-hooks.

## Как работает внутри

Код строит `positive = x − cond_p` и `negative = x − uncond_p`, разворачивает каждый batch item в вектор и вычисляет `alpha = <positive, negative> / (||negative||² + 1e−8)`. Alpha имеет одно значение на batch item и затем растягивается по остальным осям.

Возвращаемое выражение можно свернуть до `out + (cfg − 1) × (1 − alpha) × uncond_p`, где `out` — текущий результат CFG. Alpha не ограничивается диапазоном 0–1: при отрицательном скалярном произведении или большой проекции correction может менять знак и величину сильнее ожидаемого.

## Настройки

Настроек самой ноды нет. Управлять эффектом можно только косвенно: downstream `cfg`, conditioning, model family и порядок соседних hooks меняют входные tensors формулы.

При `cfg = 1` множитель `(cfg − 1)` обнуляет correction. Стандартный sampling обычно одновременно пропускает unconditional condition. При `alpha = 1` correction также равна нулю. Эти равенства полезны для изолированной проверки подключения.

## Пример подключения

В 512 JSON bundle 0.1.42 найдены две `CFGZeroStar`: `wan2.1_fun_control` и `wan2.1_fun_inp`. Обе находятся в root, имеют mode 0, пустые widgets и общий сериализованный workflow UUID `e7533930-2792-43a9-b4b5-ded4617d8a43`.

Топология одинакова: `ModelSamplingSD3 #67 → UNetTemporalAttentionMultiply #68 → CFGZeroStar #66 → KSampler #3`. KSampler хранит 20 steps, cfg 6, UniPC, simple и denoise 1. Fragment сохраняет участок `CFGZeroStar → KSampler`; upstream temporal patch и WAN conditioning остаются внешними. Структура проверена, граф не запускался.

## Частые ошибки

**Ждут zero-init.** ComfyUI source не обнуляет первые predictions и не имеет настройки числа zero steps. Это только optimized-scale hook.

**Ищут strength.** У ноды нет widget. Эффект зависит от downstream cfg и самих predictions.

**Считают alpha вероятностью.** Коэффициент не clamp-ится и может быть меньше 0 или больше 1.

**Не учитывают порядок post-hooks.** Каждый следующий hook получает результат предыдущего. Перестановка `CFGZeroStar` и другой post-CFG ноды меняет формулу.

**Переносят WAN settings на любую модель.** Два официальных графа подтверждают topology, а не универсальность cfg 6 или UniPC.

## Ограничения и производительность

Dot product и squared norm считаются отдельно для каждого batch item по всем прочим элементам. Элементы batch не смешиваются между собой, но внутри одного элемента используется единый alpha для всех каналов, кадров и пространственных координат.

Добавка `1e−8` защищает знаменатель при нулевом unconditional-направлении. Она не ограничивает большие конечные alpha и не устраняет NaN или Inf, уже присутствующие во входах.

По сравнению с model forward flatten, редукции и correction недороги, но выполняются на каждом step и создают промежуточные tensors. Фактическое влияние на время и память зависит от размера video latent.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `CFGZeroStar`, модуле `comfy_extras.nodes_cfg`. Fingerprint: `sha256:4670102f9220dd2cd6f5e94df4662b6cb8ab3cb3a8d047f031978927e28ab50c`. Flags deprecated, experimental, dev_only и api_node равны false. Replacement и execution aliases отсутствуют.

Embedded docs 0.5.9 обещают «enhanced control» и «model stability», но не приводят метрику и не отделяют optimized scale от zero-init. Статья фиксирует только формулу ComfyUI и явно наблюдаемую topology.

- [Реализация `CFGZeroStar`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_cfg.py#L8-L49)
- [Официальный reference repository CFG-Zero*](https://github.com/WeichenFan/CFG-Zero-star)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/CFGZeroStar/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

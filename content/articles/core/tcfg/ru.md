# TCFG: SVD-проекция unconditional score

## Что делает нода

`TCFG` означает Tangential Damping Classifier-free Guidance. Нода клонирует `MODEL` и добавляет pre-CFG hook. Перед стандартным смешением она заменяет unconditional prediction так, чтобы соответствующий score остался на главной сингулярной оси пары conditional и unconditional scores.

ComfyUI source связывает реализацию с работой arXiv 2503.18137. Статья описывает фактический код ноды, а не переносит на любой граф заявленные в работе результаты качества.

## Место в графе

Подключите MODEL во вход `TCFG`, а `patched_model` передайте sampler с positive и negative conditioning. Hook срабатывает после вычисления conditioning predictions и до обычной CFG-функции.

TCFG добавляется в список `sampler_pre_cfg_function`. Несколько pre-hooks выполняются в порядке model patches, и каждый следующий получает уже изменённый `conds_out`. Поэтому перестановка TCFG с другой pre-CFG нодой может дать другой результат.

## Входы

Единственный вход — `model: MODEL`. Числовых widgets нет. Коэффициент cfg и оба conditioning задаются downstream sampler или guider.

Функция ожидает, что первые два элемента `conds_out` соответствуют conditional и unconditional predictions. Если выходов меньше двух либо одно из первых двух условий равно `None`, она возвращает исходный список без изменения.

## Выходы

Выход `patched_model: MODEL` — clone с зарегистрированным pre-CFG hook. Нода не возвращает `GUIDER`, score или LATENT.

Остальные элементы `conds_out`, если они есть, сохраняются: код заменяет только второй prediction и дописывает хвост списка без изменений.

## Как работает внутри

Для каждого batch item код строит `cond_score = x − cond_pred` и `uncond_score = x − uncond_pred`, разворачивает их в два вектора float32 и складывает в матрицу формы `2 × D`. `torch.linalg.svd(..., full_matrices=False)` даёт правые сингулярные векторы; используется первый `v1`.

Новый unconditional score равен его проекции на `v1`: `(uncond_score · v1) × v1`. Затем код возвращается к prediction как `x − projected_score`. Знак сингулярного вектора может меняться, но проекция на его ось от этого не зависит.

## Настройки

У ноды нет регулируемой strength. Для сравнения сделайте отдельную MODEL-ветвь в обход TCFG и оставьте seed, cfg, sampler, scheduler, sigmas и conditioning одинаковыми.

При `cfg = 1` стандартная оптимизация ComfyUI обычно передаёт `None` вместо unconditional condition. TCFG замечает это и пропускает преобразование. Чтобы исследовать именно SVD-проекцию, нужен sampling path с обеими conditioning-ветвями.

## Пример подключения

Полный scan 512 JSON bundle 0.1.42, включая 496 root graphs и 272 subgraphs, не нашёл `TCFG` ни как node type, ни как точное строковое имя. Официального preset или topology для этой версии нет.

Source-derived fragment соединяет `MODEL → TCFG → KSampler` и использует runtime defaults KSampler: seed 0, 20 steps, cfg 8, Euler, simple, denoise 1. Эти числа нужны для полного semantic fragment и не являются рекомендацией paper или найденным official TCFG case. Fragment не выполнялся.

## Частые ошибки

**Ждут эффект при cfg 1.** Unconditional condition тогда обычно отсутствует, и hook возвращает predictions без изменения.

**Считают, что нода меняет conditional prediction.** Первый элемент сохраняется; проецируется только unconditional score.

**Принимают SVD за глобальную по batch.** Матрица строится отдельно для каждого batch item. Элементы batch не смешиваются.

**Игнорируют порядок pre-hooks.** TCFG читает текущий `conds_out`; предыдущая функция могла его изменить.

**Ссылаются на paper как на гарантию.** Совпадение метода и реализации не доказывает улучшение на выбранной модели, sampler и prompt.

## Ограничения и производительность

SVD выполняется на каждом sampling step и отдельно для каждого batch item. Матрица имеет две строки, но длина `D` равна числу остальных элементов tensor. Это добавляет вычисления и промежуточные float32 buffers поверх model forward.

Если SVD на текущем устройстве выбрасывает `RuntimeError`, код повторяет её на CPU, затем возвращает `v1` на исходное устройство. Такой fallback может вызвать синхронизацию и передачу данных; причина исходной ошибки при этом не различается.

Входы всегда переводятся во float32 для SVD, а итог приводится обратно к dtype unconditional score. Это повышает точность разложения относительно half precision, но требует дополнительной памяти.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `TCFG`, модуле `comfy_extras.nodes_tcfg`. Fingerprint: `sha256:d2411b73c2bf2951a3cd8f4d09fda2821319a956cf3b17b6e80de981c370e7ec`. Flags deprecated, experimental, dev_only и api_node равны false. Replacement и execution aliases отсутствуют.

Embedded docs 0.5.9 верно называет paper и общую цель, но утверждает улучшение output quality без условий и не объясняет SVD, skip при отсутствующем unconditional, float32 conversion и CPU fallback.

- [Реализация `TCFG`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_tcfg.py#L1-L64)
- [Работа TCFG, arXiv 2503.18137](https://arxiv.org/abs/2503.18137)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/TCFG/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

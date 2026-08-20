# Mahiro: similarity-weighted positive guidance

## Что делает нода

`Mahiro` клонирует `MODEL` и добавляет экспериментальный post-CFG hook. Hook смешивает обычный CFG-результат с conditional prediction, умноженным на guidance scale. Вес смеси вычисляется через cosine similarity после знакового извлечения квадратного корня из двух промежуточных tensors.

Runtime display name — `Positive-Biased Guidance`. Нода не меняет prompt и не создаёт новый conditioning; она перерабатывает predictions после CFG combine.

## Место в графе

Ставьте `Mahiro` в MODEL-цепочку до sampler: `MODEL → Mahiro → KSampler`. Positive, negative, cfg и latent остаются входами sampler.

Mahiro добавляет функцию в список `sampler_post_cfg_function`. Если рядом стоят `CFGZeroStar`, `CFGNorm` в post-режиме или другой post-hook, каждый получает результат предыдущего. Порядок нод задаёт порядок формул.

## Входы

Единственный вход — `model: MODEL`. Числовых настроек у ноды нет. `cond_scale`, conditional и unconditional predictions поступают из текущего sampling context.

Runtime search aliases — `mahiro`, `mahiro cfg`, `similarity-adaptive guidance` и `positive-biased cfg`. Это поисковые фразы интерфейса, а не исторические execution IDs; поле `runtimeIdentity.aliases` поэтому остаётся пустым.

## Выходы

Выход `patched_model: MODEL` — clone с post-CFG hook. Нода не возвращает `GUIDER`, `CONDITIONING` или LATENT.

Формула выполняется на каждом sampling step после того, как стандартная или пользовательская CFG-функция создала текущий `denoised` result.

## Как работает внутри

Код задаёт `leap = cond_p × cfg`, `u_leap = uncond_p × cfg` и `merge = (leap + current_cfg_result) / 2`. Для `u_leap` и `merge` применяется преобразование `sign(x) × sqrt(abs(x))`, затем считается cosine similarity по `dim=1` и среднее по всем оставшимся измерениям и batch.

Если обозначить итоговое среднее similarity как `s`, вес обычного CFG равен `(s + 1) / 2`. Возврат можно записать как `weight × current_cfg_result + (1 − weight) × leap`. Для конечных tensors cosine similarity лежит около диапазона −1…1, поэтому формула выбирает смесь между двумя endpoints.

## Настройки

У Mahiro нет strength. Эффект определяется downstream cfg и predictions модели. Для оценки создайте параллельную ветвь без Mahiro и фиксируйте seed, conditioning, sampler, scheduler и sigmas.

При cfg 1 стандартная оптимизация обычно не вычисляет unconditional condition. В обычном случае `leap` и текущий CFG-result тогда совпадают с conditional prediction, поэтому смешение остаётся тем же tensor. При cfg 0 Mahiro не является гарантированным identity: `leap` обнуляется, а formula может вернуть лишь часть текущего CFG-result.

## Пример подключения

В полном census официального bundle 0.1.42 — 512 JSON, 496 root graphs и 272 subgraphs — прямых `Mahiro` и точных строковых упоминаний ID нет. Поэтому официальные widgets или рекомендуемая model family не зафиксированы.

Source-derived fragment соединяет `MODEL → Mahiro → KSampler` и использует runtime defaults KSampler: seed 0, 20 steps, cfg 8, Euler, simple, denoise 1. Эти значения нужны для замкнутого semantic fragment, а не являются найденным Mahiro preset. Fragment не выполнялся.

## Частые ошибки

**Ищут параметр интенсивности.** У ноды только MODEL input. Менять силу отдельно от downstream cfg нельзя.

**Считают similarity отдельной для каждого изображения.** После cosine по каналам код вызывает `.mean()` без измерений; получается один scalar для всего batch и пространства.

**Называют преобразование нормализацией tensors.** Source использует signed square root, а нормирование выполняется внутри cosine similarity. Это не деление каждого tensor на собственную норму в явном коде.

**Не учитывают post-hook order.** Перестановка Mahiro и CFGZeroStar меняет вход `denoised` следующей функции.

**Принимают search alias за execution alias.** Workflow должен сохранять class type `Mahiro`; строка `positive-biased cfg` нужна только поиску.

## Ограничения и производительность

Signed square roots, cosine similarity и смешение дешевле model forward, но создают несколько полноразмерных промежуточных tensors на каждом step. Для больших video batches это добавляет память и bandwidth.

Средний similarity общий для всего batch. Один элемент или участок tensor может изменить вес остальных элементов, поэтому сравнение batch_size 1 и большого batch не обязано совпадать с независимыми запусками.

`torch.nn.functional.cosine_similarity` использует epsilon для малых норм, но hook не проверяет уже появившиеся NaN или Inf. Нода имеет experimental flag, а официальный bundle не даёт рабочего reference case.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `Mahiro`, модуле `comfy_extras.nodes_mahiro`. Fingerprint: `sha256:a657e6ea447319c013397d0720c331a88ca4a3d4d319416208508dff5f02a32a`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacement и execution aliases отсутствуют.

Embedded docs 0.5.9 неточно называют сравниваемые tensors «normalized conditional and unconditional outputs» и обещают более точное направление генерации без benchmark. Русский файл дополнительно содержит постороннюю эмоциональную фразу в заголовке. Эти формулировки не перенесены в статью.

- [Реализация `Mahiro`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_mahiro.py#L8-L53)
- [Контракт post-CFG hooks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L605)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/Mahiro/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

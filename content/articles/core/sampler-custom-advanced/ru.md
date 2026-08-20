# SamplerCustomAdvanced: sampling из независимых компонентов

`SamplerCustomAdvanced` исполняет sampling, когда шум, guidance, алгоритм и расписание уже собраны отдельными нодами. Она принимает `NOISE`, `GUIDER`, `SAMPLER`, `SIGMAS` и `LATENT`, а затем возвращает итоговый latent и последнее доступное предсказание `x0`.

## 1. Что делает нода

Нода просит объект `NOISE` построить тензор под форму входного LATENT и передаёт его вместе с остальными компонентами в `GUIDER.sample`. Благодаря этому random/zero noise, обычный CFG, dual guider и специализированные sampler/scheduler можно комбинировать без изменения исполняющего узла.

Это низкоуровневая сборка стандартного sampling-пайплайна ComfyUI. Она не делает компоненты совместимыми автоматически: модель внутри GUIDER, SIGMAS, sampler и структура latent должны относиться к одному сценарию.

## 2. Место в графе

Перед нодой обычно стоят `RandomNoise` или `DisableNoise`, один из guider-узлов, sampler-конструктор и scheduler. `LATENT` приходит из empty latent, encoder или предыдущей стадии. После ноды ставят VAE Decode либо следующий latent-этап.

Выбирайте `SamplerCustomAdvanced`, если нужен отдельный `NOISE` или нестандартный `GUIDER`. Если достаточно обычных positive/negative conditioning и одного CFG, `SamplerCustom` короче и сам создаёт эти компоненты.

## 3. Входы

- `noise` — объект `NOISE`; тензор создаётся только после получения формы latent.
- `guider` — `GUIDER`, который хранит модель и логику guidance.
- `sampler` — алгоритм типа `SAMPLER`.
- `sigmas` — последовательность уровней шума.
- `latent_image` — исходный `LATENT`, включая возможные `noise_mask` и metadata.

Нода не имеет собственных seed, CFG или conditioning. Эти значения находятся внутри соответствующих объектов: seed — в NOISE, модель и conditioning — в GUIDER, алгоритмические параметры — в SAMPLER.

## 4. Выходы

- `output` — итоговый `LATENT`.
- `denoised_output` — последнее `x0`, если sampler сообщил его callback; иначе тот же объект, что и `output`.

Последнее `x0` проходит через `guider.model_patcher.model.process_latent_out` и переносится на CPU. Это оценка чистого latent на последнем доступном шаге, а не отдельный post-processing запуск. Результаты копируют metadata входа, но удаляют `downscale_ratio_spacial` и `downscale_ratio_temporal`.

## 5. Как работает

Нода сначала исправляет пустой latent по числу каналов и downscale-параметрам модели из `guider.model_patcher`. Затем вызывает `noise.generate_noise(latent_image)`, извлекает `noise_mask` и создаёт callback для `len(sigmas) - 1` переходов.

Основная работа выполняется в `guider.sample(noise, latent, sampler, sigmas, mask, callback, disable_pbar, seed)`. Guider подготавливает mask и модели, упаковывает обычные либо nested latent, исполняет sampler и освобождает дополнительные модели после завершения. Итог перемещается на intermediate device ComfyUI.

Если `SIGMAS` пуст, guider возвращает исходный latent без вызова алгоритма. Такой вход полезен лишь как диагностический крайний случай; для нормального sampling нужно расписание хотя бы с переходом.

## 6. Параметры и настройка

Настройка распределена по графу. Для воспроизводимости фиксируйте одновременно seed в NOISE, параметры GUIDER, sampler, SIGMAS и исходный LATENT. Изменение одного seed недостаточно, если scheduler или conditioning тоже меняются между очередями.

Проверяйте модельный контракт scheduler: некоторые расписания используют саму MODEL, другие строят числа независимо. `noise_mask` берётся из LATENT автоматически; отдельного порта у ноды нет. Если маска устарела после crop/rebatch, sampling может затронуть не ту область или завершиться ошибкой формы.

## 7. Проверенный пример

Recipe `Advanced custom sampling с Euler` показывает минимальную topology: внешние `NOISE`, `GUIDER`, `SIGMAS` и `LATENT`, `KSamplerSelect(euler)` и `SamplerCustomAdvanced`. Это распространённая форма официальных subgraph и безопасный каркас для подстановки совместимых компонентов.

Второй recipe воспроизводит участок официальных LTX 2.3 workflow: `SamplerEulerAncestral(eta = 0, s_noise = 1) → SamplerCustomAdvanced`, рядом приходят `RandomNoise`, `CFGGuider`, `ManualSigmas` и latent. Полный census нашёл 87 `SamplerCustomAdvanced`: 14 root и 73 subgraph; 81 mode 0 и 6 mode 4. Модельный fragment не исполнялся целиком.

## 8. Частые ошибки

- Передают MODEL вместо GUIDER. Модель должна быть упакована guider-нодой.
- Подключают тензор шума как LATENT либо NOISE в неверный порт.
- Собирают scheduler для одной модели, а GUIDER — для другой.
- Ищут seed или CFG внутри самой ноды; здесь таких параметров нет.
- Считают `denoised_output` отдельным финальным denoise-pass.
- Не замечают `noise_mask` в metadata входного LATENT.
- Подают пустой `SIGMAS` и принимают неизменившийся latent за успешную генерацию.

## 9. Ограничения и производительность

Разделение на компоненты не уменьшает стоимость sampling. Она определяется модельными вызовами, длиной SIGMAS, размером latent и логикой GUIDER. NOISE обычно строится на CPU, затем переносится по model path; последний `x0` также сохраняется на CPU для второго выхода.

Гибкость увеличивает число возможных несовместимых комбинаций. Runtime проверяет типы портов, но тип `SAMPLER` не кодирует модельное семейство, а `SIGMAS` не хранит декларативную гарантию происхождения. Для production workflow полезно начинать с официальной topology и менять компоненты по одному.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не experimental и не deprecated; formal replacement отсутствует.

Английская embedded docs упоминает mask, downscale metadata и `x0`; русский файл опускает эти детали. Ни один вариант не объясняет empty-latent repair, intermediate device, пустое расписание и жизненный цикл моделей. Формулировки здесь проверены по реализации ноды и `Guider.sample`.

- [SamplerCustomAdvanced в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L1028-L1082)
- [Guider sampling pipeline](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L1210-L1386)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

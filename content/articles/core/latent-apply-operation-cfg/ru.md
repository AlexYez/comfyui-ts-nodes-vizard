# LatentApplyOperationCFG

## Что делает нода

`LatentApplyOperationCFG` клонирует `MODEL` и добавляет pre-CFG hook. На каждом шаге sampler hook получает список предсказаний `conds_out` и применяет заданную `LATENT_OPERATION` до расчёта guidance.

При двух предсказаниях код обрабатывает разность первого и второго, затем возвращает базовый второй компонент: `operation(cond0 - cond1) + cond1`. Так меняется guidance-дельта, а не весь baseline одинаково.

## Когда она нужна и когда не нужна

Нода нужна для операций, которые должны действовать на model output каждого шага. Официальные ACE Step 1 workflow используют Reinhard tonemap перед CFG, чтобы ограничивать величину дельты в аудиосэмплинге.

Для однократного изменения готового LATENT используйте `LatentApplyOperation`. Не добавляйте hook автоматически ко всем моделям: его смысл зависит от sampler, числа conditioning-ветвей и выбранной операции.

## Короткий рецепт подключения

1. Пропустите ACE-модель через `ModelSamplingSD3` с shift `5`.
2. Создайте `LatentOperationTonemapReinhard(multiplier=1)`.
3. Подключите MODEL и операцию к `LatentApplyOperationCFG`.
4. Передайте новый MODEL в `KSampler`.

Эта внутренняя топология повторяется в трёх официальных workflow: song, music-to-music editing и instrumentals. В них KSampler использует 50 шагов, CFG 5, Euler/simple; denoise равен 1 для двух генераций и 0,3 для editing.

## Входы и hook-контракт

`model` — любой совместимый `MODEL`, способный работать с sampler pre-CFG functions. `operation` — callable `LATENT_OPERATION`. Нода возвращает clone модели и не меняет исходный объект.

Hook добавляется в список существующих `sampler_pre_cfg_function`, а не заменяет их. Порядок нескольких patch-нод поэтому имеет значение: операции выполняются последовательно в порядке регистрации.

## Выход и место в графе

Выход `MODEL` подключают к обычному или custom sampler. Нода не принимает conditioning, CFG-scale и latent напрямую; эти данные появляются во время выполнения sampler.

Ставьте её после model-sampling patch, если официальный граф требует такой порядок, и до sampler. В ACE templates цепочка именно `ModelSamplingSD3 → LatentApplyOperationCFG → KSampler`.

## Как работает формула

При `len(conds_out) == 2` hook мутирует элемент `0`: вычисляет `delta = conds_out[0] - conds_out[1]`, применяет operation и прибавляет `conds_out[1]`. Второй tensor остаётся прежним.

Если длина не равна двум, операция применяется только к `conds_out[0]`. Это относится и к одному, и к более чем двум элементам: дополнительные entries код не обрабатывает. Hook возвращает тот же list после изменения.

## Практический пример

Воспроизведите официальный ACE-фрагмент с Reinhard multiplier `1`. Сначала сделайте контрольный sampling без `LatentApplyOperationCFG`, затем подключите ноду, не меняя seed, conditioning, shift, steps и CFG.

Для unit-проверки можно использовать искусственные tensors: при операции `x → 2x`, cond0 `30` и cond1 `10` результат первого entry равен `50`, второй остаётся `10`. Это подтверждает обработку дельты `(30−10)`, а не простое удвоение cond0.

## Частые ошибки и проверка

- Ожидают изменения сохранённого LATENT. Hook работает с предсказаниями внутри sampler.
- Меняют порядок patch-нод и получают другой результат. Pre-CFG hooks накапливаются списком.
- Предполагают обработку всех ветвей при `len > 2`. Код меняет только индекс 0.
- Путают Reinhard multiplier с CFG. Это разные масштабы в разных формулах.
- Применяют 2D sharpen к video prediction. Проверьте tensor rank операции.

## Ограничения и производительность

Операция запускается на каждом шаге, поэтому её стоимость умножается на steps. Sharpen добавляет convolution, Reinhard — norm/statistics. Hook может увеличить пиковую память из-за временной дельты `cond0 - cond1`.

Нода не включает `disable_cfg1_optimization`; при CFG=1 поведение зависит от того, какие predictions фактически передаст sampler. Экспериментальный статус означает, что контракт может меняться.

## Совместимость, изменения и источники

Сверено с ComfyUI `0.32.0`, frontend `1.48.7`, тремя официальными ACE templates 0.1.42 и embedded docs 0.5.9. Найдено ровно три прямых случая. Replacement API пуст; нода experimental и не deprecated.

Редактор пока не проверил материал вручную. Статья остаётся техническим черновиком; exact hook выполнен на synthetic tensors, полные аудиомодели и sampling не запускались.

### Источники

- [LatentApplyOperationCFG](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_latent.py#L342-L371)
- [Накопление pre-CFG hooks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L120-L124)
- [Workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

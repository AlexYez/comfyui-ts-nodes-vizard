# LatentOperationTonemapReinhard

## Что делает нода

`LatentOperationTonemapReinhard` создаёт функцию `LATENT_OPERATION`, которая сжимает величину channel-вектора каждого spatial-элемента. Направление в пространстве каналов сохраняется, а большая magnitude плавно приближается к вычисленному пределу.

Это не image tone mapping и не изменение пиксельной яркости. Операция работает с tensor до VAE decode или с model prediction в `LatentApplyOperationCFG`.

## Когда она нужна и когда не нужна

Подтверждённый случай — три официальных ACE Step 1 workflow: Reinhard с multiplier `1` подключён к pre-CFG wrapper. Такой фильтр ограничивает редкие большие guidance-дельты относительно статистики текущего tensor.

Не применяйте ноду как универсальное исправление пересвета изображения. Для готового RGB нужны image-операции. При multiplier `0` runtime допускает значение, но формула даёт деление на ноль и non-finite output.

## Короткий рецепт подключения

1. Создайте `LatentOperationTonemapReinhard`.
2. Установите multiplier `1`.
3. Подключите выход к `LatentApplyOperationCFG.operation`.
4. Подайте MODEL после `ModelSamplingSD3(shift=5)`.
5. Используйте тот же KSampler, conditioning и seed для A/B-теста.

Связка извлечена из трёх официальных ACE templates; Wizard не выдаёт её за выполненную локально генерацию.

## Вход и выход

`multiplier` принимает `0…100`, шаг `0,01`, default `1`. Он масштабирует порог `top`, а не напрямую весь latent. Значения больше единицы ослабляют сжатие, меньшие положительные — усиливают.

Выход `LATENT_OPERATION` — callable, а не LATENT. Его нужно подключить к `LatentApplyOperation` или `LatentApplyOperationCFG`.

## Как вычисляется magnitude

Для 4D tensor `B×C×H×W` код берёт `vector_norm` по channel dimension и добавляет `1e-10`, получая `B×1×H×W`. Исходный latent делится на magnitude, формируя normalized direction.

Затем mean и стандартное отклонение magnitude считаются по всем оставшимся измерениям внутри каждого batch item. Порог равен `(mean + 5·std) · multiplier`.

## Формула Reinhard

Magnitude сначала делится на `top`, затем проходит `x/(x+1)` и снова умножается на `top`. Для положительного top это эквивалентно `m·top/(m+top)`: малые значения меняются умеренно, очень большие приближаются к top.

После этого новая magnitude умножается на normalized direction. Канальное направление сохраняется, если вход и промежуточные числа конечны.

## Практический пример

В ACE song и instrumentals official workflows стоят KSampler: 50 steps, CFG 5, Euler, simple, denoise 1. В editing используется та же связка, но denoise `0,3`. Во всех трёх Reinhard multiplier сериализован как `1,0000000000000002`, то есть обычная floating-point запись единицы.

Для synthetic проверки возьмите tensor с несколькими разными spatial magnitudes. Убедитесь, что направление каждого channel-вектора сохраняется, а максимальные нормы уменьшаются сильнее малых.

## Частые ошибки и проверка

- Выход подключён к порту LATENT. Нужна apply-нода.
- multiplier поставлен в `0` как «выключение». Используйте обход ноды или корректный identity-контроль; ноль даёт NaN/Inf.
- Tensor имеет единственную spatial-точку. `torch.std` с default correction может вернуть NaN.
- Эффект оценивают при разных seed или CFG. Зафиксируйте sampler.
- Ожидают жёсткий clamp. Reinhard — плавная рациональная функция.

## Ограничения и производительность

Операция вычисляет norm, mean и std, создаёт normalized tensor и несколько промежуточных значений. В pre-CFG режиме эта стоимость повторяется на каждом sampler step.

Для 5D latent norm по dim 1 работает, а статистика охватывает все последующие измерения; однако смысл для конкретной video/audio модели нужно проверять отдельно. Edge cases multiplier `0` и singleton statistics не защищены.

## Совместимость, изменения и источники

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, embedded docs `0.5.9` и 512 JSON official wheel. Ровно три прямых случая — ACE Step 1. Нода experimental, не deprecated, replacement отсутствует.

Редактор пока не проверил материал вручную. Формула и edge cases проверены exact-source tensor probe; полное ACE sampling не выполнялось.

### Источники

- [LatentOperationTonemapReinhard](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_latent.py#L373-L407)
- [Workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

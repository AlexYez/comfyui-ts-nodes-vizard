# Outpaint по схеме Flux Fill

Фрагмент повторяет центральную цепочку официального `flux_fill_outpaint_example`:

`LoadImage` → `ImagePadForOutpaint` → `InpaintModelConditioning` → `KSampler` → `VAEDecode` → `PreviewImage`.

Параметры padding (`400 / 0 / 400 / 400`, feathering `24`), `noise_mask=false` и настройки sampler (`20`, CFG `1`, `euler`, `normal`, denoise `1`) взяты из шаблона 0.1.42.

Перед вставкой подготовьте внешние ветки:

1. Flux Fill `MODEL` подключите к `KSampler`.
2. Positive conditioning после `FluxGuidance` подключите к `InpaintModelConditioning`.
3. Negative conditioning после `ConditioningZeroOut` подключите туда же.
4. Установите `ae.safetensors` в каталог VAE или замените loader тем VAE, который указан в официальной инструкции вашей модели.
5. Выберите входное изображение и при необходимости измените стороны расширения.

Не переносите `noise_mask=false` и CFG `1` в произвольную inpaint-модель. Эти значения относятся к проверенному Flux Fill workflow.

Рецепт намеренно не содержит полного workflow: без внешней Flux-модельной цепочки он был бы неполным и вводил бы в заблуждение. Фрагмент структурно проверен, но локальный запуск с весами и человеческое утверждение ещё не пройдены.

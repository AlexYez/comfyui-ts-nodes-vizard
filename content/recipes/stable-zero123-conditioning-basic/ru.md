# Подготовить один ракурс Stable Zero123

Фрагмент вставляет одну `StableZero123_Conditioning` и заполняет параметры из runtime-схемы: `256 × 256`, batch 1, elevation 0° и azimuth 0°.

Подключите к ноде одно опорное `IMAGE`, а также `CLIP_VISION` и VAE из совместимого Stable Zero123 checkpoint. Выходы `positive`, `negative` и `latent` предназначены для sampler, который использует `MODEL` из того же checkpoint.

Sampler и decode не включены. В официальном wheel workflow templates JSON 0.1.42 нет этой ноды, а схема не сообщает рекомендованные steps, CFG, sampler и scheduler. Для этих значений нужен отдельный источник по выбранному checkpoint.

Фрагмент не исполнялся как полный workflow. Синтетическая проверка вызвала точный метод ноды с тестовыми тензорами и подтвердила обработку RGB, camera embedding и форму нулевого latent; настоящие веса не загружались.

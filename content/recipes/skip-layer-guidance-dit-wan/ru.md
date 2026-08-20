# SkipLayerGuidanceDiT перед ModelSamplingSD3 в Wan 2.1

Подайте совместимый Wan 2.1 MODEL в `SkipLayerGuidanceDiT`: double- и single-индексы `9,10`, scale 3, окно 0,01–0,8, rescaling 0. Выход соедините с `ModelSamplingSD3`, shift 5.

Такой порядок и настройки сериализованы в `wan2.1_fun_control` и `wan2.1_fun_inp`. Поскольку SLG вычисляет sigma-границы до downstream `ModelSamplingSD3`, fragment намеренно сохраняет именно официальный порядок, а не выдаёт его за общий preset.

В fragment нет весов, temporal-attention patch, CFGZeroStar, conditioning, latent и sampler. Он проверен по schema и локальной topology, но не импортировался и не исполнялся.

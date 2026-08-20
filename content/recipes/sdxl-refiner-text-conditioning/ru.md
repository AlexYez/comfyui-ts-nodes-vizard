# Текстовое conditioning для SDXL Refiner

Подайте `CLIP` от совместимого Refiner checkpoint и задайте текст. Нода добавит к результату `aesthetic_score = 6.0`, `width = 1024`, `height = 1024`.

`ascore` — числовая метка в conditioning, а не автоматическая оценка изображения. Нода не читает пиксели и не проверяет, действительно ли подключён Refiner CLIP.

Выход подключается к ветви conditioning того sampler/guider, который работает с Refiner. Полная base → refiner цепочка требует модели, расписания сигм и latent, поэтому в этот fragment не включена.

В официальном wheel 0.1.42 exact NodeId отсутствует. Значения взяты из defaults `/object_info`, но пример не исполнялся с настоящим Refiner.

Редактор пока не проверил материал вручную.

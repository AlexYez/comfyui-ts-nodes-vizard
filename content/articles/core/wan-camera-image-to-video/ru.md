# WanCameraImageToVideo

## Назначение

`WanCameraImageToVideo` добавляет camera embedding, стартовые кадры и CLIP Vision-признаки в conditioning локальной Wan camera I2V. Нода создаёт пустой noise target, но не строит траекторию сама — для этого используется `WanCameraEmbedding`.

## Место в графе

Подключите `positive`, `negative`, VAE и геометрию. `camera_conditions`, `start_image` и `clip_vision_output` необязательны. Три выхода направляются в модельно-совместимый sampler; после него нужен Wan VAE decoder и video output.

## Входы

`width` и `height` меняются с шагом 16, `length` — с шагом 4, batch — от 1. Значения по умолчанию: 832×480, 81 кадр и batch 1. Для camera embedding используйте те же три геометрических значения, лучше через прямые соединения.

## Выходы

Пустой `LATENT` имеет форму `[batch,16,((length-1)//4)+1,height//8,width//8]`. Положительная и отрицательная ветви могут получить `camera_conditions`, `clip_vision_output`, `concat_latent_image` и `concat_mask`.

## Стартовые кадры

`start_image` ограничивается первыми `length` кадрами, масштабируется bilinear-методом с центральной обрезкой и кодируется VAE как RGB. Temporal latent записывается в начало Wan 2.1-нормализованной concat-основы и обрезается по целевой длине.

## Mask

До группировки mask имеет длину `Tlatent*4`. Первые `start_frames+3` позиции обнуляются, затем форма становится `[1,4,Tlatent,Hlatent,Wlatent]`. Mask и concat latent добавляются только если подключено стартовое изображение.

## Camera и CLIP Vision

`camera_conditions` и `clip_vision_output` просто записываются в metadata обеих conditioning-ветвей. Они не меняют форму пустого latent и не проверяются против width, height или length. Согласованность фактически проверит downstream-модель.

## Проверенный пример

Соедините все четыре выхода `WanCameraEmbedding`: embedding в `camera_conditions`, числа — в геометрию. Начните с Static и одного стартового кадра. После проверки формы смените preset на Pan или Zoom, не меняя остальные параметры.

## Ошибки и производительность

Несогласованное разрешение embedding и conditioning может проявиться поздно внутри модели. Без `start_image` VAE не вызывается, хотя порт остаётся обязательным по схеме. Центральная обрезка может удалить края исходного кадра, а длинный image batch увеличивает VAE-время.

## Совместимость и источники

Conditioning-путь проверен по `WanCameraImageToVideo` в `nodes_wan.py` ComfyUI 0.32.0. Полный camera workflow с весами и визуальная проверка соответствия выбранной траектории пока не выполнялись.

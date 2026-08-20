# MiniMaxH3ImageToVideo: T2VA и ключевые кадры

## Назначение

Нода объединяет текст, необязательные первый и последний кадры и пустой аудиовидеолатент MiniMax H3.

## Место в графе

Подайте совместимые CLIP и VAE; positive и latent идут в guider/sampler. Для чистого T2V оставьте оба изображения пустыми.

## Входы

`prompt` поддерживает dynamic prompts. Размер default 1344×768. `length` выравнивается вверх к сетке 17k+5. `first_frame` и `last_frame` необязательны.

## Выходы

`positive` содержит scheduled conditioning и при наличии кадров metadata keyframes. `LATENT` — NestedTensor из video/audio zeros.

## Первый кадр

Берётся только первый элемент batch и растягивается до canvas без сохранения пропорций (`crop=disabled`). Он получает `resolved_frame_index=0`.

## Последний кадр

Также берётся один IMAGE, но масштабирование использует aspect-preserving center cover-crop. Индекс равен последнему кадру уже выровненной длительности.

## Проверенный пример

Два официальных графа используют 1344×768 и length 73: I2V и T2V. Рецепт Wizard повторяет I2V-размеры, оставляя prompt и first frame внешними.

## Conditioning

Кадры передаются CLIP ещё при токенизации как images. Затем VAE-коды записываются в `minimax_keyframes`, а точная выровненная длина — в `minimax_frame_count`.

## Ограничения и производительность

Дополнительные элементы IMAGE batch игнорируются. First и last обрабатываются разными правилами геометрии. VAE и Qwen/CLIP могут потребовать значительную память.

## Совместимость и источники

Проверено по ComfyUI 0.32.0, frontend 1.48.7, source, runtime и двум templates 0.1.42. Embedded docs отсутствуют; полное sampling не выполнялось.

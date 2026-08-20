# Разобрать unCLIP-checkpoint и добавить референс

Выберите полный checkpoint, для которого подтверждена совместимость с SD 2.1 unCLIP. Fragment использует его `CLIP_VISION`, кодирует внешнее изображение с `crop = center` и добавляет embedding в базовое positive conditioning с `strength = 1` и `noise_augmentation = 0`.

`MODEL`, `CLIP` и `VAE` остаются доступными для остального графа, но fragment их не соединяет. В официальных templates 0.1.42 `unCLIPCheckpointLoader` отсутствует, поэтому это schema/source example, а не воспроизведение official topology. Checkpoint не загружался, fragment не выполнялся.

# WanSCAILToVideo

## Назначение
`WanSCAILToVideo` собирает conditioning и latent для SCAIL/SCAIL-2: pose-video, цветные identity masks, references, CLIP Vision и продолжение предыдущего чанка. Она не выполняет sampling и не декодирует результат.

## Место в графе
Подайте positive/negative, VAE и нужные optional sources. Четыре выхода идут в Wan sampler и следующую итерацию chunking. Цветные маски обычно приходят из `SCAIL2ColoredMask`.

## Входы
Размеры: width 32–16384 шаг 32, height аналогично, length 1–16384 шаг 4, batch 1–4096. Pose strength 0–10, диапазон 0–1. Offset начинается с 0; previous_frame_count по умолчанию 5 и меняется шагом 4.

## Выходы
Возвращаются обновлённые positive/negative, LATENT и новый `video_frame_offset`. Пустой latent имеет форму `[batch,16,(length-1)//4+1,height//8,width//8]`; при продолжении добавляется `noise_mask` с нулём на закреплённых первых latent-кадрах.

## Как работает
`ref_mask_flag` равен `not replacement_mode`. Каждая reference image отдельно масштабируется bicubic/center и отдельно кодируется VAE, чтобы batch не трактовался как видео. Reference latents добавляются списком в conditioning; CLIP Vision записывается обычным значением.

## Параметры
Pose и pose mask после offset совместно обрезаются до меньшей длины и формы `4n+1`, затем уменьшаются до половины разрешения. Pose latent умножается на strength и получает timestep range. Цветная маска преобразуется в семь бинарных цветов, /8 spatial и четыре временных кадра на 28 каналов.

## Проверенный пример
Четыре официальных экземпляра находятся в двух replacement workflow (обычный и int8): 512×896, length 65, batch 1, pose 1/0/1, offset 0, previous count 5, replacement true. Два экземпляра на файл обслуживают последовательные части графа.

## Частые ошибки
В replacement mode driving mask должна иметь белый фон, reference mask — чёрный; в animation наоборот. Reference mask без reference image игнорируется. Если offset уже за концом pose-video, соответствующий input выключается.

## Ограничения и производительность
Предыдущие кадры берутся только с хвоста, offset уменьшается на фактическое число anchor frames и ограничивается нулём. Reference batches кодируются циклом. Нода experimental; полный SCAIL-2 sampler и VAE в проверке не запускались.

## Совместимость и источники
Порты и fingerprint сверены с `/object_info` 0.32.0, shapes и metadata — с `nodes_scail.py`, пояснения — embedded-docs 0.5.9. Официальные пресеты переписаны из всех 512 JSON; человеческое утверждение ожидается.

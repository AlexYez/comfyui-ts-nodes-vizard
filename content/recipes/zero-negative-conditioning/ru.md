# Нулевое conditioning для negative-входа

Fragment воспроизводит цепочку из подграфа `basic_switch_node`: `CLIPTextEncode` создаёт conditioning, `ConditioningZeroOut` обнуляет его, а `KSampler` получает выход в `negative`. Текст и sampling widgets взяты из official case; MODEL, CLIP, positive и latent остаются внешними входами.

Исходный официальный workflow имеет ID `30235234-3bb4-42cc-9e1c-33ad1bba0192`. В его первом подграфе используются ноды № 56, № 54 и № 58; sampling-настройки — seed 12673005598788, 4 steps, CFG 1, `res_multistep`, `simple`, denoise 1.

Структура и widget values сверены, но fragment не запускался с закреплёнными model weights. Он не включает VAE decode и сохраняется со статусом `in_review`.

# Повторить начальную сигму Lotus depth

Фрагмент воспроизводит часть `flux_depth_lora_example`: `BasicScheduler` с `normal`, одним шагом и `denoise = 1`, затем `SetFirstSigma` со значением `10000`.

Это число относится к Lotus depth/model-sampling шкале. Не переносите его в SDXL, Flux, Wan или другую модель без отдельной проверки `sigma_max` и официального workflow.

Порты и widgets сверены с пакетом 0.1.42, а clone/index behavior — с exact-source probe. Модель, сэмплер и изображение не запускались; workflow-поле отсутствует.

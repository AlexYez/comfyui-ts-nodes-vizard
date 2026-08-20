# Вписать IMAGE-бэтч в 1280 × 720 и проверить размер

Подайте IMAGE во внешний вход. ResizeAndPadImage сохранит пропорции, добавит чёрные поля и вернёт точный размер `1280 × 720`; интерполяция — `lanczos`. GetImageSize покажет width, height и число элементов бэтча.

Настройки и связь с GetImageSize взяты из активной ноды № 722 официального `template_ltx2_3_ic_lora_ingredients`. Upstream RepeatImageBatch, preview и LTX subgraph оставлены за границей fragment.

Нода сохраняет batch_size входа. Если у IMAGE пять элементов, GetImageSize должен вернуть `1280`, `720`, `5`.

Fragment прошёл схему, но не исполнялся с реальным изображением. Человеческое утверждение ещё не выполнено.

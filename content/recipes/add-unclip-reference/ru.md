# Добавить визуальный референс через unCLIP

Фрагмент повторяет одну ступень официального `sdxl_revision_text_prompts`: `CLIPVisionEncode` с `crop = center` подаёт результат в `unCLIPConditioning` со `strength = 0.75` и `noise_augmentation = 0`.

Подключите visual encoder, изображение и positive conditioning от совместимого checkpoint. Для второго референса можно поставить такую же пару после первой, но strength складывающихся условий лучше проверять по одному.

Фрагмент не подтверждает совместимость произвольной модели с `unclip_conditioning`. Он проверен по схеме и точным портам; полный encode и sampling с весами не запускались.

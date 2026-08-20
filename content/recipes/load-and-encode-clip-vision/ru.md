# Загрузить CLIP Vision G и закодировать референс

Подключите внешнее `IMAGE` к `CLIPVisionEncode`. Fragment загружает `clip_vision_g.safetensors`, передаёт `CLIP_VISION` в encode и выбирает `crop = center`. Так соединены ноды №39 и №13/36 в официальном `sdxl_revision_text_prompts` с UUID `22fbfe6b-e7d7-4193-8409-8599b5dce771`.

Выход `CLIP_VISION_OUTPUT` ещё нужно направить в совместимую принимающую ноду, например `unCLIPConditioning`. Имя файла и структура связей подтверждены набором 0.1.42; веса не входят в проект, fragment не импортировался и не выполнялся.

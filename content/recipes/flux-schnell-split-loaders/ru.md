# Раздельная загрузка Flux.1 Schnell

Fragment основан на корневом графе official `flux_schnell_full_text_to_image`. `UNETLoader` № 38 выбирает `flux1-schnell.safetensors` и `default`; `DualCLIPLoader` № 40 загружает `clip_l.safetensors`, затем `t5xxl_fp16.safetensors`, с `type=flux` и `device=default`. Выход CLIP соединён с `CLIPTextEncodeFlux`, как link 59 в исходнике.

Тексты prompt сокращены редактором, но раздельные поля CLIP-L/T5 и guidance 3,5 сохранены. Выход `MODEL` оставлен для подключения к подходящей Flux sampling-цепи. Для полного workflow также нужны latent, sampler, `ae.safetensors` и декодирование; fragment не подменяет эти зависимости.

Структура проверена против `/object_info` и official JSON. Три файла весов не загружались, inference не выполнялся. Поэтому рецепт показывает доказанную компоновку загрузчиков, но не заявляет проверенное изображение.

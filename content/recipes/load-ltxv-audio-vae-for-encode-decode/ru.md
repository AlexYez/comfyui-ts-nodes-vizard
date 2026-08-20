# Один LTX Audio VAE для encode и decode

Фрагмент повторяет доказанную связь из официального `template_image_speech_to_video`: `LTXVAudioVAELoader` с checkpoint `ltx-2.3-22b-dev-fp8.safetensors` одновременно обслуживает `LTXVAudioVAEEncode` и `LTXVAudioVAEDecode`.

Перед вставкой убедитесь, что файл действительно лежит в `models/checkpoints`. Если используется другая версия LTX, замените preset на согласованный checkpoint и не смешивайте latent из разных audio VAE.

Внешний `source_audio` идёт в encode, а `sampled_audio_latent` — в decode. Рецепт не соединяет выход encode напрямую со входом decode: в рабочем графе между ними обычно находится sampling или сборка audio/video latent.

Проверены схема, типы портов и точная официальная топология loader→encode/decode. Веса LTX 2.3 и полный workflow не запускались, поэтому recipe остаётся `in_review`.

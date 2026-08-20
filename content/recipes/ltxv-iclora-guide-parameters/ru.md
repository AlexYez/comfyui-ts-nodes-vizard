# IC-LoRA metadata → LTXV guide

Fragment повторяет ключевую связь официального LTX 2.3 IC-LoRA subgraph: `MODEL` после LoRA Loader идёт в `GetICLoRAParameters`, затем `IC_LORA_PARAMETERS` подключается к `LTXVAddGuide(frame_idx=0, strength=1)`.

Подключите к guide positive, negative, VAE, video LATENT и референсный IMAGE. `iclora_model` должен быть выходом того же IC-LoRA Loader, для которого подготовлен референс. Если latent spatial grid не делится на извлечённый factor, guide завершится ошибкой до sampling.

Checkpoint, LoRA-файл, preprocessing, sampler и crop-guides не входят в fragment. Полный граф с реальными весами не исполнялся; схема и exact official topology проверены.

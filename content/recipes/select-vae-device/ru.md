# Направить VAE на второй GPU

Подайте `VAE` в `SelectVAEDevice` и выберите `device = gpu:1`. Нода создаёт отдельную wrapper-копию и patcher, а после retarget синхронизирует `first_stage_model` и поле `device`. Offload назначается по стандартной VAE-политике ComfyUI.

Если второго устройства нет, routing остаётся прежним. Значение `cpu` отсутствует в UI; импортированный fragment с таким значением runtime примет, но нода намеренно его отклонит и вернёт копию VAE с исходной маршрутизацией.

Fragment не выполняет encode/decode. Exact-source probe проверил `gpu:1`, `default`, `cpu` и unavailable-device на синтетической VAE-обёртке без весов и CUDA-вычислений.

Редактор пока не проверил материал вручную.

# Дискретная V-prediction модель перед scheduler

Fragment меняет `model_sampling` на дискретную V-параметризацию и сразу строит `SIGMAS` через `BasicScheduler`. Используйте его только с checkpoint, для которого V-prediction подтверждён источником модели.

## Подключение

Подайте исходный `MODEL` во внешний порт. Выход patch уже соединён со scheduler. Тот же выход `ModelSamplingDiscrete` подключите к guider; не используйте для него исходную модель.

## Настройки

Выбраны `v_prediction`, `zsnr = false`, scheduler `simple`, 20 шагов и полный denoise. Если модель требует zero-terminal-SNR, включайте его только после проверки training-конфигурации и диапазона sigma.

## Границы проверки

Точная нода не встретилась в 512 JSON официальных шаблонов 0.1.42. Fragment проверен по runtime/source, а patch-метод исполнен на model-config без весов. Полный sampling не выполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingDiscrete в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L42-L89)

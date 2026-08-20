# Собрать три reference images в заданном порядке

Подключите сцену к `images.image0`, заменяемый объект — к `images.image1`, персонажа — к `images.image2`. Такой порядок повторяет входы BatchImagesNode № 15 из официального `api_bfl_flux2_max_sofa_swap`; платная Flux2MaxImageNode в fragment намеренно не включена.

Первый IMAGE задаёт пространственную форму. Если остальные отличаются по размеру, BatchImagesNode применит bilinear resize с center crop. Для предсказуемой геометрии подготовьте источники заранее.

Preview Image показывает элементы бэтча, а не один коллаж. Если порядок неверен, поменяйте именно autogrow-входы. Fragment проверен по схеме и source-топологии, но в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [BatchImagesNode в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_post_processing.py#L514-L588)
- [Официальный `api_bfl_flux2_max_sofa_swap`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/api_bfl_flux2_max_sofa_swap.json)

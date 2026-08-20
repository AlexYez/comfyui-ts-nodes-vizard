# Подать LTXV Dual CFG Guider в advanced sampler

Fragment переносит точную локальную ветвь официальных LTX‑2.5 subgraph: `LTXVDualCFGGuider` с `video_cfg = 1` и `audio_cfg = 1` подключён к входу `guider` ноды `SamplerCustomAdvanced`.

Такая пара встречается пять раз: один раз в first/last-frame-to-video и по два раза в image-to-video и text-to-video. Во всех cases модель приходит от `UNETLoader`, conditioning — от LTXV conditioning/guide ветви, а sampler получает nested AV latent.

При равных шкалах исходник намеренно переходит к обычному single-CFG с video_cfg. Поэтому official `[1,1]` не демонстрирует раздельное усиление audio и video, хотя использует специальный guider как совместимый контракт AV-графа.

Fragment не переносит имена весов и остальную большую subgraph. Топология и widgets проверены, model-free probe выполнил split-формулу на синтетическом packed tensor, но полный LTX‑2.5 sampling не запускался. Редактор ещё не утверждал рецепт вручную.

## Источники

- [Официальный LTX‑2.5 T2V template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_5_t2v.json)
- [Реализация Dual CFG](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L1053-L1120)

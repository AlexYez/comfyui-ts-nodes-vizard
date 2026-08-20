# RGBA-кадры в прозрачный WebM

Подайте готовый пакет RGBA на `images`, а частоту исходного ролика — на `fps`. Оставьте `codec = vp9`: только эта ветка `SaveWEBM` выбирает `yuva420p` и передаёт четвёртый канал.

Фрагмент повторяет конечную часть официального шаблона Bria, но не включает удаление фона и `JoinImageWithAlpha`. Он не добавляет звук и не создаёт полный workflow. Значение `crf = 32` совпадает с шаблоном; для своего материала сравните несколько значений на коротком отрывке.

Проверьте сохранённый `.webm` в проигрывателе с поддержкой VP9 alpha. Отсутствие прозрачности в конкретном плеере ещё не доказывает, что альфа не записана.

Редактор пока не проверил материал вручную.

### Источники

- [SaveWEBM в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video.py#L12-L73)
- [Официальный Bria workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/api_bria_remove_video_background_transparent.json)

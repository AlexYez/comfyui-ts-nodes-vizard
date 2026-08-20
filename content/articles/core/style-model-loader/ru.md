# StyleModelLoader: подобрать модель стиля к vision-цепочке

`StyleModelLoader` читает checkpoint из `style_models` и возвращает `STYLE_MODEL`. В ComfyUI 0.32.0 loader распознаёт два разных семейства — классический StyleAdapter и Flux Redux; одинаковый socket скрывает их разные размеры признаков.

## Файл выбирается из style_models

Combo `style_model_name` строится из `models/style_models` и дополнительных путей этой категории. Каталог принимает общий набор расширений PyTorch и safetensors, но расширение не определяет семейство модели.

Loader разрешает полный путь через `folder_paths`, затем читает state dict с `safe_load=True`. Никакого свободного URL или произвольного пути у ноды нет.

## Marker в state dict выбирает реализацию

Если среди ключей есть `style_embedding`, создаётся `StyleAdapter`. Если найден `redux_down.weight`, создаётся `ReduxImageEncoder` для Flux Redux.

При отсутствии обоих markers функция поднимает `invalid style model`. Loader не пытается угадать архитектуру по имени файла и не конвертирует другие image adapter форматы.

## StyleAdapter ожидает признаки ширины 1024

Core создаёт legacy StyleAdapter с `width = 1024`, `context_dim = 768`, тремя attention-слоями и восемью style-токенами. На вход его модели поступает `last_hidden_state` из `CLIP_VISION_OUTPUT`.

После обработки каждый референс даёт токены ширины 768. Они подходят только к conditioning с такой же последней размерностью.

## Flux Redux ожидает SigCLIP ширины 1152

`ReduxImageEncoder` по умолчанию принимает признаки ширины 1152. Два linear-слоя проецируют их в размерность 4096, которую использует Flux text conditioning.

Официальный workflow выбирает `flux1-redux-dev.safetensors` вместе с `sigclip_vision_patch14_384.safetensors`. Это проверенная пара, а не взаимозаменяемые файлы с любым CLIP Vision.

## CLIP_VISION_OUTPUT не кодирует размерность

`CLIPVisionEncode` всегда возвращает один тип `CLIP_VISION_OUTPUT`, независимо от внутренней ширины vision-модели. `StyleModel.get_cond` передаёт его `last_hidden_state` прямо в загруженный style model.

Если vision encoder выдаёт 1024 вместо ожидаемых 1152 или наоборот, type checker провод разрешит, но матричная операция завершится ошибкой.

## CONDITIONING тоже должно быть совместимым

`StyleModelApply` добавляет style-токены к tensor conditioning через `torch.cat` по оси токенов. Последняя размерность должна совпасть: 768 для legacy StyleAdapter или 4096 для Flux Redux.

Loader не принимает checkpoint MODEL и не может проверить эту сторону пары заранее. Для Redux используйте Flux-conditioning из официальной ветви, для legacy adapter — рекомендованную ему text-модель.

## Нода только загружает веса

`StyleModelLoader` не принимает референсное IMAGE и не меняет conditioning. Изображение сначала кодирует `CLIPVisionEncode`, а `StyleModelApply` соединяет его признаки, STYLE_MODEL и исходное conditioning.

Поэтому фраза «применить стиль» относится ко всей цепочке. Сам loader не создаёт изображение и не запускает diffusion model.

## Кэш не следит за содержимым checkpoint

У loader нет `IS_CHANGED` с хэшем файла. При неизменном `style_model_name` execution cache может переиспользовать ранее созданный STYLE_MODEL.

Если перезаписать checkpoint под тем же именем, входная сигнатура останется прежней. После обновления весов очистите cache или перезапустите ComfyUI, чтобы не смешивать старый объект и новый файл.

## Официальный workflow использует две ссылки

В wheel 0.1.42 есть ровно один `StyleModelLoader`: нода № 42 в `flux_redux_model_example`. Она загружает `flux1-redux-dev.safetensors` и разветвляет один STYLE_MODEL в две `StyleModelApply`.

Каждая ссылка проходит через отдельную `CLIPVisionEncode`, обе apply-ноды имеют strength 1 и режим `multiply`, а conditioning идёт через них последовательно к BasicGuider. Так workflow добавляет два набора Redux-токенов.

## Shared fragment оставляет Flux conditioning внешним

Рецепт воспроизводит одну ветвь официальной схемы: SigCLIP loader и IMAGE идут в `CLIPVisionEncode`, Flux Redux loader — в `StyleModelApply`, а совместимое Flux `CONDITIONING` приходит извне. Настройки — center crop, strength 1 и multiply.

Fragment прошёл schema и topology checks, но весовые файлы не загружались и полный граф не исполнялся. Он также используется статьёй `StyleModelApply`; редактор пока не проверил материал вручную.

## Источники

- [StyleModelLoader в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1097-L1110)
- [Определение StyleAdapter и Flux Redux](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L1450-L1468)
- [Каталог и расширения style model](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L10-L38)
- [Размерности StyleAdapter](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/t2i_adapter/adapter.py#L203-L229)
- [Размерности Flux Redux](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/flux/redux.py#L6-L25)
- [Execution cache по входной сигнатуре](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_execution/caching.py#L82-L127)
- [Официальный Flux Redux workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/flux_redux_model_example.json)

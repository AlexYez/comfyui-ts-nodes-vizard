# PreviewGaussianSplat: интерактивный просмотр Gaussian Splat

## Что делает нода

`PreviewGaussianSplat` принимает splat-совместимый `File3D`, создаёт его копию во временной папке ComfyUI и сообщает frontend имя этой копии. Встроенное расширение Load3D загружает файл в интерактивный viewer. Пользователь может вращать камеру, менять размер области просмотра и сохранять состояние сцены в `viewport_state`.

Backend не переводит файл в тензор `SPLAT` и не растеризует его в `IMAGE`. Он возвращает исходный объект `model_3d`, метаданные трансформации, камеру, `width` и `height`. Временная копия нужна только браузерному viewer, которому доступен файловый маршрут `api/view?type=temp`.

Для `.spz`, `.splat` и `.ksplat` frontend сразу выбирает splat adapter. Расширение `.ply` неоднозначно: такой контейнер используют и Gaussian Splat, и обычные облака точек. Frontend читает заголовок через Spark `PlyReader` и считает PLY сплатом, если у вершины присутствуют все `scale_0…2` и `rot_0…3`. Иначе файл передаётся point-cloud adapter.

Нода имеет `output_node = true`, хотя у неё есть пять обычных выходов. Постановка в граф запускает preview-side effect и одновременно позволяет продолжить цепочку без повторной загрузки файла.

## Когда использовать и когда не использовать

Используйте `PreviewGaussianSplat`, когда нужно осмотреть уже созданный `File3D`: проверить ориентацию, границы, плотность, цвет, положение камеры либо подготовить `camera_info` для следующего 3D-узла. Она подходит после `SplatToFile3D` и после загрузчиков, которые сразу возвращают splat-файл.

Нода не заменяет `RenderSplat`. Viewer рисует сцену в браузере и предназначен для интерактивного осмотра. `RenderSplat` создаёт воспроизводимые `IMAGE` и `MASK` на backend, поддерживает фиксированную камеру и пакет turntable-кадров. Если изображение должно стать частью графа, выбирайте backend-рендер.

Не используйте preview как способ постоянного сохранения. Имя имеет вид `preview_splat_<uuid>.<format>`, а файл кладётся в temp. Для результата, который должен пережить очистку временной папки, передайте `File3D` в `SaveGLB` — runtime display name этой ноды равен `Save 3D Model`.

Обычный point-cloud PLY лучше подавать в `PreviewPointCloud`. Типы входов помогают не перепутать ветви, но окончательный выбор adapter для PLY всё равно зависит от содержимого заголовка.

## Короткий рецепт подключения

1. Получите `File3D` в формате PLY, SPZ, SPLAT или KSPLAT.
2. Подайте его во вход `model_3d`.
3. Оставьте `width = 1024` и `height = 1024` для первой проверки.
4. Откройте ноду и дождитесь загрузки файла после выполнения графа.
5. Поверните камеру; frontend запишет её состояние в `viewport_state` при следующей сериализации prompt.
6. Если состояние камеры должно прийти извне, подключите optional `camera_info`: оно имеет приоритет над данными `viewport_state`.

Fragment «Gaussian Splat File3D → PreviewGaussianSplat» содержит сам preview и два внешних входа: файл и frontend-managed `LOAD_3D`. В 512 JSON официального workflow wheel 0.1.42 точной ноды нет, поэтому fragment помечен как source-derived и не притворяется проверенным полным workflow.

## Входы, выходы и параметры

`model_3d` принимает объединённый тип `FILE_3D_SPLAT_ANY, FILE_3D_PLY, FILE_3D_SPLAT, FILE_3D_SPZ, FILE_3D_KSPLAT`. Backend использует `model_3d.format` как расширение временной копии и вызывает `save_to`.

`viewport_state` — обязательный `LOAD_3D`. Его виджет обслуживает frontend. При сериализации он возвращает словарь с текущими `camera_info` и `model_3d_info`, а также служебными пустыми полями image/mask/normal/recording.

`model_3d_info` — optional advanced `LOAD3D_MODEL_INFO`. Если вход подключён, его значение идёт в output и UI result. Иначе backend берёт `viewport_state["model_3d_info"]`, а при отсутствии значения использует пустой список.

`camera_info` — optional advanced `LOAD3D_CAMERA`. Подключённое значение имеет приоритет; fallback — `viewport_state["camera_info"]`, затем `None`.

`width` и `height` — обязательные `INT`, default `1024`, диапазон `1…4096`, шаг `1`. Frontend передаёт изменения в `load3d.setTargetSize`. Backend только возвращает числа: они не означают, что файл был растеризован в картинку этого размера.

Выходы: тот же `FILE_3D_SPLAT_ANY`, `LOAD3D_MODEL_INFO`, `LOAD3D_CAMERA`, `INT width`, `INT height`. Exact NodeId — `PreviewGaussianSplat`; display name — `Preview Splat`; module — `comfy_extras.nodes_load_3d`; category — `3d`.

## Типовые связки

`SPLAT → SplatToFile3D → PreviewGaussianSplat` — прямой путь от тензорного представления к browser preview. Выберите PLY, если нужно сохранить полные spherical harmonics, либо SPZ/KSPLAT для более компактного базового цвета.

Выход `model_3d` можно одновременно отправить в `SaveGLB`. Несмотря на NodeId, эта нода принимает общий File3D и сохраняет фактический формат, поэтому SPZ не превращается в GLB сам по себе.

`File3DToSplat` выполняет обратную операцию: разбирает контейнер в CPU float32 `SPLAT`, после чего доступны `GetSplatCount`, `TransformSplat` и `RenderSplat`. Preview такого разбора не делает.

Frontend-регистрация `Comfy.PreviewGaussianSplat` обрабатывает результат backend как `[filename, camera, model_info]`, загружает его из `temp`, затем применяет камеру и первую transform-запись после завершения текущего load generation. Это связывает Python node и Vue/Three/Spark viewer; без совместимого frontend останутся выходы, но встроенная сцена не появится.

## Практический пример

Exact-source probe создал memory-backed PLY из набора байтов и выполнил `PreviewGaussianSplat` с `width = 800`, `height = 600`. Backend сохранил байты без изменения во временный файл `preview_splat_<uuid>.ply`. Возвращённый `model_3d` оказался тем же Python-объектом, а размеры сохранились как `800` и `600`.

В `viewport_state` лежали камера и transform metadata, но probe дополнительно подключил явные `camera_info` и `model_3d_info`. В UI result и обычных outputs появились именно явные значения. Это подтверждает приоритет optional inputs.

Отдельный source-review frontend показал, что после выполнения путь нормализуется с `\` на `/`, записывается в `Last Time Model File` и загружается с `loadFolder = temp`. После remount frontend пытается восстановить этот путь без сообщения о 404. Временный файл мог быть уже очищен, поэтому такое восстановление не равно постоянному хранению.

Probe не запускал WebGL/Spark render и не оценивал вид сцены. Он проверял файловый и metadata-контракт, а не полный пользовательский пример.

## Частые ошибки и способы проверки

**Viewer пуст после выполнения.** Проверьте, пришёл ли в UI result непустой filename и существует ли temp-файл. Frontend показывает alert, когда `result[0]` отсутствует; 404 при тихом восстановлении старого preview может не показать toast.

**PLY открылся как облако точек.** Проверьте заголовок. Splat detection требует все три `scale_*` и четыре `rot_*`. Одного имени `.ply` недостаточно.

**Файл пропал после перезапуска.** Preview пишет в temp, а не output. Сохраните исходный `File3D` отдельной save-нодой.

**Камера из `viewport_state` не применяется.** Подключённый `camera_info` всегда сильнее fallback. Отсоедините его либо передайте нужное состояние явно.

**После изменения `width` картинка на диске не стала больше.** Нода не создаёт image-файл. Параметры задают target size viewer; для растрового результата нужен `RenderSplat`.

**Контекстное меню не предлагает экспорт.** Preview extension возвращает пустой список export items для splat adapter. Это отдельное ограничение frontend, не ошибка Python node.

## Производительность и внутреннее поведение

Backend копирует весь `File3D` в temp при каждом выполнении и создаёт уникальное имя. Для disk-backed источника `File3D.save_to` использует `shutil.copy2`; для stream-backed читает поток и записывает его целиком. Большой PLY или KSPLAT требует дополнительного места и последовательного ввода-вывода.

Frontend затем загружает те же байты по HTTP. `SplatModelAdapter` создаёт `SplatMesh` из Spark и ждёт `initialized`. Сцена добавляет отдельный Spark renderer. Значит peak memory включает исходный File3D, temp-копию, сетевую копию в браузере и GPU-ресурсы viewer.

Для PLY выполняется дополнительное чтение заголовка, чтобы выбрать splat или point-cloud adapter. Promise байтов кешируется на время одной загрузки, поэтому проверка и сам adapter не обязаны скачивать файл дважды.

После создания SplatMesh frontend задаёт quaternion `(1, 0, 0, 0)` в формате Three.js `xyzw`: это поворот на 180° вокруг X, согласующий 3DGS и viewer axes. Это viewer-трансформация, а не изменение байтов или выходного File3D.

## Совместимость, изменения и устаревание

Статья проверена по ComfyUI 0.32.0 и frontend 1.48.7. Backend source commit — `c2bcbecd…`, frontend commit — `6d6af63c…`. Нода экспериментальная и output-node; флаги `deprecated`, `dev_only`, `api_node` равны `false`. Replacement API не содержит `PreviewGaussianSplat`.

UI зависит от frontend extension `Comfy.PreviewGaussianSplat`, Load3D components, Three.js и Spark. Exact runtime schema сама по себе не описывает загрузчик, temp-folder routing и PLY disambiguation; при обновлении frontend эти контракты нужно проверять отдельно от backend fingerprint.

Embedded docs 0.5.9 верно перечисляет входные форматы и pass-through outputs, но не раскрывает temp lifecycle, content-based PLY routing, приоритет optional inputs и поведение remount. В workflow wheel 0.1.42 нода отсутствует.

## Связанные ноды и источники

`SplatToFile3D` создаёт подходящий контейнер из `SPLAT`; `File3DToSplat` возвращает его в тензорную форму; `RenderSplat` создаёт растровый результат. `PreviewPointCloud` использует тот же frontend shell для обычного PLY, но другой adapter.

Контракт сверялся с `comfy_extras/nodes_load_3d.py`, `PreviewUI3DAdvanced`, frontend `load3dPreviewExtensions.ts`, `LoaderManager.ts`, `SplatModelAdapter.ts`, `scripts/metadata/ply.ts` и embedded docs 0.5.9. Exhaustive census дал ноль официальных cases. Temp-file probe подтвердил copy, metadata precedence и pass-through; браузерный рендер и человеческое утверждение ещё ожидаются.

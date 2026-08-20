# SavePointCloud: сохранение point-cloud PLY с viewport

## Что делает нода

`SavePointCloud` сохраняет готовый point-cloud `File3D` в папку `output`, показывает результат во встроенном 3D-просмотрщике и возвращает входной объект дальше. Дополнительные выходы передают transform metadata, камеру, `width` и `height`.

Закреплённая схема принимает семейство `FILE_3D_POINT_CLOUD_ANY` и `FILE_3D_PLY`. Фактическая реализация не разбирает вершины и не проверяет, есть ли в PLY грани, цвета или Gaussian-поля. Она копирует байты и использует `File3D.format` как расширение результата.

Нода экспериментальная и одновременно помечена как output-node. Запись файла происходит как side effect, а пять обычных выходов позволяют продолжить ветвь без повторного чтения PLY.

## Когда использовать и когда не использовать

Используйте `SavePointCloud`, когда producer уже вернул point-cloud PLY как File3D, результат должен остаться в `output`, а состояние интерактивного viewport требуется downstream. Узкий тип делает назначение графа понятнее, чем универсальный `SaveGLB`.

Нода не создаёт облако точек из `IMAGE`, depth map, координат или `MESH`. Такое преобразование выполняется раньше специализированным producer. Она также не переводит PLY в другой контейнер и не упрощает набор точек.

Для Gaussian Splat PLY выбирайте `SaveGaussianSplat`: оба формата используют расширение `.ply`, но содержат разные свойства вершин и обслуживаются разными frontend-adapter. Для треугольного mesh, который нужно перекодировать, подходит `SaveGLB` с входом `MESH`.

Если постоянный файл не нужен, `PreviewPointCloud` создаёт временную копию. Если графу нужен raster `IMAGE`, сохранение PLY не заменяет render или capture.

## Короткий рецепт подключения

Source-derived fragment содержит один runtime-узел:

1. Получите `FILE_3D_POINT_CLOUD_ANY` в формате PLY.
2. Подайте его во вход `model_3d`.
3. Позвольте frontend-виджету сформировать обязательный `viewport_state`.
4. Оставьте `filename_prefix = 3d/ComfyUI`.
5. Для первого запуска используйте `width = 1024`, `height = 1024`.
6. Optional `camera_info` и `model_3d_info` оставьте неподключёнными, если нужны значения текущего viewer.

В workflow wheel 0.1.42 точного `SavePointCloud` нет. Fragment не содержит локальный файл и не выдумывает producer. Он проверен по runtime и source, но не считается официальной топологией или выполненным полным workflow.

## Входы, выходы и параметры

`model_3d` принимает multitype `FILE_3D_POINT_CLOUD_ANY, FILE_3D_PLY`. Tooltip runtime называет point cloud file `.ply`. На уровне Python ожидается `Types.File3D` с путём либо бинарным потоком.

`filename_prefix` — строка с default `3d/ComfyUI`. Helper создаёт имя `<prefix>_00001.<format>` и запрещает выход за пределы `output`. Для корректного PLY `format` должен быть `ply`. Пустая метка приводит к расширению `.glb`, но байты остаются PLY.

`viewport_state` имеет тип `LOAD_3D` и обслуживается frontend. Backend использует его `camera_info` и `model_3d_info`, когда optional advanced-входы не подключены. Несловарное состояние превращается в пустой объект.

`model_3d_info` и `camera_info` — optional advanced. Проверка идёт на `None`, поэтому пустой список model info или пустой словарь камеры считается явным override.

`width` и `height` — `INT` от `1` до `4096`, default `1024`, шаг `1`. Они задают target size/aspect viewer и выходят дальше без изменения.

Выходы: `FILE_3D_POINT_CLOUD_ANY model_3d`, `LOAD3D_MODEL_INFO`, `LOAD3D_CAMERA`, `INT width`, `INT height`. UI-result содержит output-путь, итоговую камеру и итоговый model info.

## Типовые связки

Producer облака точек подключается прямо к `SavePointCloud`, если его выход уже типизирован как File3D PLY. Между ними не нужна промежуточная конвертация: save-нода не получает пользы от повторного чтения тех же байтов.

`PreviewPointCloud → SavePointCloud` создаёт сначала временную контрольную копию, затем постоянную. Оба узла возвращают pass-through-состояние, поэтому модель, камера и размеры могут идти по одной связанной ветви.

`Load3D` умеет загружать `.ply` и возвращать общий `FILE_3D`. Совместимость прямого соединения зависит от runtime type matching: если общий тип не принимается узким входом, используйте producer с точным point-cloud типом, а не подменяйте NodeId или alias.

`SaveGLB` принимает `FILE_3D_POINT_CLOUD_ANY` через широкий multitype и может терминально сохранить тот же PLY. Он не возвращает файл и viewport дальше. `SaveGaussianSplat` нужен, когда PLY содержит Gaussian scale/rotation fields либо используется SPZ, SPLAT или KSPLAT.

## Практический пример

Exact-source probe создал memory-backed PLY с тестовыми байтами и выполнил `SavePointCloud` с префиксом `3d/pointcloud`, `width = 1`, `height = 4096`. Вместо словаря в `viewport_state` было передано некорректное строковое значение.

В `output` появился `3d/pointcloud_00001.ply`; байты совпали с входными. Первый выход сохранил object identity, размеры прошли без изменения, `model_3d_info` стал пустым списком, а `camera_info` — `None`. Это подтверждает, что файловая запись не зависит от готовности viewport и что backend не ограничивает соотношение сторон внутри допустимого диапазона.

Probe не утверждает, что тестовые байты являются валидным PLY: цель была проверить exact copy, fallback состояния и выходы. Реальный Three.js parse, отображение цвета и полный fragment не запускались.

Полный обход 512 JSON и 768 root/subgraph graphs не нашёл `SavePointCloud`. Поэтому практический пример основан на закреплённой реализации и помечен честно, без переноса topology другой 3D-ноды.

## Частые ошибки и способы проверки

**Входной тип не подключается.** Нода принимает point-cloud family и PLY, а не произвольный `MESH`, `SPLAT` или строку пути. Проверьте exact output producer в `/object_info`.

**PLY открылся как Gaussian Splat.** Frontend пробует splat adapter первым и проверяет Gaussian-поля в заголовке. Если они присутствуют, файл будет показан как splat независимо от названия save-ноды. Уточните происхождение PLY и выберите `SaveGaussianSplat`.

**PLY с гранями выглядит как mesh.** PointCloudModelAdapter проверяет индексный буфер. При наличии faces и обычном material mode он строит `THREE.Mesh`; режим point cloud принудительно показывает вершины точками. Save-нода не удаляет грани.

**Точки белые вместо исходного цвета.** Viewer использует vertex colors, только если PLY-loader создал атрибут `color`. Проверьте свойства файла и exporter upstream.

**После сохранения ожидалось прореживание или нормализация координат.** Backend ничего такого не делает. Viewer временно центрирует и масштабирует безгранное облако по bounding sphere для показа, но байты output и pass-through File3D не меняются.

**Файл назван `.glb`.** Producer не выставил `File3D.format = ply`. Исправьте метку у источника; эта нода не определяет формат по содержимому.

**Камера или transform metadata пусты.** Проверьте готовность frontend-виджета и optional overrides. Сам файл сохранится даже при несловарном viewport.

## Производительность и внутреннее поведение

Backend выполняет одно полное копирование и не использует GPU. Disk-backed File3D переносится через `shutil.copy2`, stream-backed читается с начала и записывается целиком. Структура PLY не валидируется, поэтому malformed-файл может сохраниться быстро и сломаться только при просмотре.

Frontend затем загружает output повторно. Для ASCII PLY при выбранном setting может применяться FastPLYLoader; в остальных случаях используется Three.js PLYLoader. Геометрии вычисляются vertex normals. Для облака без faces рассчитывается bounding sphere, после чего точки временно центрируются и масштабируются в viewer.

Большой point cloud расходует память на исходный File3D, output-копию, ArrayBuffer браузера, BufferGeometry и GPU-буферы. `width` и `height` меняют target viewport, но не число точек и не размер файла.

Если PLY содержит faces, frontend может построить mesh и дать дополнительные material modes. Для чистого point cloud capabilities ограничивают материалы режимом `pointCloud`; это UI-поведение, а не свойство сохранённого контейнера.

## Совместимость, изменения и устаревание

Статья привязана к ComfyUI 0.32.0 и frontend 1.48.7. Exact NodeId — `SavePointCloud`, display name — `Save Point Cloud`, module — `comfy_extras.nodes_save_3d`, category — `3d`. Нода экспериментальная и output-node; она не deprecated, не dev-only и не API-only. В replacement snapshot ID отсутствует.

Schema fingerprint: `sha256:42942d8ac3ab81716b586d8a2da9b0121a8fc17bb07f581ad4237a54d4ef02a0`. Особенно важны узкий union входа, выход `FILE_3D_POINT_CLOUD_ANY` и frontend PLY routing.

Frontend extension `Comfy.SavePointCloud` загружает output, сериализует `viewport_state`, связывает размеры с target viewer и восстанавливает камеру/первую transform-запись. Loader выбирает между SplatModelAdapter и PointCloudModelAdapter по содержимому PLY.

Embedded docs 0.5.9 правильно называет вход PLY и pass-through outputs, но не раскрывает отсутствие валидации, поведение PLY с faces, content-based splat routing и точный filename pattern. Русская embedded-страница также содержит служебную фразу переводчика, поэтому её текст не копировался.

## Связанные ноды и источники

`PreviewPointCloud` показывает временную копию с тем же state contract. `Load3D` загружает PLY и умеет выдавать общий File3D. `SaveGLB` — широкий терминальный writer, `SaveGaussianSplat` — сосед для Gaussian PLY и splat-контейнеров.

Факты сверены с `SavePointCloud` и shared helper в `nodes_save_3d.py`, `File3D`, frontend `load3dPreviewExtensions.ts`, `LoaderManager`, `PointCloudModelAdapter`, embedded docs 0.5.9 и exhaustive wheel census. Probe подтвердил PLY-extension, byte-preserving copy, несловарный viewport fallback, object identity и размеры; реальный PLY parse, WebGL и человеческое утверждение ещё ожидаются.

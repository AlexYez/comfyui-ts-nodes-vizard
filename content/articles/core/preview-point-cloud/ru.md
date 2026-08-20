# PreviewPointCloud: просмотр облака точек PLY

## Что делает нода

`PreviewPointCloud` принимает `File3D` с облаком точек PLY, копирует его во временную папку и передаёт frontend имя файла. Встроенный Load3D viewer читает PLY, строит Three.js geometry и показывает точки либо mesh, если в файле есть faces и выбран соответствующий material mode.

Backend-класс почти совпадает с `PreviewGaussianSplat`, но его типовой контракт уже: `FILE_3D_POINT_CLOUD_ANY` или `FILE_3D_PLY`. Временное имя начинается с `preview_pointcloud_` и заканчивается расширением `model_3d.format`.

Frontend делит PLY между двумя adapter. Сначала `SplatModelAdapter` проверяет наличие gaussian-полей scale и rotation. Если проверка отрицательная, срабатывает `PointCloudModelAdapter`. Поэтому название ноды не принуждает Gaussian Splat PLY отображаться как обычные точки: содержимое остаётся решающим.

Нода возвращает исходный File3D и состояние сцены. Она не создаёт новый PLY, не упрощает облако и не выдаёт `IMAGE`.

## Когда использовать и когда не использовать

Используйте ноду после генератора, конвертера или загрузчика, который возвращает point-cloud PLY. Она удобна для быстрой проверки распределения точек, vertex colors, ориентации и framing камеры перед сохранением или дальнейшей обработкой.

Не путайте обычный point cloud и 3D Gaussian Splat. В обоих случаях контейнер может называться `.ply`, но gaussian-версия содержит scale, rotation, opacity и spherical harmonics. Для неё предназначен `PreviewGaussianSplat`.

Preview не заменяет узел конвертации в mesh и не гарантирует пригодность данных для печати. Если PLY содержит faces, frontend может показать mesh; это свойство файла, а не реконструкция поверхности из точек.

Для долговременного результата нужна save-нода. Temp-копия может исчезнуть после очистки и не должна быть единственным экземпляром данных.

## Короткий рецепт подключения

1. Подайте point-cloud `File3D` во вход `model_3d`.
2. Оставьте `width = 1024`, `height = 1024`.
3. Выполните граф и дождитесь загрузки viewer.
4. Если точки не видны, проверьте границы, цвет и размер point material.
5. Сохраните нужный ракурс: frontend запишет camera state в `viewport_state`.
6. Для внешней камеры подключите optional `camera_info`.

Fragment «Point-cloud PLY → PreviewPointCloud» source-derived: в полном recursive census 512 workflow JSON точных instances нет. Он содержит внешний `FILE_3D_POINT_CLOUD_ANY` и управляемый frontend вход `LOAD_3D`, но не включает выдуманный полный workflow.

## Входы, выходы и параметры

`model_3d` — обязательный union `FILE_3D_POINT_CLOUD_ANY, FILE_3D_PLY`. Tooltip pinned runtime прямо ограничивает ожидаемый контейнер `.ply`.

`viewport_state` — обязательный `LOAD_3D`. Frontend сериализует туда camera и model transform. Без соответствующего custom widget это не обычный текстовый параметр.

`model_3d_info` — optional advanced `LOAD3D_MODEL_INFO`; подключённое значение сильнее `viewport_state.get("model_3d_info", [])`.

`camera_info` — optional advanced `LOAD3D_CAMERA`; подключённое значение сильнее `viewport_state.get("camera_info")`.

`width` и `height` — `INT` от `1` до `4096`, default `1024`, step `1`. Frontend синхронизирует их с target size viewer.

Выходы: `FILE_3D_POINT_CLOUD_ANY`, `LOAD3D_MODEL_INFO`, `LOAD3D_CAMERA`, ширина и высота. Exact NodeId — `PreviewPointCloud`, display name — `Preview Point Cloud`, module — `comfy_extras.nodes_load_3d`, category — `3d`. Нода experimental и output-node.

## Типовые связки

Типичный upstream — загрузчик или API-node, возвращающий `FILE_3D_PLY`. Выход `model_3d` preview можно отправить в `SaveGLB` для постоянного сохранения без повторной загрузки с диска.

`PreviewGaussianSplat` использует общий frontend extension factory и ту же temp-folder схему. Различаются runtime types и выбранный adapter. Это связанные ноды, но не aliases.

Point-cloud adapter умеет четыре material modes для PLY с faces: `original`, `pointCloud`, `normal`, `wireframe`. Для face-less geometry capabilities ограничиваются `pointCloud`. Нода не хранит этот выбор в Python schema; им управляет viewer.

Frontend configuration сначала загружает файл, затем применяет сохранённый material mode, camera и scene properties. Изменение widget width/height вызывает `setTargetSize`, но не меняет исходную геометрию.

## Практический пример

Exact-source probe создал memory-backed File3D с форматом `ply`, выполнил `PreviewPointCloud` и проверил temp-файл. Байты сохранились без изменения под именем `preview_pointcloud_<uuid>.ply`.

Когда optional inputs отсутствовали, backend взял `camera_info` и `model_3d_info` из `viewport_state`. При строке вместо словаря код заменил viewport на `{}`, вернул `model_3d_info = []` и `camera_info = None`. Значит повреждённое состояние не ломает этот fallback само по себе.

Frontend source показывает два пути разбора. ASCII PLY может идти через ускоренный `FastPLYLoader`, если setting `Comfy.Load3D.PLYEngine` равен `fastply`; иначе используется Three.js `PLYLoader`. Binary PLY всегда проходит через Three.js path.

Browser rendering не запускался. Probe подтверждает backend copy и metadata contract, но не видимость точек, material mode и производительность конкретного PLY.

## Частые ошибки и способы проверки

**PLY открылся как Gaussian Splat.** Проверьте scale/rotation properties в vertex header. Frontend намеренно отдаёт такой файл splat adapter до point-cloud fallback.

**Точки серые.** Point adapter ищет vertex attribute `color`. Если его нет, материал получает постоянный цвет `0xcccccc`.

**Объект выглядит как mesh.** PLY содержит faces и material mode не равен `pointCloud`. Переключите режим в viewer, если нужен именно набор точек.

**Gizmo недоступен.** Point-cloud capabilities ставят `gizmoTransform = false`. Это frontend-ограничение; metadata output не превращает viewer в редактор геометрии.

**После preview файл исчез.** Нода работает с temp. Сохраните File3D отдельно.

**Изменение width/height не меняет число точек.** Эти widgets управляют размером viewer, а не downsampling.

## Производительность и внутреннее поведение

Backend делает полную temp-копию. Frontend затем загружает весь PLY. Для больших облаков основная цена — disk I/O, HTTP transfer, parse и GPU buffers.

Face-less geometry нормализуется внутри point adapter: вычисляется bounding sphere, центр вычитается, а radius масштабируется к единице. Это изменение frontend geometry для показа, не исходного File3D. Если radius равен нулю, scale пропускается.

Точки используют `PointsMaterial(size = 0.005, sizeAttenuation = true)`. При наличии vertex colors включается `vertexColors`; без них применяется серый цвет. Geometry с faces сначала получает vertex normals и может строиться как `Mesh`.

Ускоренный FastPLY path предназначен только для ASCII. Setting не меняет binary parser и не влияет на backend copy.

## Совместимость, изменения и устаревание

Проверочная пара — ComfyUI 0.32.0 и frontend 1.48.7, commits `c2bcbecd…` и `6d6af63c…`. `experimental = true`, `output_node = true`; `deprecated`, `dev_only`, `api_node` равны `false`. Replacement API записи не содержит.

Нода зависит от frontend extension `Comfy.PreviewPointCloud`. Python fingerprint не обнаружит изменение PLY parser, material capabilities или normalization, поэтому каталог должен отслеживать и frontend baseline.

Embedded docs 0.5.9 корректно называет temp copy и PLY, но не описывает content-based splat routing, ASCII engine, bounding-sphere normalization и face-aware branch. Официальных workflow cases в 0.1.42 нет.

## Связанные ноды и источники

`PreviewGaussianSplat` нужен для gaussian PLY/SPZ/SPLAT/KSPLAT. В текущем каталоге нет отдельной статьи про point-cloud генератор, поэтому relations не указывают несуществующую цель.

Факты сверены с backend `PreviewPointCloud`, `File3D`, frontend `load3dPreviewExtensions.ts`, `LoaderManager.ts`, `PointCloudModelAdapter.ts`, PLY metadata helper и embedded docs 0.5.9. Probe подтвердил temp copy и fallback; full browser example и человеческое утверждение ожидаются.

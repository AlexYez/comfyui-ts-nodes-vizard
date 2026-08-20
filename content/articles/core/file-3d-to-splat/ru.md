# File3DToSplat: разбор PLY, SPLAT, KSPLAT и SPZ

## Что делает нода

`File3DToSplat` читает все bytes из `File3D`, выбирает parser и создаёт внутренний `SPLAT`. Результат всегда содержит один batch item: позиции `1 × N × 3`, линейные scales `1 × N × 3`, quaternion `wxyz`, opacity `1 × N × 1` и SH `1 × N × K × 3`.

Если `model_3d.format` равен одному из известных ключей `ply`, `splat`, `ksplat`, `spz`, этот metadata выбирает parser напрямую. Если format пуст или неизвестен, `_detect_splat_format` смотрит на bytes: `ply`, gzip magic, KSPLAT version header либо длину, кратную 32, для raw SPLAT.

Parser переводит storage conventions в render-ready values. PLY log scale проходит через `exp`, opacity logit — через sigmoid, quaternion нормализуется. Base-color formats преобразуют RGB в SH DC с `K = 1`.

Нода не загружает файл с произвольного пути и не пишет temp/output. Она работает с уже созданным `File3D`, который может быть disk-backed или stream-backed.

## Когда использовать и когда не использовать

Используйте ноду, когда файловый загрузчик, API или custom node возвращает splat container, а downstream ожидает `SPLAT`: `TransformSplat`, `GetSplatCount`, `RenderSplat`, `MergeSplat` или `SplatToMesh`.

PLY — лучший вариант для сохранения full spherical harmonics, если он действительно следует 3DGS property convention. KSPLAT, SPZ и raw SPLAT могут быть удобнее для обмена, но parser возвращает только базовый цвет даже там, где внешняя KSPLAT версия содержит дополнительные SH blocks: pinned reader сознательно пропускает их.

Не подавайте обычный mesh PLY. Parser ожидает vertex positions и может заполнить отсутствующие gaussian fields defaults, но результат не станет осмысленным Gaussian Splat. Preview frontend умеет отличать splat PLY от point cloud; backend `File3DToSplat` такого отдельного guard не делает.

Нода читает весь файл в память и не предназначена для streaming огромного контейнера по частям.

## Короткий рецепт подключения

1. Получите splat-совместимый `File3D`.
2. Подайте его в `File3DToSplat`.
3. Соедините выход с `GetSplatCount`.
4. Проверьте число, затем отправьте pass-through SPLAT в `RenderSplat` или transform chain.
5. Если цвет потерял view-dependent часть, проверьте исходный контейнер: SPZ/SPLAT и pinned KSPLAT reader возвращают только `K = 1`.
6. При ошибке parser сверяйте не только расширение, но и header/содержимое.

Fragment «Splat File3D → File3DToSplat → GetSplatCount» source-derived. В exhaustive census 512 JSON и 768 root/subgraph graphs точной `File3DToSplat` нет, поэтому полный workflow не приложен.

## Входы, выходы и параметры

`model_3d` — обязательный multitype: общий `FILE_3D` плюс `FILE_3D_SPLAT_ANY`, PLY, SPLAT, KSPLAT, SPZ. Других widgets нет.

PLY parser принимает только `binary_little_endian`; ASCII и big-endian вызывают `ValueError`. List properties внутри vertex element не поддерживаются. Имена property определяют смысл полей.

Если PLY не содержит `scale_0`, scale становится `0.01` по трём осям. Без `rot_0` используется identity `wxyz = [1,0,0,0]`; без opacity — единица. Цвет берётся из `f_dc`/`f_rest`, иначе из `red/green/blue`, иначе SH заполняется нулями.

Raw `.splat` требует длину, кратную 32 bytes. Record содержит float32 xyz/scale, uint8 RGBA и byte quaternion. KSPLAT reader поддерживает compression levels `0`, `1`, `2` и собирает sections; если splats нет, выдаёт error.

SPZ reader распаковывает gzip и поддерживает versions `1`, `2`, `3`. Version 1 positions float16; 2/3 — signed 24-bit fixed point. Quaternion v3 uses smallest-three packing, v1/v2 — три byte components.

Выход — `SPLAT`, CPU contiguous float32 tensors; `counts = None`, потому что batch состоит из одного ряда без padding. Exact NodeId `File3DToSplat`, display name `Get Splat`, module `comfy_extras.nodes_gaussian_splat`, category `3d/splat`.

## Типовые связки

`File3D → File3DToSplat → GetSplatCount` — диагностика импорта. `GetSplatCount` возвращает тот же SPLAT и число `N`, поэтому затем можно продолжить цепочку.

`File3DToSplat → TransformSplat → RenderSplat` позволяет исправить orientation/scale и получить backend image. Для интерактивной проверки можно параллельно подать исходный File3D в `PreviewGaussianSplat`.

`SplatToFile3D` выполняет обратное преобразование. PLY round-trip сохраняет all SH properties writer этой версии. KSPLAT/SPZ round-trip остаётся lossy по цвету и quantization.

Metadata format имеет приоритет над content detection. Если объект ошибочно помечен `format = ply`, но внутри лежит SPZ, нода запускает PLY parser и падает, хотя signature detector распознал бы gzip при пустом metadata.

## Практический пример

Probe экспортировал два реальных gaussians во все три writer formats, затем импортировал их. PLY вернул `positions 1 × 2 × 3` и SH `1 × 2 × 4 × 3`; KSPLAT и SPZ вернули те же positions shape, но SH `1 × 2 × 1 × 3`.

Отдельный 32-byte raw SPLAT record без format metadata распознался по делимости длины и дал один gaussian. PLY с пустым metadata распознался по prefix. Неверные 31 bytes дошли до `could not determine splat format`.

Интересный edge case: пустые bytes имеют длину `0`, а ноль кратен `32`. Detector выбирает raw SPLAT parser и возвращает пустой `SPLAT` формы `1 × 0 × 3` без exception. Следующий `SplatToFile3D` такой объект уже не экспортирует.

Probe также пометил SPZ bytes как `format = ply`: parser metadata победил detector и выдал `not a PLY`. Это подтверждает важность корректного `File3D.format`.

## Частые ошибки и способы проверки

**`unsupported PLY format ascii`.** Backend reader принимает только binary little-endian. Browser point-cloud viewer умеет ASCII PLY, но это другой parser и другой контракт.

**Файл имеет правильное расширение, но parser ошибается.** `File3D.format` мог быть неверным. Если источник memory-backed, задайте правильный `file_format` либо оставьте пустым для content detection.

**Обычный PLY превратился в странный SPLAT.** Отсутствующие gaussian fields получают defaults. Проверяйте scale/rotation/opacity/SH properties до импорта.

**После KSPLAT исчез higher-order SH.** Reader пропускает SH blocks и восстанавливает base RGB из color field. Это ограничение pinned реализации.

**SPZ не распаковывается.** Проверьте gzip magic, внутренний NGSP magic и version 1–3. Повреждение length может проявиться как struct/numpy error.

**Пустой файл не вызвал ошибку.** Для raw detector это валидная длина `0 × 32`. Проверьте `GetSplatCount` перед дальнейшей обработкой.

## Производительность и внутреннее поведение

`File3D.get_bytes()` читает disk-backed path целиком либо перематывает stream и читает его полностью. Parsers строят numpy views/arrays, затем `np.ascontiguousarray`, `torch.from_numpy` и `.float()` создают CPU float32 tensors.

PLY parser строит structured dtype из header properties. Higher-order SH требует память пропорционально `N × K`. `exp` и sigmoid выполняются в numpy float32 и могут overflow на экстремальных сторонних значениях; source не вводит общий sanitization.

KSPLAT parser обходит declared maximum sections, рассчитывает offsets и при compressed positions восстанавливает bucket coordinates. Он доверяет header достаточно, чтобы повреждённые offsets могли вызвать низкоуровневую numpy/struct ошибку.

SPZ сначала полностью gzip-decompresses payload. Peak RAM включает compressed bytes, raw bytes, numpy arrays и torch copies. Для большого файла это важнее стоимости самой node graph wiring.

## Совместимость, изменения и устаревание

Статья проверена по ComfyUI 0.32.0 commit `c2bcbecd…`. Флаги experimental/deprecated/dev_only/api/output равны `false`. Replacement API не содержит `File3DToSplat`.

Runtime description говорит об autodetect by contents, но source уточняет условие: известный `model_3d.format` выбирается раньше detector. После обновления проверяйте порядок, список KSPLAT compression levels и SPZ versions.

Embedded docs 0.5.9 правильно перечисляет форматы и full-SH distinction, но не описывает binary-only PLY, metadata precedence, defaults отсутствующих properties, empty raw edge case и memory cost. Official workflow 0.1.42 не содержит ноду.

## Связанные ноды и источники

`SplatToFile3D` создаёт контейнер; `PreviewGaussianSplat` показывает его без тензорного разбора; `GetSplatCount` проверяет N; `RenderSplat` растеризует imported SPLAT.

Контракт сверялся с readers/detector и class `File3DToSplat`, типами `File3D`/`SPLAT`, embedded docs 0.5.9 и exhaustive workflow census. Probe подтвердил PLY/SPLAT/KSPLAT/SPZ, shapes, SH loss, metadata precedence и ошибки. External corpus fuzzing, полный workflow и человеческое утверждение ещё ожидаются.

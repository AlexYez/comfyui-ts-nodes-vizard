# SplatToFile3D: сериализация SPLAT в PLY, KSPLAT или SPZ

## Что делает нода

`SplatToFile3D` превращает внутренний объект `SPLAT` в memory-backed `File3D`. Нода выбирает один из трёх writer: бинарный PLY, KSPLAT level 0 или gzip-сжатый SPZ v2. Она ничего не записывает в output сама; сохранением занимается следующая нода.

`SPLAT` хранит активированные значения: позиции в world space, линейные положительные масштабы, нормализованные quaternion `wxyz`, opacity в `0…1` и spherical harmonics формы `B × N × K × 3`. Writers преобразуют эти значения в соглашения конкретного контейнера.

Поддерживается только первый элемент batch. Если `B > 1`, код пишет warning и берёт index `0`. При наличии `counts` используется реальная длина `counts[0]`, а padding после неё не попадает в файл.

Результат содержит поток `BytesIO` и `file_format`. Расширение появляется позже, когда preview или save вызывает `File3D.save_to`.

## Когда использовать и когда не использовать

Используйте ноду перед `PreviewGaussianSplat` или `SaveGLB`, когда upstream возвращает тензорный `SPLAT`. Она нужна на границе между вычислительными splat-нодами и файловыми 3D-нодами.

Выбор формата зависит от данных. PLY сохраняет все SH coefficients и float32 geometry; он лучше для round-trip внутри ComfyUI, но обычно крупнее. KSPLAT writer создаёт uncompressed level 0 и оставляет только базовый цвет. SPZ v2 хранит base color, квантует позиции, scale, rotation и opacity, затем сжимает gzip.

Не ожидайте output для всего batch. Разбейте batch заранее и сериализуйте элементы отдельно. Иначе всё после первого элемента будет отброшено без exception.

Нода не умеет писать `.splat`: в source оставлен TODO. Combo предлагает только `ply`, `ksplat`, `spz`; вручную переданное `format = splat` вызывает `ValueError`.

## Короткий рецепт подключения

1. Подайте `SPLAT` в `SplatToFile3D`.
2. Выберите `spz`, если нужен компактный base-color файл; в официальном TripoSplat workflow используется именно этот вариант.
3. Соедините `model_3d` с `SaveGLB.mesh`.
4. Задайте `filename_prefix`, например `3d/ComfyUI_TripoSplat`.
5. Если нужен полный SH round-trip, смените format на `ply`.
6. Проверьте batch size и `counts[0]` до экспорта.

Рецепт «SPLAT → SPZ → Save 3D Model» повторяет точную official topology: node `92` с widget `spz` получает выход SPLAT subgraph `88`, а File3D идёт в node `51` `SaveGLB` с префиксом `3d/ComfyUI_TripoSplat`. Это один реальный case среди 512 workflow JSON.

## Входы, выходы и параметры

`splat` — обязательный `SPLAT`. Пять tensor fields должны иметь согласованные первые две оси. Writers ожидают хотя бы один реальный gaussian; пустой первый item приводит к `ValueError("SplatToFile3D: gaussian is empty")`.

`format` — `COMBO` с options `ply`, `ksplat`, `spz`. Runtime не задаёт отдельное поле default, поэтому ComfyUI использует первый option — `ply`. Метод `execute` также имеет Python default `"ply"`.

`ply` создаёт `format binary_little_endian 1.0`. Scale записывается как `log(scale)`, opacity как logit, quaternion остаётся `wxyz`. SH DC идёт в `f_dc_0…2`, остальные coefficients раскладываются channel-major в `f_rest_*`.

`ksplat` создаёт 4096-byte file header, 1024-byte section header и 44 bytes на gaussian. Это version `0.1`, compression level `0`, SH degree `0`. Base RGB вычисляется из DC: `rgb = clamp(sh_dc × C0 + 0.5)`; RGBA квантуется до uint8.

`spz` создаёт Niantic magic `NGSP`, version `2`, fractional bits `12`, SH degree `0`. Позиции — signed 24-bit fixed point, opacity/color/scale/rotation — byte fields, затем весь payload gzip-сжимается.

Выход — один `FILE_3D_SPLAT_ANY` под именем `model_3d`. Exact NodeId `SplatToFile3D`, display name `Create 3D File (from Splat)`, module `comfy_extras.nodes_gaussian_splat`, category `3d/splat`.

## Типовые связки

Официальная связка — `SPLAT → SplatToFile3D(format=spz) → SaveGLB`. Хотя downstream NodeId содержит GLB, runtime union принимает `FILE_3D_SPZ` и сохраняет `.spz`.

Для просмотра используйте `SplatToFile3D → PreviewGaussianSplat`. Preview создаст ещё одну temp-копию, но передаст исходный File3D дальше.

`File3DToSplat` — обратная нода. Для PLY round-trip сохраняются все SH terms. После KSPLAT/SPZ output имеет `K = 1`, потому что writer отбрасывает higher-order SH.

Перед экспортом можно поставить `TransformSplat`; его affine changes попадут в позиции, scale и quaternion файла. `RenderSplat` можно оставить параллельной ветвью для raster preview без сериализации.

## Практический пример

Exact-source probe создал batch из двух элементов. У первого item было три padded slots, но `counts[0] = 2`; у второго — один реальный gaussian. Все writers вернули форму `1 × 2 × 3` после обратного импорта. Второй batch item и padding не попали в данные, а код пять раз записал warning о `B = 2`.

PLY sample занял 835 bytes и вернул SH формы `1 × 2 × 4 × 3` побитово близко к source float32. KSPLAT занял 5208 bytes из-за фиксированных заголовков и вернул `K = 1`. SPZ sample занял 67 bytes и тоже вернул `K = 1`; gzip magic подтвердился.

Positions, scales, opacity и normalized rotation вернулись в допусках соответствующей точности. Для PLY допуск почти float32; для KSPLAT color/opacity — byte; для SPZ используются более грубые fixed-point и byte quantization.

Это синтетический round-trip writers/readers, а не полный TripoSplat generation. Official fragment schema проверен, но upstream subgraph с моделями не запускался.

## Частые ошибки и способы проверки

**Сохранился только один объект batch.** Это контракт ноды. Warning сообщает размер batch; exporter всегда берёт item `0`.

**После SPZ/KSPLAT пропали view-dependent оттенки.** Эти writers сохраняют только SH DC. Используйте PLY для higher-order spherical harmonics.

**Пустой SPLAT вызывает exception.** Проверьте `counts[0]` либо `positions.shape[1]`. Нулевая реальная длина не сериализуется.

**Файл получил расширение `.spz`, хотя downstream называется SaveGLB.** Save-нода уважает `File3D.format`; NodeId не заставляет перекодировать контейнер.

**Ручной format `splat` не работает.** Writer отсутствует. Combo намеренно не предлагает этот вариант.

**KSPLAT оказался крупнее маленького PLY.** Его fixed headers занимают 5120 bytes ещё до records. На маленьком N overhead доминирует.

## Производительность и внутреннее поведение

Все writers переносят выбранные tensors на CPU через `.cpu().numpy()` и собирают полный bytes payload в RAM. Memory-backed File3D хранит ещё одну копию. На больших splat наборах peak host memory может быть существенно выше конечного файла.

PLY использует float32 record со всеми SH coefficients, поэтому размер растёт примерно линейно с `N × K`. KSPLAT level 0 использует 44 bytes на gaussian плюс 5120 fixed bytes. SPZ raw payload использует примерно 16-byte header и 19 bytes на gaussian до gzip при SH degree 0.

SPZ writer квантует position с `2^12` units, canonicalizes quaternion sign `w ≥ 0` и отбрасывает `w`, восстанавливаемый parser по длине. Scale хранится как byte approximation log-space. Это lossy-преобразование.

PLY clip защищает `log(scale)` и logit opacity от бесконечностей. Он не нормализует quaternion перед записью; ожидается корректный активированный `SPLAT`.

## Совместимость, изменения и устаревание

Материал проверен по ComfyUI 0.32.0, commit `c2bcbecd…`, runtime fingerprint pinned. Флаги `experimental`, `deprecated`, `dev_only`, `api_node`, `output_node` равны `false`. Replacement API записи не содержит.

Official workflow 0.1.42 хранит node version `0.22.0`, widget `spz` и общий link type `FILE_3D`; exact runtime 0.32.0 выдаёт более узкий `FILE_3D_SPLAT_ANY`. Семантическая topology остаётся совместимой.

Embedded docs 0.5.9 правильно различает full SH PLY и base-color formats, но оценку «SPZ примерно в десять раз меньше» следует считать ориентиром source tooltip, а не гарантией для каждого файла. Probe на двух gaussians дал другое соотношение из-за headers и gzip.

## Связанные ноды и источники

`File3DToSplat` разбирает результат; `PreviewGaussianSplat` показывает его; `RenderSplat` создаёт images; `TransformSplat` меняет geometry до записи.

Факты сверены с writers и node class в `comfy_extras/nodes_gaussian_splat.py`, типами `SPLAT`/`File3D`, embedded docs 0.5.9 и официальным TripoSplat workflow 0.1.42. Probe подтвердил три формата, counts, batch truncation, empty/error branches и round-trip; human approval ожидается.

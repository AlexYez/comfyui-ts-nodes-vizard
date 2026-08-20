# SV3D_Conditioning: круговой маршрут камеры для SV3D

## Что делает нода

`SV3D_Conditioning` подготавливает positive conditioning, negative conditioning и нулевой `LATENT` для модели Stable Video 3D. Опорное изображение кодируется через CLIP Vision и VAE. В metadata conditioning записываются списки elevation и azimuth длиной `video_frames`.

Elevation одинаков для всех кадров. Azimuth начинается с 0° и увеличивается на `360 / (max(video_frames, 2) - 1)`. При двух и более кадрах маршрут заканчивается на 360°, то есть последний угол геометрически совпадает с первым.

Нода не запускает sampler, не декодирует изображения и не создаёт mesh. Её выходной latent использует первый размер как число кадров: `[video_frames, 4, height // 8, width // 8]`.

## Когда использовать и когда не использовать

Используйте ноду с совместимым SV3D checkpoint, когда из одного изображения требуется набор видов вокруг объекта. Вариант модели SV3D-p читает списки углов; SV3D-u использует изображение и reference latent, но его `encode_adm` не обращается к elevation и azimuth.

Нода не подходит для произвольной траектории камеры: пользователь задаёт только постоянный elevation, а azimuth всегда строится от 0° до 360°. Для явного ряда углов Stable Zero123 используйте `StableZero123_Conditioning_Batched`.

Слово Video в названии семейства не меняет типы выходов: нода возвращает conditioning и latent для многовидовой последовательности. FPS, звуковой поток и контейнер появляются только в следующих нодах. Геометрическую 3D-модель этот путь сам по себе не выдаёт.

## Короткий рецепт подключения

1. Загрузите SV3D checkpoint через `ImageOnlyCheckpointLoader`, чтобы получить согласованные `MODEL`, `CLIP_VISION` и VAE.
2. Подайте одно опорное `IMAGE`, `CLIP_VISION` и VAE в `SV3D_Conditioning`.
3. Задайте `width`, `height`, `video_frames` и постоянный `elevation`.
4. Подключите `positive`, `negative` и `latent` к sampler вместе с `MODEL` из того же checkpoint.
5. Декодируйте sampled latent тем же VAE. Если нужна видеозапись, передайте batch изображений в `CreateVideo` и задайте fps отдельно.

Фрагмент `recipe.sv3d-conditioning-orbit` содержит только conditioning-ноду с runtime-значениями `576 × 576`, 21 кадр и elevation 0°. Это не полный workflow: в официальном wheel 0.1.42 нет точного случая `SV3D_Conditioning`.

## Входы, выходы и параметры

Все семь входов входят в `input.required` закреплённого `/object_info`.

| Имя | Тип | Поведение в ComfyUI 0.32.0 |
| --- | --- | --- |
| `clip_vision` | `CLIP_VISION` | Получает pooled признаки опорного изображения. |
| `init_image` | `IMAGE` | Опорное изображение для CLIP Vision и VAE. |
| `vae` | `VAE` | Кодирует RGB-копию после center crop и bilinear resize. |
| `width` | `INT` | По умолчанию 576, диапазон 16–16384, шаг 8. |
| `height` | `INT` | По умолчанию 576, диапазон 16–16384, шаг 8. |
| `video_frames` | `INT` | Число видов, по умолчанию 21, диапазон 1–4096. |
| `elevation` | `FLOAT` | Один угол для всей последовательности, −90…90°, по умолчанию 0°, шаг 0,1°. |

`positive` содержит pooled CLIP tensor, VAE reference latent и оба списка углов. `negative` содержит нулевые pooled/latent tensors, но те же списки углов. `latent` — нулевой tensor на CPU без `batch_index`.

## Типовые связки

`ImageOnlyCheckpointLoader` → `SV3D_Conditioning` обеспечивает модель, vision encoder и VAE из одной контрольной точки. Это особенно важно здесь: ComfyUI распознаёт SV3D-u и SV3D-p как разные model configs с разным размером ADM conditioning.

`SV3D_Conditioning` → `KSampler` передаёт reference image и маршрут камеры в модель. Конкретные sampler, scheduler, CFG и число шагов не определяются схемой ноды; их следует брать из проверенного руководства к checkpoint.

`KSampler` → `VAEDecode` возвращает batch изображений. `VAEDecode` не добавляет временные metadata. Для файла-видео используйте `CreateVideo` после decode и явно выберите frame rate.

`StableZero123_Conditioning_Batched` решает похожую задачу другим семейством модели и позволяет задавать оба шага камеры вручную. Его batch получает одинаковый исходный шум через `batch_index`; `SV3D_Conditioning` такого поля не создаёт.

## Практический пример

При значениях по умолчанию `video_frames = 21` и `elevation = 0` шаг azimuth равен 18°. Список начинается с 0° и заканчивается 360°:

`0°, 18°, 36°, …, 342°, 360°`.

Первая и последняя камера совпадают по направлению. Такой endpoint заложен в формулу ноды; если последующий формат не требует замкнутого кадра, повтор можно удалить после генерации.

Граничные случаи следуют из той же формулы. Один кадр получает `[0°]`. Два кадра получают `[0°, 360°]`, то есть два одинаковых направления. Прямой вызов закреплённого метода для пяти кадров дал `[0°, 90°, 180°, 270°, 360°]`, постоянный elevation 15° и latent формы `[5, 4, 5, 7]`. В проверке использовались тензоры и заглушки encoder; модель с весами не запускалась.

## Частые ошибки и способы проверки

- **Углы не влияют на результат.** Проверьте тип checkpoint. `SV3D_u.encode_adm` игнорирует elevation и azimuth; camera schedule кодирует `SV3D_p`.
- **Первый и последний кадр почти одинаковы.** Маршрут включает и 0°, и 360°. Это не ошибка округления.
- **При двух кадрах нет второго ракурса.** Формула даёт 0° и 360°. Для двух разных направлений эта нода не предоставляет настройки шага; увеличьте число кадров и выберите нужные результаты позже либо используйте другой conditioning-путь.
- **Нужен другой стартовый azimuth или неполный круг.** В runtime таких входов нет. Редактирование списка возможно только другой нодой или реализацией, а не скрытым параметром `SV3D_Conditioning`.
- **Sampler получает несовместимые условия.** Загрузите `MODEL`, `CLIP_VISION` и VAE из одного SV3D checkpoint через image-only loader.
- **Объект обрезан или меняет масштаб.** CLIP Vision и VAE используют разные preprocessing-ветви с центрированием. Подготовьте квадратное изображение с объектом по центру, если это соответствует checkpoint.
- **Памяти не хватает.** Уменьшите `video_frames` или разрешение; оба множителя прямо увеличивают latent и работу sampler.

## Производительность и внутреннее поведение

CLIP Vision и VAE кодируют опорное изображение один раз. VAE-ветвь делает center crop, bilinear resize до `width × height` и оставляет первые три канала. Затем создаются два коротких списка углов и нулевой latent, объём которого линейно растёт с `video_frames`.

Базовый код SVD/SV3D приводит `concat_latent_image` к пространственному размеру noise и размножает его по числу кадров. P-вариант дополнительно кодирует augmentation в 256 значений, polar angle `90° − elevation` в 512 и azimuth в 512. В результате ширина ADM равна 1280. U-вариант создаёт только 256-компонентный augmentation ADM и не читает camera lists.

При `video_frames = 21` сам нулевой latent 576 × 576 имеет форму `[21, 4, 72, 72]`. Это лишь небольшая часть памяти полного прохода: временное внимание SV3D и промежуточные активации sampler требуют существенно больше. Точная пиковая память зависит от checkpoint, dtype, устройства и настроек семплирования; в этой проверке она не измерялась.

## Совместимость, изменения и устаревание

Материал привязан к ComfyUI 0.32.0 и frontend 1.48.7. Runtime flags: `deprecated: false`, `experimental: false`, `api_node: false`, `dev_only: false`. Replacement API не содержит `SV3D_Conditioning` ни как старый, ни как новый ID.

Schema fingerprint: `sha256:bcf423ac3af14c084e58691891d2159fee629a5b1f035e7ffda7ea3e343f21d5`.

Рекурсивный просмотр workflow templates JSON 0.1.42 охватил 512 JSON, 496 root workflow, 272 subgraph и 8120 нод. Exact ID отсутствует и как строка, и как `node.type`; подтвердить topology и widgets официальным примером из этого wheel нельзя.

Встроенная документация 0.5.9 сообщает о последовательности elevation/azimuth, но не приводит формулу 0–360°, дублированный endpoint и различие SV3D-u/SV3D-p. Русская версия помечает скалярные виджеты как необязательные и переводит exact port identifiers. Эти расхождения исправлены по `/object_info` и коду.

## Связанные ноды и источники

- `ImageOnlyCheckpointLoader` — загрузка SV3D model, CLIP Vision и VAE одним комплектом.
- `KSampler` и `VAEDecode` — семплирование и декодирование многовидового latent.
- `CreateVideo` — упаковка декодированного batch в видео с выбранным fps.
- `StableZero123_Conditioning_Batched` — управляемый шаг elevation/azimuth в другом семействе модели.
- [Точная реализация `SV3D_Conditioning`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_stable3d.py#L110-L153).
- [Различие SV3D-u и SV3D-p в model conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L535-L609).
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SV3D_Conditioning/en.md).

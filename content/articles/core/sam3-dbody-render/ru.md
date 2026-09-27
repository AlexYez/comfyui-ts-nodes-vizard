# Render 3D Body Pose: изображение позы и управляющие карты

Рендерит позу в IMAGE: поверхность тела, силуэт, плоский или объёмный OpenPose либо SCAIL-капсулы. Позволяет проверить реконструкцию и подготовить визуальное управление для совместимых моделей.

## Как пользоваться

pose_data принимает MHR и поддерживаемый внешний rig. render_style раскрывает настройки выбранного представления. Нулевые width/height используют исходный размер; если задана одна сторона, другая сохраняет пропорции. background необязателен, camera_info заменяет предсказанную камеру. Silhouette выходит как изображение, не разъём MASK.

## Пример подключения

Подключите результат Smooth и исходные кадры как фон, чтобы оценить совпадение позы. Затем уберите фон и выберите openpose_2d для модели, ожидающей такую карту. Проверьте поддержку рук и лица у целевого ControlNet до включения лишних деталей.

## Ограничения и частые ошибки

Разные стили не взаимозаменяемы для обученного conditioning: SCAIL и OpenPose имеют разное кодирование. Смена камеры меняет проекцию, а не исправляет исходную позу. При коротком batch фона последний кадр повторяется. Рендер не сохраняет анимированный скелет — для этого нужен BuildPoseFile.

## Входы и настройки

Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.

| Вход | Тип | Обязательный | Значения из схемы |
| --- | --- | --- | --- |
| `pose_data` | `MHR_POSE_DATA,KIMODO_POSE_DATA` | да | соединение / значение без фиксированного default |
| `width` | `INT` | да | по умолчанию: 0; минимум: 0; максимум: 16384; шаг: 8 |
| `height` | `INT` | да | по умолчанию: 0; минимум: 0; максимум: 16384; шаг: 8 |
| `render_style` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: mesh, silhouette, openpose_2d, openpose_3d, scail |
| `render_style=mesh → shader` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: default, normals, rainbow, rainbow_face_normal, rainbow_face_semantic, depth |
| `render_style=mesh → shader=rainbow → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → shader=rainbow → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → shader=rainbow_face_normal → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → shader=rainbow_face_normal → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → shader=rainbow_face_semantic → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → shader=rainbow_face_semantic → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `render_style=mesh → opacity` | `FLOAT` | да | по умолчанию: 1.0; минимум: 0.0; максимум: 1.0; шаг: 0.01 |
| `render_style=mesh → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `render_style=mesh → region` | `COMBO` | да | по умолчанию: full_body; варианты: full_body, hands_only |
| `render_style=openpose_2d → marker_radius_px` | `INT` | да | по умолчанию: 4; минимум: 1; максимум: 32; шаг: 1 |
| `render_style=openpose_2d → stick_width_px` | `INT` | да | по умолчанию: 4; минимум: 1; максимум: 32; шаг: 1 |
| `render_style=openpose_2d → limb_alpha` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.0; максимум: 1.0; шаг: 0.05 |
| `render_style=openpose_2d → face_style` | `COMBO` | да | по умолчанию: disabled; варианты: disabled, full, eyes_mouth |
| `render_style=openpose_2d → hand_style` | `COMBO` | да | по умолчанию: disabled; варианты: disabled, dwpose, openpose |
| `render_style=openpose_2d → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `render_style=openpose_3d → radius_m` | `FLOAT` | да | по умолчанию: 0.015; минимум: 0.004; максимум: 0.1; шаг: 0.001 |
| `render_style=openpose_3d → include_hands` | `BOOLEAN` | да | по умолчанию: true |
| `render_style=openpose_3d → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `render_style=scail → radius_m` | `FLOAT` | да | по умолчанию: 0.022; минимум: 0.005; максимум: 0.2; шаг: 0.001 |
| `render_style=scail → hand_style` | `COMBO` | да | по умолчанию: dwpose; варианты: disabled, dwpose, openpose |
| `render_style=scail → face_style` | `COMBO` | да | по умолчанию: disabled; варианты: disabled, full, eyes_mouth |
| `render_style=scail → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `background` | `IMAGE` | нет | соединение / значение без фиксированного default |
| `camera_info` | `LOAD3D_CAMERA` | нет | соединение / значение без фиксированного default |

## Выходы

| Выход | Тип | Список |
| --- | --- | --- |
| `image` | `IMAGE` | нет |

## Проверенные источники и кейсы

В официальном шаблоне `utility_sam3d_body`: Граф: main (root). Входящие связи: `GetVideoComponents`, `SAM3DBody_Smooth`. Исходящие связи: `CreateVideo`. Имя файла: `utility_sam3d_body.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

[Реализация в ComfyUI 0.37.0](https://github.com/Comfy-Org/ComfyUI/blob/73c9bad4d21e7addbe1d13bc92eee0f1431b017d/comfy_extras/nodes_sam3d_body.py#L855-L1087). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.

Статья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.

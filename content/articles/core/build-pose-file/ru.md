# Create 3D Animation File: экспорт позы в GLB или BVH

Создаёт файл анимации из данных позы. GLB может содержать тело, визуализацию костей, OpenPose или SCAIL; BVH предназначен для переноса движения одного скелета.

## Как пользоваться

format раскрывает настройки формата и mesh_style. Для body_mesh, bones_only и BVH нужны SAM3D-модель либо внешний skeleton_override. fps задаёт скорость воспроизведения. camera_translation: off оставляет базовое положение, centered переносит смещение относительно первого кадра, absolute использует оценённый перенос камеры. track_index выбирает человека; -1 означает всех для GLB, но первый трек для BVH.

## Пример подключения

После проверки позы в Render выберите GLB/body_mesh, подключите исходную модель и укажите FPS исходного видео. Выход model_3d отправьте в ноду сохранения 3D. Для ретаргетинга в другой программе попробуйте BVH, явно выберите человека и согласуйте units: cm или m.

## Ограничения и частые ошибки

Нода возвращает файл в памяти, а не автоматически пишет его на диск. Неверный FPS меняет скорость движения. Абсолютный перенос может отнести персонажа далеко от начала координат из-за оценённой глубины. BVH не сохраняет поверхность и все возможности GLB; ретаргетинг на другой rig требует отдельной проверки.

## Входы и настройки

Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.

| Вход | Тип | Обязательный | Значения из схемы |
| --- | --- | --- | --- |
| `pose_data` | `MHR_POSE_DATA,KIMODO_POSE_DATA` | да | соединение / значение без фиксированного default |
| `format` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: glb, bvh |
| `format=glb → mesh_style` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: body_mesh, bones_only, openpose, scail |
| `format=glb → mesh_style=body_mesh → bone_vis` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: off, octahedrons |
| `format=glb → mesh_style=body_mesh → bone_vis=octahedrons → bone_vis_radius_m` | `FLOAT` | да | по умолчанию: 0.02; минимум: 0.005; максимум: 0.5; шаг: 0.005 |
| `format=glb → mesh_style=body_mesh → bone_vis=octahedrons → bone_vis_color` | `COMBO` | да | по умолчанию: rainbow_y; варианты: white, rainbow_y |
| `format=glb → mesh_style=body_mesh → shader` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: default, rainbow, rainbow_face_normal, rainbow_face_semantic |
| `format=glb → mesh_style=body_mesh → shader=rainbow → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_normal → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_normal → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_normal → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_semantic → rainbow_tilt_z` | `FLOAT` | да | по умолчанию: -35.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_semantic → rainbow_tilt_x` | `FLOAT` | да | по умолчанию: 0.0; минимум: -90.0; максимум: 90.0; шаг: 0.5 |
| `format=glb → mesh_style=body_mesh → shader=rainbow_face_semantic → person_palette_falloff` | `FLOAT` | да | по умолчанию: 0.6; минимум: 0.1; максимум: 1.0; шаг: 0.05 |
| `format=glb → mesh_style=bones_only → bone_vis` | `COMFY_DYNAMICCOMBO_V3` | да | режимы: octahedrons |
| `format=glb → mesh_style=bones_only → bone_vis=octahedrons → bone_vis_radius_m` | `FLOAT` | да | по умолчанию: 0.02; минимум: 0.005; максимум: 0.5; шаг: 0.005 |
| `format=glb → mesh_style=bones_only → bone_vis=octahedrons → bone_vis_color` | `COMBO` | да | по умолчанию: rainbow_y; варианты: white, rainbow_y |
| `format=glb → mesh_style=openpose → marker_radius_m` | `FLOAT` | да | по умолчанию: 0.01; минимум: 0.005; максимум: 0.1; шаг: 0.001 |
| `format=glb → mesh_style=openpose → stick_radius_m` | `FLOAT` | да | по умолчанию: 0.008; минимум: 0.002; максимум: 0.05; шаг: 0.001 |
| `format=glb → mesh_style=openpose → include_hands` | `BOOLEAN` | да | по умолчанию: false |
| `format=glb → mesh_style=openpose → hand_marker_radius_m` | `FLOAT` | да | по умолчанию: 0.005; минимум: 0.001; максимум: 0.1; шаг: 0.001 |
| `format=glb → mesh_style=openpose → hand_stick_radius_m` | `FLOAT` | да | по умолчанию: 0.003; минимум: 0.001; максимум: 0.05; шаг: 0.001 |
| `format=glb → mesh_style=openpose → face_style` | `COMBO` | да | по умолчанию: disabled; варианты: disabled, full, eyes_mouth |
| `format=glb → mesh_style=openpose → face_marker_radius_m` | `FLOAT` | да | по умолчанию: 0.0; минимум: 0.0; максимум: 0.05; шаг: 0.0005 |
| `format=glb → mesh_style=scail → stick_radius_m` | `FLOAT` | да | по умолчанию: 0.022; минимум: 0.002; максимум: 0.1; шаг: 0.001 |
| `format=glb → mesh_style=scail → marker_radius_m` | `FLOAT` | да | по умолчанию: 0.0; минимум: 0.0; максимум: 0.1; шаг: 0.001 |
| `format=glb → mesh_style=scail → material_roughness` | `FLOAT` | да | по умолчанию: 0.3; минимум: 0.0; максимум: 1.0; шаг: 0.05 |
| `format=glb → mesh_style=scail → include_hands` | `BOOLEAN` | да | по умолчанию: false |
| `format=glb → mesh_style=scail → hand_marker_radius_m` | `FLOAT` | да | по умолчанию: 0.005; минимум: 0.001; максимум: 0.05; шаг: 0.001 |
| `format=glb → mesh_style=scail → hand_stick_radius_m` | `FLOAT` | да | по умолчанию: 0.003; минимум: 0.001; максимум: 0.05; шаг: 0.001 |
| `format=glb → mesh_style=scail → face_style` | `COMBO` | да | по умолчанию: disabled; варианты: disabled, full, eyes_mouth |
| `format=glb → bone_smooth_window` | `INT` | да | по умолчанию: 0; минимум: 0; максимум: 51; шаг: 2 |
| `format=bvh → units` | `COMBO` | да | по умолчанию: cm; варианты: cm, m |
| `fps` | `FLOAT` | да | по умолчанию: 24.0; минимум: 1.0; максимум: 240.0; шаг: 1.0 |
| `camera_translation` | `COMBO` | да | по умолчанию: off; варианты: off, centered, absolute |
| `track_index` | `INT` | да | по умолчанию: -1; минимум: -1; максимум: 15 |
| `sam3d_body_model` | `SAM3D_BODY_MODEL` | нет | соединение / значение без фиксированного default |

## Выходы

| Выход | Тип | Список |
| --- | --- | --- |
| `model_3d` | `FILE_3D` | нет |

## Проверенные источники и кейсы

В официальном шаблоне `utility_sam3d_body`: Граф: main (root). Входящие связи: `SAM3DBody_Loader`, `SAM3DBody_Smooth`. Исходящие связи: `Save3DAdvanced`. Имя файла: `utility_sam3d_body.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

[Реализация в ComfyUI 0.37.0](https://github.com/Comfy-Org/ComfyUI/blob/73c9bad4d21e7addbe1d13bc92eee0f1431b017d/comfy_extras/nodes_sam3d_body.py#L1105-L1458). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.

Статья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.

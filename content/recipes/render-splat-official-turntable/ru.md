# Turntable Gaussian Splat на 75 кадров

Fragment повторяет подтверждённую часть официального `3d_triposplat_image_to_gaussian_splat`: `CreateCameraInfo` в режиме orbit (`35°`, `30°`, distance `2,5`) подключена к `RenderSplat` с разрешением `1024²`, 75 кадрами, scale `1`, sharpen `2`, стилем `color` и фоном `#848484`.

Подайте внешний `SPLAT`. В оригинальном workflow `IMAGE` идёт в `CreateVideo` с `25 fps`, то есть оборот длится три секунды. Wizard не добавляет video/saver автоматически, чтобы fragment оставался переносимым. Топология проверена, но полное исполнение с TripoSplat и GPU ещё не проводилось.

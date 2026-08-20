# Gaussian Splat во встроенном viewer

Подайте splat-совместимый `File3D` и обязательный `viewport_state` в `PreviewGaussianSplat`. Fragment оставляет `width = 1024` и `height = 1024`. Во время выполнения backend создаёт временную копию, а frontend загружает её из папки `temp`.

Это source-derived fragment: точной ноды нет в workflow wheel 0.1.42. Он не содержит полного workflow и не означает, что браузерный рендер уже проверен на вашем GPU.

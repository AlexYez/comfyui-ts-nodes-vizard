# Point-cloud PLY во встроенном viewer

Подайте `FILE_3D_POINT_CLOUD_ANY` и `viewport_state` в `PreviewPointCloud`. Backend создаст временный `.ply`; frontend выберет point-cloud adapter, если PLY-заголовок не содержит полного набора scale/rotation полей Gaussian Splat.

Fragment выведен из точных backend/frontend-контрактов. В официальном workflow wheel 0.1.42 такой ноды нет, поэтому полного workflow здесь нет.

# SPZ через SaveGLB

Фрагмент повторяет связь узлов № 92 и № 51 из официального `3d_triposplat_image_to_gaussian_splat.json`. `SplatToFile3D` использует `format = spz`; его выход `model_3d` подключён к `mesh` у `SaveGLB`, где задан префикс `3d/ComfyUI_TripoSplat`.

`SaveGLB` не превращает файл в GLB: в этой ветви он получает готовый SPZ и сохраняет те же байты с расширением `.spz`. Fragment не содержит генератор TripoSplat, модели и полный workflow.

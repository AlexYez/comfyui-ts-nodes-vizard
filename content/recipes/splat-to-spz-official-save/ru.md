# Официальная ветвь сохранения SPZ

Фрагмент повторяет узлы `92 → 51` из `3d_triposplat_image_to_gaussian_splat.json`: `SplatToFile3D` использует `format = spz`, а `SaveGLB` получает `model_3d` во вход `mesh` и префикс `3d/ComfyUI_TripoSplat`.

Название `SaveGLB` здесь историческое: по runtime schema нода принимает splat-совместимый `File3D` и сохраняет его с фактическим расширением `.spz`. Полный TripoSplat workflow не прикреплён, потому что он включает модели и зависимости за пределами этого короткого рецепта.

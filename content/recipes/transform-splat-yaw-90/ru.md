# Поворот SPLAT на 90° вокруг Y

Подключите SPLAT. Fragment задаёт `rotate_y = 90`; остальные обязательные поля создаются с runtime defaults: translation `0`, прочие углы `0`, scale `1`.

Это source-derived рецепт: прямого `TransformSplat` в official templates 0.1.42 нет. Порядок в реализации — rotation, затем per-axis scale, затем translation. Сравните результат в одном и том же `RenderSplat`; полный 3D render в проверке не выполнялся.

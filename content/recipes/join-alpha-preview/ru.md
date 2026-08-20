# Собрать RGB и маску прозрачности в RGBA

Подайте цвет в `color_image`, а ComfyUI MASK — в `transparency_mask`. Белое в MASK станет alpha `0` и будет прозрачным; чёрное станет alpha `1` и останется непрозрачным.

Этот участок встречается в пяти official workflow: после удаления фона, segmentation, layer separation и alpha-video decoding. В некоторых шаблонах перед Join стоит `InvertMask`, когда upstream использует другую полярность.

Resize, inversion и batch repeat проверены на synthetic tensors. Полный fragment ещё не запускался в интерфейсе; сохранение конкретным форматом и человеческое утверждение не выполнены.

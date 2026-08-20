# APG: контрольная конфигурация runtime

Fragment вставляет `APG` со значениями интерфейса ComfyUI 0.32.0: `eta = 1`, `norm_threshold = 5`, `momentum = 0`. Это воспроизводимая отправная точка для A/B-сравнения, а не утверждение о лучшей настройке любой модели.

Подайте выход в `CFGGuider` и не используйте CFG=0: pinned hook делит на `cond_scale`. Сохраните seed и сначала сравните результат с полностью удалённой APG-нодой. Tooltip про default CFG при `eta = 1` не означает побитового равенства обычному CFG; exact-source probe показал отличие формулы.

В официальных workflow 0.1.42 APG не найден. Полного workflow и визуального model run нет; проверены schema, exact hook, tensor projection, clipping/momentum branches и ограничения.

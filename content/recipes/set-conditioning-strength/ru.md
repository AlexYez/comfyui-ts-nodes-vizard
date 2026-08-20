# Сила conditioning 0,6

Fragment принимает готовое conditioning и записывает в каждую запись `strength: 0.6`. Embedding, mask и mask strength не меняются.

Area не обязательна. Если она уже задана, коэффициент применяется внутри неё; без area он относится ко всей доступной области записи.

В official workflow templates JSON 0.1.42 runtime ID не найден. Пример проверен по runtime и sampler source, но не исполнялся и остаётся `in_review`.

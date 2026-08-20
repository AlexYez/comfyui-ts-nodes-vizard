# Source-derived SkipLayerGuidanceSD3 перед KSampler

Подайте SD3 MODEL в `ModelSamplingSD3` с shift 3, затем в `SkipLayerGuidanceSD3` с исходными defaults: layers `7, 8, 9`, scale 3, окно 0,01–0,15. Выход соедините с `KSampler`; conditioning и latent приходят извне.

Порядок ставит sampling patch до перевода процентов SLG в sigma. Он выведен из контракта исходника, а не скопирован из официального template: полный census bundle 0.1.42 не нашёл `SkipLayerGuidanceSD3`.

Fragment schema-valid, но не импортировался и не исполнялся. Он не подтверждает, что индексы 7–9 подходят конкретному checkpoint или что preset улучшает результат.

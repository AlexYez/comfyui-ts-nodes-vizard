# SkipLayerGuidanceDiTSimple в развилке Wan Dancer

Подайте MODEL в `ModelSamplingSD3` с shift 5, затем в `SkipLayerGuidanceDiTSimple`: `double_layers = "9"`, пустой `single_layers`, окно 0–1. Выход MODEL направьте одновременно в `BasicScheduler` (`simple`, 48 steps, denoise 1) и `CFGGuider`.

Развилка и SLG widgets взяты из subgraph `f7467834-35a6-42fe-b525-7f17383beb4f`. В оригинале cfg поступает в guider по связи от switch; fragment вместо этого задаёт 3. Значение выбрано для проверки unconditional-ветви: при точном cfg 1 стандартная оптимизация передаёт `uncond = None`, и Simple SLG не включается.

Fragment не содержит noise, sampler, latent и полный Wan Dancer conditioning. Он не импортировался и не исполнялся с весами.

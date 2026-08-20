# ACE: Reinhard перед CFG

Fragment повторяет внутреннюю цепочку трёх official ACE Step 1 templates: внешний MODEL проходит через `ModelSamplingSD3(shift=5)`, а `LatentOperationTonemapReinhard(multiplier=1)` подключается к `LatentApplyOperationCFG`.

В оригиналах выход MODEL идёт в `KSampler` с 50 steps, CFG 5, Euler/simple. Song и instrumentals используют denoise 1, editing — 0,3. Fragment не добавляет sampler и conditioning, потому что они зависят от конкретного ACE-графа. Топология проверена, полное аудиосэмплирование не выполнялось.

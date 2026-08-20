# Sharpen для 4D LATENT

Подайте image LATENT формы `B×C×H×W`. `LatentOperationSharpen` создаётся с runtime defaults: radius `9`, sigma `1`, alpha `0,1`; `LatentApplyOperation` заменяет только tensor `samples`.

Сначала проверьте alpha `0` как identity, затем верните `0,1` и сравните decode при одном VAE. H и W должны быть больше radius из-за reflect padding. Прямого official workflow нет; fragment source-derived и с моделью не исполнялся.

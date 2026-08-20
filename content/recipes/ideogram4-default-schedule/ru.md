# Ideogram 4 Default для 1024 × 1024

Fragment вставляет `Ideogram4Scheduler` с набором `20 / 1024 / 1024 / 0 / 1.75`. Значения `steps`, `mu` и `std` взяты из Default preset двух официальных Ideogram 4 subgraph 0.1.42, а не из случайного сохранённого состояния widget.

Подключите `SIGMAS` к `SamplerCustomAdvanced` совместимого Ideogram 4 графа. Размер latent должен быть тем же — 1024 × 1024. Для другого размера измените оба поля после такого же выравнивания, какое использует официальный workflow.

Модель, guider, sampler, conditioning и latent в fragment не входят. Поле полного workflow отсутствует, а Ideogram generation с весами не выполнялась.

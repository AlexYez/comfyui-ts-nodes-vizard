# FreSca: source-derived runtime defaults

Fragment вставляет `FreSca` с `scale_low = 1.0`, `scale_high = 1.25`, `freq_cutoff = 20`. Подключите output к path, где одновременно вычисляются conditional и unconditional predictions.

Cutoff ограничивается половиной каждой spatial axis. На even prediction `8 × 8` default покрывает весь spectrum, поэтому high-scale не действует, а low-scale `1` даёт identity. Сначала проверьте фактическую форму.

Official wheel 0.1.42 не содержит FreSca. Fragment воспроизводит exact runtime schema, не включает полный workflow и не подтверждён model run.

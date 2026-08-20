# CFG 3 на последних 30% хода

Fragment повторяет форму официального Ideogram v4 subgraph: основной `MODEL` проходит через `CFGOverride`, затем вместе со второй моделью и двумя conditioning входит в `DualModelGuider`. Выход `GUIDER` подключается к `SamplerCustomAdvanced`.

Значения override — `cfg = 3`, `start_percent = 0,7`, `end_percent = 1`. Это sigma-окно, а не гарантированно последние 30% дискретных steps. Loader, prompts, sigmas и latent нужно подобрать под конкретную модель.

Структура и типы сверены с ComfyUI 0.32.0 и `image_ideogram4_t2i` из bundle 0.1.42. Fragment не импортировался в UI и не выполнялся с весами.

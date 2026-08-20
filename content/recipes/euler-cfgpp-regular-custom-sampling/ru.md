# Euler CFG++ regular для custom sampling

Fragment создаёт `SamplerEulerCFGpp(version = regular)` и передаёт его выход `SAMPLER` в `SamplerCustomAdvanced.sampler`.

## Подключение

Подайте в исполнитель согласованный набор `NOISE`, `GUIDER`, `SIGMAS` и `LATENT`. Сам fragment не выбирает модель, CFG, scheduler и seed.

## Почему выбрана regular

Ветка `regular` вызывает зарегистрированный алгоритм `euler_cfg_pp`. Ветка `alternative` использует другую формулу из `nodes_advanced_samplers.py`; менять их без отдельного сравнения на той же модели не следует.

## Что проверено

Типы портов и dispatch обеих версий сверены с runtime `/object_info` и exact source ComfyUI 0.32.0. Полный scan 512 JSON и 272 subgraph не нашёл ни `SamplerEulerCFGpp`, ни выбранного в widget имени `euler_cfg_pp`, поэтому fragment не объявлен официальным workflow-кейсом.

## Что не проверено

Fragment не импортировался в ComfyUI и не запускался с весами. Выходные изображения regular и alternative не сравнивались; человеческое редакционное одобрение ожидается.

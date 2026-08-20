# Второй проход после latent upscale до 1152 × 1152

Этот fragment вырезан из старого официального примера ComfyUI Hires Fix. Первый sampler и загрузчики оставлены внешними входами, чтобы не привязывать recipe к устаревшему checkpoint из демонстрации.

## Что совпадает с официальным workflow

`LatentUpscale` использует `nearest-exact`, `width = 1152`, `height = 1152` и `crop = disabled`. Второй `KSampler` сохраняет `14` шагов, `cfg = 8`, `dpmpp_2m`, scheduler `simple`, `denoise = 0.5` и seed из embedded workflow. После него стоят `VAEDecode` и `SaveImage` с префиксом `ComfyUI`.

В исходном примере первый проход начинается с `EmptyLatentImage 768 × 768`. Поэтому новый grid равен `144 × 144` вместо `96 × 96`, то есть стороны увеличены в 1,5 раза.

## Как подключить fragment

Передайте LATENT первого sampler во вход `first_pass_latent`. `model`, positive и negative должны соответствовать второму проходу, а `vae` — latent-формату входа. Значения sampler из старого SD2.1-примера не являются универсальным пресетом: после проверки топологии подберите их под свою модель.

## Статус проверки

Embedded workflow из официального PNG извлечён и сопоставлен с исходниками ComfyUI `0.32.0`. Fragment прошёл проверку типов, портов и схемы, но не исполнялся. В закреплённом пакете workflow `0.1.42` самой ноды `LatentUpscale` нет; полный legacy workflow намеренно не включён.

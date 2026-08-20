# HiDream O1 Dev: SamplerLCM с ограничением шума

Fragment переносит узлы `SamplerLCM` и `SamplerCustom` из официального `image_hidream_o1_dev`. В закреплённом JSON у `SamplerLCM` widgets равны `[1, 1, 2.5]`, а у исполнителя — `add_noise = true`, seed `270186383729385` с режимом randomize и `cfg = 1`.

## Подключение

Подайте MODEL после официальной для HiDream настройки model sampling, соответствующие positive/negative conditioning, `SIGMAS` и LATENT. В исходном workflow `BasicScheduler` использует `normal`, 28 шагов и denoise 1.

## Что сохраняет fragment

Сохранены точные настройки двух нод и связь `SAMPLER → sampler`. Switch-ноды, загрузчик checkpoint, `ModelNoiseScale(7.6)`, VAE decode и сохранение изображения намеренно оставлены за пределами fragment.

## Что проверено

Прямой кейс найден в root-графе `image_hidream_o1_dev`, UUID `a2143803-dd9d-4fd4-9370-31ce70307498`: node 125 подключён к `SamplerCustom` node 108. Схема fragment и типы портов проверены локально.

## Что не проверено

Fragment не импортировался в UI и не выполнялся с HiDream-весами. Seed из официального файла сохранён как факт сериализации, но режим `randomize` при новом запуске может заменить его; человеческое одобрение ожидается.

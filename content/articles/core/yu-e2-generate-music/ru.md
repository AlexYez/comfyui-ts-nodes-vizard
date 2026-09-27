# YuE2 Generate Music: conditioning по стилю, словам и ABC

Подготавливает музыкальное conditioning YuE2. Может опираться на нотный план ABC или работать без него; возвращает conditioning и фактическую длительность, а не AUDIO.

## Как пользоваться

style и lyrics задают содержание, abc — музыкальную запись. При пустом abc управление по нотам выключается независимо от выбранного mode. max_duration ограничивает продолжительность; temperature, top_p, top_k и repetition_penalty относятся к авторегрессионному этапу. cfg_scale = 1 не усиливает guidance; не путайте его с CFG следующего sampler.

## Пример подключения

Для управляемой мелодии соедините ABC из YuE2GenerateABC либо SheetSage2AudioToABC с abc и согласуйте mode. Подключите seconds к EmptyYuE2LatentAudio, а conditioning — к sampler YuE2. После сэмплирования понадобится соответствующий аудио-декодер.

## Ограничения и частые ошибки

Длинный текст занимает контекст модели и может сократить доступную длительность. Ориентируйтесь на выход seconds, а не только на max_duration. Передача ABC не означает копирование исходной фонограммы или голоса. Энкодер, генеративная модель, latent и VAE должны принадлежать совместимой цепочке YuE2.

## Входы и настройки

Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.

| Вход | Тип | Обязательный | Значения из схемы |
| --- | --- | --- | --- |
| `clip` | `CLIP` | да | соединение / значение без фиксированного default |
| `style` | `STRING` | да | соединение / значение без фиксированного default |
| `lyrics` | `STRING` | да | соединение / значение без фиксированного default |
| `abc` | `STRING` | да | по умолчанию:  |
| `seed` | `INT` | да | по умолчанию: 0; минимум: 0; максимум: 18446744073709551615 |
| `mode` | `COMBO` | да | варианты: full, melody |
| `max_duration` | `FLOAT` | да | по умолчанию: 360.0; минимум: 0.04; максимум: 900.0; шаг: 0.04 |
| `temperature` | `FLOAT` | да | по умолчанию: 1.0; минимум: 0.0; максимум: 5.0; шаг: 0.05 |
| `top_p` | `FLOAT` | да | по умолчанию: 0.95; минимум: 0.01; максимум: 1.0; шаг: 0.01 |
| `top_k` | `INT` | да | по умолчанию: 100; минимум: 1; максимум: 32768 |
| `repetition_penalty` | `FLOAT` | да | по умолчанию: 1.2; минимум: 0.01; максимум: 10.0; шаг: 0.01 |
| `cfg_scale` | `FLOAT` | нет | по умолчанию: 1.0; минимум: 0.0; максимум: 100.0; шаг: 0.01 |

## Выходы

| Выход | Тип | Список |
| --- | --- | --- |
| `CONDITIONING` | `CONDITIONING` | нет |
| `seconds` | `FLOAT` | нет |

## Проверенные источники и кейсы

В cover-шаблоне ABC поступает от SheetSage2 через PreviewAny; в text2music — из ветки генерации нот. В обоих случаях seconds связан с пустым YuE2 latent, а результат KSampler затем декодируется в звук.

В официальном шаблоне `audio_yue2_music_cover`: Граф: Music Cover (YuE2) (root/definitions/subgraphs/0). Входящие связи: `CheckpointLoaderSimple`, `PreviewAny`, `SeedNode`, `SubgraphInput`. Исходящие связи: `ConditioningZeroOut`, `EmptyYuE2LatentAudio`, `KSampler`, `PreviewAny`. Имя файла: `audio_yue2_music_cover.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

В официальном шаблоне `audio_yue2_text2music`: Граф: Text to Music (YuE2) (root/definitions/subgraphs/0). Входящие связи: `CheckpointLoaderSimple`, `PreviewAny`, `PrimitiveStringMultiline`, `SeedNode`, `SubgraphInput`. Исходящие связи: `ConditioningZeroOut`, `EmptyYuE2LatentAudio`, `KSampler`, `PreviewAny`. Имя файла: `audio_yue2_text2music.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

[Реализация в ComfyUI 0.37.0](https://github.com/Comfy-Org/ComfyUI/blob/73c9bad4d21e7addbe1d13bc92eee0f1431b017d/comfy_extras/nodes_yue2.py#L41-L76). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.

Статья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.

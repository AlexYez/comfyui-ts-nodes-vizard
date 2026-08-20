# Заменить SaveAudio на SaveAudioAdvanced без смены формата

Подключите прежний источник к внешнему входу и перенесите пользовательский `filename_prefix`, если он отличался от `audio/ComfyUI`. `SaveAudioAdvanced` уже настроена на FLAC и возвращает тот же `AUDIO` через выход `audio`.

В `/api/node_replacements` 0.32.0 нет автоматического правила для старого saver, а в official workflow bundle 0.1.42 `SaveAudio` отсутствует. Fragment основан на совпадающих runtime-портах и общем writer helper. Изолированно оба класса записали FLAC, но этот fragment не импортировался и не исполнялся целиком.


# Загрузить LTXAV text encoder для двух prompt-ветвей

`LTXAVTextEncoderLoader` получает пару файлов, которая сохранена в официальном image-and-speech-to-video template: Gemma 3 12B FP4 mixed и LTX 2.3 22B dev FP8. Один выход `CLIP` разветвляется в два `CLIPTextEncode`.

Positive и negative тексты оставлены внешними входами. Так fragment не подменяет пользовательский prompt придуманной строкой и сохраняет доказанную топологию официального subgraph.

Если выбрана другая версия LTX, замените оба файла согласованной парой. `device=default` повторяет все 18 официальных случаев в wheel 0.1.42; режим `cpu` имеет другой профиль памяти и скорости.

Схема, типы портов и preset names проверены. Многогигабайтные веса и настоящий text encode не выполнялись, поэтому recipe не считается end-to-end примером.

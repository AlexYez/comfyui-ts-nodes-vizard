# Голосовой референс LTXV ID-LoRA → conditioning → CFGGuider

Fragment повторяет связи ноды №349 из официального `video_ltx2_3_id_lora`: `LTXVReferenceAudio` получает MODEL после ID-LoRA, positive, negative, опорный `AUDIO` и LTX Audio VAE. Сохранённые параметры — scale `3`, начало `0`, конец `1`.

Оба conditioning-выхода проходят через `LTXVConditioning`, где внешний `frame_rate` добавляется к metadata. MODEL-выход и обработанные conditioning подключаются к `CFGGuider` с `cfg = 1`, как в закреплённом subgraph.

Подайте примерно пятисекундный чистый голосовой фрагмент, если следуете условиям, указанным в runtime tooltip. Это рекомендация из обучения, не автоматический trim: нода кодирует весь waveform. Scale `0` отключит дополнительный no-reference pass, но не удалит ref-токены из conditioning. Реальные ID-LoRA, checkpoint и аудиоклип в пакет не входят; полная генерация не выполнялась.

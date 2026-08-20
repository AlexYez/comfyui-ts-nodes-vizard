# MiniMax H3: исходные sigma-shift 12 / 3

Fragment добавляет `MiniMaxH3SigmaShift` с `shift_video = 12` и `shift_audio = 3`. Это defaults точной runtime-схемы и исходные sampling settings MiniMax H3 в ComfyUI 0.32.0; не случайный сохранённый widget preset.

Подключите один и тот же выходной `MODEL` к guider и model-dependent scheduler. При этой паре `audio_scale` равен `4`, а модель выводит audio sigma из текущей video sigma через общую базовую flow-сетку.

В официальных workflow 0.1.42 exact NodeId не найден, поэтому fragment не выдаётся за извлечённую полноценную topology. MiniMax H3 веса не запускались, полный workflow отсутствует.

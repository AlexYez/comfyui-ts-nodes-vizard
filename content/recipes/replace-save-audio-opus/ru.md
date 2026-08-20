# Заменить SaveAudioOpus на SaveAudioAdvanced с Opus 128k

Подключите старый источник к внешнему входу и перенесите prefix. `SaveAudioAdvanced` настроена на Opus 128k — runtime-default обеих нод. При другом legacy quality замените вложенное значение.

Четыре официальных `SaveAudioOpus` сохраняют такую настройку, но все они отключены, отсоединены и не доказывают выполнение. Изолированный encoder-прогон подтвердил Opus 128k и resample 44,1→48 кГц; полный migration-fragment и браузерное прослушивание не выполнялись.


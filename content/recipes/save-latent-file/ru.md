# Сохранить внешний LATENT в output/latents

Передайте LATENT во внешний вход `latent`. Нода создаст файл вида `output/latents/wizard-session_00001_.latent`; следующий запуск с тем же prefix увеличит счётчик.

## Что попадёт в файл

Сохраняются только tensor `samples` под ключом `latent_tensor`, marker формата и разрешённые служебные metadata. `noise_mask`, `batch_index` и пользовательские поля словаря на диск не записываются. Выход ноды при этом продолжает текущую ветку с исходным LATENT.

## Статус примера

В 496 официальных workflow 0.1.42 `SaveLatent` не встречается. Exact-source file branch проверена в временной папке, но сам fragment ещё не запускался в ComfyUI. Полного workflow нет.

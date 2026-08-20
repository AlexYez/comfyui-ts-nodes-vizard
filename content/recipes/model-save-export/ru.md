# Сохранить внешний diffusion MODEL без CLIP и VAE

Подайте `MODEL` после нужных patch или merge и задайте `filename_prefix = diffusion_models/wizard-model`. Первый свободный файл появится в `output/diffusion_models` с пятизначным счётчиком.

Это model-only экспорт. CLIP и VAE в файл не входят, поэтому для дальнейшей работы понадобятся совместимые энкодер текста и автоэнкодер. Не выдавайте этот файл за полный checkpoint. Полного workflow в рецепте нет.

Изолированная проверка выполнила общий save helper на синтетическом MODEL во временной папке и проверила metadata, prediction markers и отсутствие CLIP/VAE в вызове сериализатора. Настоящие веса и полный fragment в ComfyUI не запускались.

Редактор пока не проверил материал вручную.

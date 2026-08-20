# Model-only LoRA для Z-Image Turbo

Fragment повторяет `UNETLoader` № 60 и `LoraLoaderModelOnly` № 62 из корневого графа official `basic_switch_node`. Сохранены exact файлы, `weight_dtype=default`, strength 1 и link 60 между нодами.

В исходном workflow простой switch выбирает исходный или изменённый `MODEL`. Здесь переключатель опущен: после вставки можно самостоятельно сделать две ветви для сравнения с одинаковыми seed и sampling-настройками.

Структура и widgets проверены по JSON 0.1.42 и `/object_info`. Веса не скачивались и изображение не генерировалось.

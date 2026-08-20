# Загрузить .latent и декодировать для проверки

Скопируйте доверенный `.latent` в корень input, затем замените placeholder в `LoadLatent` реальным именем. Подайте исходный совместимый VAE через внешний вход `vae`.

## Что проверяет fragment

Цепочка `LoadLatent` → `VAEDecode` → `PreviewImage` показывает tensor без нового denoise. Если изображение неверно, сначала сверяйте VAE, модельный latent-формат и legacy marker, а не параметры sampler.

## Статус примера

Официальных workflow с `LoadLatent` в полном наборе 0.1.42 нет. File branch выполнена в изолированной временной папке; fragment с настоящим VAE ещё не исполнялся. Полный workflow не приложен.

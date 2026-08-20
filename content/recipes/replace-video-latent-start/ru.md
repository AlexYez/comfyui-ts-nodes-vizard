# Заменить начало video latent

Fragment содержит `ReplaceVideoLatentFrames(index = 0)` и повторяет способ подключения из официального Kandinsky 5 I2V subgraph.

## Подключение

Подайте основную последовательность во вход `destination_video`, а кадры замены — в `source_frames`. Source целиком записывается с позиции 0; длина destination не меняется. Выход можно подключить к следующей latent-операции из вашего video pipeline.

## Что именно проверено

В официальном subgraph два разных выхода подготовительной ноды подключены к `destination` и `source`, `index` равен 0, а выход Replace идёт дальше по latent-ветке. Эта topology, имена портов и настройка сверены с workflow templates 0.1.42.

Exact-source tensor-проба подтвердила замену кадров и происхождение metadata. Полный Kandinsky workflow с весами не запускался, поэтому recipe остаётся fragment-only.

## На что обратить внимание

Оба входа должны быть пятиосевыми и совпадать по batch, channels, height и width. При успешной операции тензор основан на destination, но остальные поля словаря копируются из source. Для четырёхосевого LATENT нода ошибочно воспримет высоту как время.

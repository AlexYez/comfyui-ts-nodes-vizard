# Get Image Size: ширина, высота и размер IMAGE-бэтча

`GetImageSize` читает форму входного IMAGE и выдаёт три целых числа: ширину, высоту и число элементов бэтча. Она нужна, когда геометрию или длину следующей операции следует взять из фактического тензора, а не повторять вручную в виджетах.

## У ноды три INT-выхода

Порядок выходов фиксирован: `width`, `height`, `batch_size`. Все три имеют тип `INT`; выходного IMAGE нет. Вход один — обязательный `image`.

Для тензора из пяти изображений размером `1280 × 720` нода вернёт `width = 1280`, `height = 720`, `batch_size = 5`. Содержимое пикселей на эти числа не влияет.

## Размеры читаются из трёх осей

ComfyUI хранит обычный IMAGE в порядке `batch, height, width, channels`. Реализация берёт `height = image.shape[1]`, `width = image.shape[2]`, `batch_size = image.shape[0]`.

Число каналов нода не возвращает. Она также не вычисляет соотношение сторон, площадь или мегапиксели — для них потребуется отдельная арифметика над width и height.

## IMAGE не проходит через ноду

Описание в source schema и embedded docs утверждает, что исходное изображение «passes through unchanged». Runtime inventory и `execute` этому не соответствуют: объявлены и возвращаются только три `INT`.

Чтобы продолжить IMAGE-ветку, разветвите выход предыдущей ноды: один провод направьте в GetImageSize, второй — в обработку изображения. Не ищите у GetImageSize четвёртый порт и не подключайте INT туда, где ожидается IMAGE.

## Progress text показывает те же три числа

У ноды есть скрытый вход `unique_id`. Когда он доступен, реализация отправляет в интерфейс текст `width`, `height` и `batch size`. Это подпись состояния, а не дополнительный выход графа.

Сохранённый workflow иногда содержит эту строку в `widgets_values`, но при следующем выполнении она вычисляется из текущего входа. Для связей используйте выходные INT-порты, а не текст, показанный на карточке.

## Официальный product-ad связывает размеры двух изображений

В `templates-product_ad-v2.0` LoadImage № 1 идёт в GetImageSize № 17. Его `width` и `height` подключены к `target_width` и `target_height` ResizeAndPadImage № 16, куда приходит другое загруженное изображение.

Так второе изображение вписывается в размеры первого. Сохранённые `512 × 512` у ResizeAndPadImage перекрыты проводами; фактическая геометрия определяется reference IMAGE во время выполнения.

## batch_size может адресовать последний кадр

В `api_vidu_video_extension` GetVideoComponents № 3 разветвляет `images` в GetImageSize № 10 и ImageFromBatch № 5. Выход `batch_size` подключён к `batch_index` ImageFromBatch.

Для бэтча размера `B` приходит индекс `B`, а ImageFromBatch прижимает его к `B − 1`. Поэтому выбирается последний кадр и передаётся в `end_frame` ViduExtendVideoNode. Здесь связь важнее сохранённого виджета `batch_index = 0`.

## Официальный инвентарь охватывает 80 нод

Полный рекурсивный просмотр wheel 0.1.42 нашёл 80 GetImageSize в 60 файлах: 25 в корневых графах и 55 в subgraph. В обычном режиме сохранены 78 экземпляров, два — в bypass (`mode = 4`).

Практические роли повторяются: width и height управляют resize или model dimensions, batch_size задаёт длину либо граничный индекс. Одинаковый workflow UUID встречается в разных файлах, поэтому инвентарь считает файлы и ноды, а не только UUID.

## Подключённый INT перекрывает виджет потребителя

Когда width, height или batch_size входят проводом в числовой виджет другой ноды, связанное значение используется при выполнении. Число, оставшееся в `widgets_values` потребителя, становится запасным состоянием и не описывает фактический запуск.

Это особенно заметно в десяти официальных ResizeAndPadImage с сохранёнными `512 × 512`: размеры у всех перекрыты связями. При чтении workflow проверяйте поле `link`, а не только видимый список значений.

## Fragment повторяет выбор последнего видеокадра

Рецепт «Выбрать последний видеокадр через batch_size» содержит GetVideoComponents, GetImageSize и ImageFromBatch. Один IMAGE-выход разветвляется в обе ноды, а `batch_size` управляет `batch_index`.

Fragment заканчивается выбранным IMAGE и не включает платную или модельную Vidu-ноду. Он воспроизводит проверяемую часть официальной топологии, но не исполнялся с реальным VIDEO в текущем редакционном прогоне.

## Если числа выглядят неверно

Проверьте порядок width и height: ширина соответствует оси 2, высота — оси 1. Убедитесь, что GetImageSize получает тот же IMAGE, который идёт дальше, а не раннюю версию до resize или crop.

Если batch_size неожиданно равен 1, upstream-нода могла выбрать один кадр или схлопнуть последовательность. Если downstream продолжает использовать старое число, проверьте провод к нужному входу и bypass-режим. Человеческое утверждение примера ещё не выполнено.

## Источники

- [GetImageSize в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L569-L601)
- [Embedded docs 0.5.9 для GetImageSize](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/GetImageSize/en.md)
- [Официальный `templates-product_ad-v2.0`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/templates-product_ad-v2.0.json)
- [Официальный `api_vidu_video_extension`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/api_vidu_video_extension.json)

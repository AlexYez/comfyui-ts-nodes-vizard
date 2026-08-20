# Сохранить IMAGE-список без перезаписи имён

Подключите списочный `IMAGE` к внешнему входу fragment. `SaveImageDataSetToFolder` запишет восьмибитные PNG в `output/dataset` с префиксом `image`; `increment` добавит счётчик вместо прямой замены совпавших имён.

Нода deprecated. Комментарий исходника рекомендует обычный `SaveImage` с подпапкой в `filename_prefix`, но формальной записи в Node Replacement API нет. Fragment оставляет устаревший runtime ID для диагностики старого графа, отсутствует в официальных workflow 0.1.42 и не исполнялся после импорта.

# INT и FLOAT перед PreviewAny

Фрагмент повторяет две независимые связи из официального `basic_datatype_conversion`: `PrimitiveInt(0)` и `PrimitiveFloat(1.5)` идут в отдельные `PreviewAny`.

Используйте его как короткую проверку типа и значения перед подключением чисел к ресурсоёмкому графу. Preview преобразует данные в текст; primitive-ноды сами ничего не форматируют.

Пара `control_after_generate: fixed` у INT относится к frontend-виджету и не добавлена как backend setting фрагмента.

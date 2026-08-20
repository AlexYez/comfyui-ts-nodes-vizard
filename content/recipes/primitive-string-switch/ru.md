# Строковый switch из primitive-нод

Фрагмент повторяет малую топологию официального `basic_switch_node`: строки `true` и `false` остаются типом `STRING`, а отдельный `PrimitiveBoolean` управляет `ComfySwitchNode`.

После вставки подключите выход `output` к `PreviewAny` или строковому входу. Переключение флага должно менять вариант, но не тип результата.

Это проверенный schema/topology fragment, а не выполненный полный workflow. Ленивая обработка ветвей зависит от `ComfySwitchNode`; primitive-ноды только передают константы.

# Truthiness без тяжёлого графа

Пустая строка проходит через NOT и превращается в true. Непустая `ready` вместе с этим true даёт AND=true. Пустая строка вместе с INT 0 даёт OR=false.

Входы `values.value0` и `values.value1` — semantic имена autogrow-портов. Добавляйте до десяти значений, но сначала приводите многoэлементные tensors к явному scalar: Python truth test для них может быть неоднозначным.

Прямых official workflow для трёх logic-нod в templates 0.1.42 нет. Фрагмент честно основан на закреплённом исходнике и runtime schema; полный граф не исполнялся.

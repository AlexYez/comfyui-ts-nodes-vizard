# Hypernetwork поверх внешнего MODEL

Подключите `MODEL` из совместимого loader к внешнему входу fragment, выберите реальный файл в `models/hypernetworks` и начните со strength, указанного автором. После ноды подключите тот же sampling-граф, который используется для контрольной ветви без patch.

Следите за логом: unsupported activation не обязательно прерывает выполнение, но output останется клоном без hypernetwork. Для честного сравнения закрепите seed и остальные параметры.

Official package 0.1.42 не содержит примера этой ноды. Fragment проверен по runtime и source, но файл hypernetwork и полный sampling не исполнялись.

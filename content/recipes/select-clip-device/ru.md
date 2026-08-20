# Направить CLIP на второй GPU

Подайте `CLIP` во вход `SelectCLIPDevice` и выберите `device = gpu:1`. На системе с двумя GPU patcher получает второе доступное устройство как load device. Его offload device остаётся исходным выбором loader.

Если `gpu:1` отсутствует, runtime всё равно принимает сохранённое значение, возвращает CLIP clone с прежней маршрутизацией и пишет сообщение в лог. Если loader не умеет создать fresh deepclone, нода ловит `RuntimeError` и также оставляет routing без изменения.

Fragment не кодирует prompt и не измеряет скорость. Exact-source probe проверил ветки `gpu:1`, `cpu`, `default` и unavailable-device на синтетических patcher. При fresh retarget probe также обнаружил разные ссылки `cond_stage_model` и `patcher.model`; настоящая CLIP-модель на GPU не запускалась, поэтому полная миграция encode не подтверждена.

Редактор пока не проверил материал вручную.

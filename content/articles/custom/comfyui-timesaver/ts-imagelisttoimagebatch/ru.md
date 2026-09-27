# TS Image List to Image Batch

<table>
<tr>
<td><img src="doc/screenshots/ts_image_batch_to_list.png" alt="Batch to List" width="300" /></td>
<td><img src="doc/screenshots/ts_image_list_to_batch.png" alt="List to Batch" width="300" /></td>
</tr>
</table>

Конвертация между `IMAGE` (один батчевый тензор) и `IMAGE`-list (Python-список одиночных тензоров). Нужно, когда одна нода ожидает батч, а следующая хочет покадровую итерацию.

## Проверка и происхождение материала

Материал импортирован из встроенной справки `comfyui-timesaver` на 2026-09-27; регистрация ноды проверена по исходнику. Статья имеет статус черновика до отдельной ручной редакционной проверки в Wizard. Если установлена другая версия пака, ориентируйтесь также на живые входы и выходы в панели.

- [Закреплённый исходник ноды](https://github.com/AlexYez/comfyui-timesaver/blob/c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f/nodes/image/ts_image_list_to_batch.py#L145)

# TS Image Batch to Image List

<table>
<tr>
<td><img src="doc/screenshots/ts_image_batch_to_list.png" alt="Batch to List" width="300" /></td>
<td><img src="doc/screenshots/ts_image_list_to_batch.png" alt="List to Batch" width="300" /></td>
</tr>
</table>

Конвертация между `IMAGE` (один батчевый тензор) и `IMAGE`-list (Python-список одиночных тензоров). Нужно, когда одна нода ожидает батч, а следующая хочет покадровую итерацию.

## Проверка и происхождение материала

Описание сверено с реализацией `comfyui-timesaver` и встроенной справкой пака на 2026-09-01. Статья имеет статус черновика до отдельной ручной редакционной проверки в Wizard. Если установлена другая версия пака, ориентируйтесь также на живые входы и выходы в панели.

- [Закреплённый исходник ноды](https://github.com/AlexYez/comfyui-timesaver/blob/29b0e730f19a1147cab29399652265f946663194/nodes/image/ts_image_batch_to_list.py#L91)

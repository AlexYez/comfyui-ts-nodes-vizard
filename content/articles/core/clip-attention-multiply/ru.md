# CLIPAttentionMultiply: масштабировать проекции self-attention

## Что делает нода

`CLIPAttentionMultiply` клонирует `CLIP`, просматривает его state dict и масштабирует совпавшие параметры четырёх проекций self-attention: query (`q`), key (`k`), value (`v`) и выход (`out`). Для каждого совпадения множитель применяется и к весу, и к смещению (`bias`).

Нода ищет не абстрактный тип слоя, а точные окончания имён: `self_attn.q_proj.weight`, `self_attn.q_proj.bias` и аналогичные `k_proj`, `v_proj`, `out_proj`. Если энкодер хранит attention под другими ключами, ни один параметр не изменится.

Runtime помечает ноду experimental. Она не добавляет новый attention-модуль и не меняет tokenizer; output — clone входного CLIP с patches, которые умножат существующие веса при materialization.

## Когда использовать и когда не использовать

Используйте ноду для измеримого эксперимента над известной CLIP-архитектурой, когда можно проверить список совпавших ключей и сравнить conditioning на фиксированном prompt-наборе. Меняйте один коэффициент за раз и держите рядом bypass-ветку.

Не применяйте её как универсальный способ «усилить понимание prompt». Масштаб параметров не имеет простой шкалы качества. Изменение q и k перестраивает распределение softmax, v меняет передаваемые значения, out — выходную проекцию; residual connections и layer normalization продолжают работать.

Для выбора более раннего hidden layer используйте `CLIPSetLastLayer`. Для смешивания двух encoder предназначены CLIP merge-ноды. Эти операции затрагивают разные уровни модели.

## Короткий рецепт подключения

1. Подайте проверяемый encoder в `clip`.
2. Оставьте три параметра равными `1` и измените один, например `q = 0.90`.
3. Передайте output в `CLIPTextEncode` с фиксированным prompt.
4. Сравните tensor statistics и конечный результат с прямым подключением того же CLIP.
5. Если отличий нет, проверьте state-dict suffixes: нода могла не найти ни одного поддерживаемого ключа.

Fragment «Проверить один коэффициент CLIP attention» содержит ноду со значениями `q = 0.90`, `k = v = out = 1`. `CLIP`, encode и workflow остаются внешними; это source-derived эксперимент, не официальный preset.

## Входы, выходы и параметры

`clip` принимает `CLIP`. `q`, `k`, `v` и `out` — advanced `FLOAT` от `0` до `10`, default `1`, шаг `0.01`. Отрицательные множители runtime не допускает. Выход один — `CLIP`.

Для совпавшего ключа нода регистрирует `add_patches({key: (None,)}, strength_patch=0, strength_model=factor)`. Patch без diff и с нулевой добавкой означает: взять текущий параметр и умножить его на factor.

`q` применяется к `q_proj.weight` и `q_proj.bias` всех найденных self-attention слоёв; `k`, `v` и `out` — к своим парам. Cross-attention, MLP, embeddings, layer norms и параметры с иным naming не затрагиваются.

При factor `1` численное значение совпавших weights остаётся прежним, хотя patch records всё равно создаются. При `0` совпавшие weight и bias обнуляются. Это не обнуляет весь CLIP: остаются остальные проекции, residual path, normalization и все неподдержанные компоненты.

## Типовые связки

Минимальная цепочка: `CLIPLoader → CLIPAttentionMultiply → CLIPTextEncode`. Для checkpoint loader используйте его CLIP-выход точно так же. Diffusion `MODEL` сама нода не меняет.

`CLIPSetLastLayer` можно поставить после AttentionMultiply, чтобы отдельно выбрать hidden layer, но тогда эксперимент имеет две переменные. Для первого сравнения оставьте layer setting одинаковым в bypass и modified ветвях.

Несколько `CLIPAttentionMultiply` подряд на одних и тех же ключах последовательно масштабируют patches. Например, два множителя `0.5` дают общий коэффициент `0.25`, а не среднее `0.5`.

С составным `CLIP`, содержащим несколько text encoders, изменятся лишь компоненты с поддерживаемыми suffixes. Это может создать частично модифицированный объект: например, CLIP-подобная часть изменится, а T5-подобная — нет.

## Практический пример

Исчерпывающий scan 512 JSON-файлов официального пакета 0.1.42, включая root и `definitions.subgraphs[*].nodes`, не нашёл `CLIPAttentionMultiply`. Официальных widgets и topology для этой ноды в выбранной версии нет.

Exact-source probe создал state dict с восемью поддерживаемыми ключами: weight и bias для q, k, v и out. Значения `0.5`, `1.5`, `2` и `0` породили ровно восемь patches с `strength_patch = 0` и соответствующими `strength_model`. Похожие ключи `cross_attn.q_proj.weight` и `mlp.fc1.weight` были пропущены.

Отдельный вызов точной `calculate_weight` умножил `[2, 4]` на `1.5` и вернул `[3, 6]`. Probe не запускал transformer forward, поэтому влияние на attention probabilities и изображения остаётся непроверенным.

## Частые ошибки и способы проверки

**Параметры меняются, а результат нет.** Проверьте, используется ли именно этот CLIP в encode-ветви и отличается ли prompt. При factor, близком к `1`, изменение может быть малым.

**Нода не зарегистрировала ни одного patch.** Архитектура использует другое naming, например объединённый `in_proj_weight`. Exact suffix matching не адаптируется автоматически.

**Одновременно изменены q и k.** До softmax query и key входят в скалярное произведение; их масштабы взаимодействуют. Возвращайте один к `1` и измеряйте второй отдельно.

**Factor 0 принят за отключение attention.** Он обнуляет выбранную проекцию и bias, но слой содержит другие проекции и residual branch. Итог не равен удалению всего self-attention блока.

**Большой factor вызывает перенасыщенное или нестабильное conditioning.** Верхняя граница `10` — контракт виджета, не рекомендуемый preset. Начните с небольшого отклонения от единицы.

**Составной encoder изменился частично.** Составьте список matched keys по каждому подэнкодеру. Отсутствие ошибки типа `CLIP` не означает одинаковую поддержку naming.

**Две ноды подряд дали слишком сильный эффект.** Множители композируются. Перемножьте их по каждой проекции и замените цепочку одним экземпляром для прозрачности.

## Производительность и внутреннее поведение

На этапе выполнения нода клонирует wrapper и проходит по `model_state_dict`. Сложность поиска линейна по числу параметров. Для matched keys она хранит patch без отдельного diff tensor, поэтому служебные записи легче полноценного model merge.

При загрузке CLIP patcher умножает weights на coefficients. Число матричных операций во время text encode не уменьшается при factor меньше единицы и не растёт при factor больше единицы; меняются значения, а не архитектура.

Factor `1` не даёт вычислительного ускорения: state dict уже просмотрен, patches созданы. Для настоящего bypass подключайте исходный CLIP напрямую.

Output clone сохраняет tokenizer и cond-stage model первого объекта. Patch list отделён от входа, но underlying weights управляются общим patcher-механизмом ComfyUI; нода не создаёт новый файл на диске.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, модуль `comfy_extras.nodes_attention_multiply`. Runtime fingerprint: `sha256:75ccff59df5d980eb2ec9e6051eb677228f7d56cb67c7e4cde95da4eb314837f`.

Нода имеет `experimental = true`, не deprecated и не API node. В Node Replacement API записи нет. Runtime aliases — `clip attention scale` и `text encoder attention`; это search aliases, не execution class aliases.

Embedded docs 0.5.9 верно перечисляют четыре группы проекций и диапазоны, но не описывают exact suffix matching. Поэтому справка не предупреждает о допустимом clone без единого изменённого параметра.

## Связанные ноды и источники

`CLIPTextEncode` превращает изменённый encoder в conditioning для сравнения. `CLIPSetLastLayer` выбирает глубину скрытого состояния. `CLIPMergeSimple` меняет полный набор общих weights двух encoder, а не только self-attention projections.

- [Реализация `CLIPAttentionMultiply`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_attention_multiply.py#L69-L101)
- [Семантика patch без diff](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/lora.py#L438-L493)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/CLIPAttentionMultiply/en.md)
- [Официальные workflow-шаблоны 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)

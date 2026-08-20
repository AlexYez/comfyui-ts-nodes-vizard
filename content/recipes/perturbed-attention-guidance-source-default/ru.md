# PAG: source-derived runtime default

Fragment вставляет `PerturbedAttentionGuidance` со `scale = 3.0`, точным default ComfyUI 0.32.0. Подайте выходной `MODEL` в прежний sampling path и сравните результат с полностью обойдённой нодой при неизменных seed, prompt, sampler и sigmas.

При ненулевом scale нода делает дополнительный conditional model call на каждом шаге. `scale = 0` отключает этот вызов и PAG-поправку, но для контрольного графа всё равно полезно сохранить отдельный вариант без patch.

В официальном workflow wheel 0.1.42 точный NodeId не найден. Fragment получен из pinned source и runtime schema; он не содержит полного workflow и не подтверждает качество default на конкретной модели.

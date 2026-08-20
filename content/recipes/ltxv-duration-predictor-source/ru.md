# Подключить LTX 2.4 duration head

Fragment принимает готовый `MODEL_PATCH` и передаёт его в `LTXVDurationPredictor`. Загрузите LTX 2.4 duration head через `ModelPatchLoader` отдельно. Внешние `MODEL` и positive `CONDITIONING` должны принадлежать совместимой LTX 2.4 цепочке.

Fragment не закрепляет имя файла: combo-значения зависят от локальной папки `models/model_patches`, а официальный wheel 0.1.42 не содержит точного duration workflow. Такой контракт не подменяет неизвестный asset вымышленным именем.

При defaults raw prediction ограничивается диапазоном 1–20 секунд только для вычисления `num_frames`. Выход `seconds` остаётся исходным числом head. Число кадров округляется и привязывается к causal grid `8k + 1`.

Проба выполнила точный node method с подклассом настоящего `DurationHead`, проверила split video/audio tokens, ограничение batch conditioning до первого элемента и frame conversion. Реальный duration checkpoint не загружался, поэтому fragment не считается выполненным end-to-end и ждёт человеческого утверждения.

## Источники

- [LTXV Duration Predictor](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L1123-L1174)
- [DurationHead и `seconds_to_num_frames`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/duration_head.py#L25-L81)

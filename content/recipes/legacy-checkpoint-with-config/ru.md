# Диагностическая загрузка checkpoint с YAML

Этот fragment предназначен для старого графа, который уже зависит от `CheckpointLoader`. Перед вставкой выберите реальный checkpoint и его YAML; placeholders намеренно не притворяются существующими файлами.

После загрузки отдельно проверьте `MODEL`, `CLIP` и `VAE` на минимальном контрольном графе. Затем сравните результат с `CheckpointLoaderSimple`. Если различие связано с `parameterization: v` или `cond_stage_config.params.layer_idx`, перенесите соответствующую настройку осознанно. Автоматической replacement-записи для этой ноды в baseline нет.

Official workflow package 0.1.42 не содержит `CheckpointLoader`, а тестовая установка не содержит legacy-пары файлов. Fragment проверен по схеме и коду, но не исполнен.

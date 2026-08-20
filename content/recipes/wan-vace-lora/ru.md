# LoRA поверх раздельно загруженных компонентов Wan VACE

Fragment повторяет активную ветвь official workflow `video_wan_vace_14B_t2v` из пакета 0.1.42. В исходном графе `UNETLoader` № 106 и `CLIPLoader` № 110 подключены к `LoraLoader` № 107. Сохранены exact имена файлов, `type=wan`, `weight_dtype=default` и коэффициенты LoRA 0,7/1.

После вставки выход `MODEL` от `LoraLoader` нужно передать в model-sampling и sampling-ветвь Wan VACE, а `CLIP` — в совместимые ноды кодирования текста. Fragment намеренно не изображает полный Wan pipeline: ему нужны VAE, latent/video conditioning и sampling-настройки из model-specific workflow.

Три файла весов перечислены как обязательные зависимости, а не как универсальные placeholders. Wizard должен остановить вставку, если соответствующих нод или файлов нет. Веса не скачивались, inference не выполнялся; проверены JSON-топология, имена портов, runtime-схемы и происхождение параметров.

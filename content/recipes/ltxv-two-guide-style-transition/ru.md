# Два LTXV guide для перехода от первого референса к последнему

Fragment сохраняет exact topology официального `video_ltx2_3_flf2v`: два `LTXVPreprocess(img_compression=25)` подготавливают изображения, затем две `LTXVAddGuide` последовательно добавляют guides `frame_idx=0/strength=0.7` и `frame_idx=-1/strength=0.7`. В LTX 2.5 структура та же, но оба preprocessing-узла используют CRF `18`, поэтому этот preset не выдан за точную копию 2.5.

Positive, negative и LATENT входят в первую guide-ноду; её три выхода переходят во вторую. Подключите один совместимый VAE к обоим external VAE inputs. После второй guide нужен sampler, а после него — `LTXVCropGuides`; эти стадии намеренно не включены, чтобы fragment не создавал ложную прямую связь Crop до sampling.

PyAV codec, VAE weights и полный video sampling не исполнялись. Параметры и связи сверены с official wheel, socket types — с pinned `/object_info`.
